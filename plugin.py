import asyncio
import base64
import os
import re
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

import aiofiles
import aiohttp
from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Action, Command, Field, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import ActivationType


class PluginSectionConfig(PluginConfigBase):
    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    config_version: str = Field(default="3.2.0", description="配置版本")
    enabled: bool = Field(default=True, description="是否启用插件")


class ComponentsConfig(PluginConfigBase):
    __ui_label__ = "组件"
    __ui_icon__ = "sliders-horizontal"
    __ui_order__ = 1

    action_enabled: bool = Field(default=True, description="是否启用关键词触发")
    command_enabled: bool = Field(default=True, description="是否启用 /vits 命令")
    mode_command_enabled: bool = Field(default=False, description="新版暂不支持旧自动模式")


class VitsConfig(PluginConfigBase):
    __ui_label__ = "GPT-SoVITS"
    __ui_icon__ = "volume-2"
    __ui_order__ = 2

    api_url: str = Field(default="http://localhost:9880/", description="GPT-SoVITS API 地址")
    default_voice_id: str = Field(default="0", description="默认音色 ID")
    language: str = Field(default="zh", description="文本与参考音频语言")
    ref_audio_path: str = Field(default="", description="参考音频绝对路径")
    prompt_text: str = Field(default="", description="参考音频文本")
    timeout: int = Field(default=60, description="请求超时时间（秒）")
    max_text_length: int = Field(default=500, description="单次合成最大文本长度")
    retry_count: int = Field(default=2, description="失败重试次数")
    audio_format: str = Field(default="wav", description="音频文件格式")
    auto_language_rewrite: bool = Field(default=True, description="发送到 TTS 前按 language 自动改写语言")
    language_rewrite_model: str = Field(default="utils", description="语言改写使用的模型任务")
    block_on_language_rewrite_failure: bool = Field(default=True, description="语言改写失败时阻止继续合成")
    keyword_trigger_enabled: bool = Field(default=True, description="是否启用显式关键词直触发")
    keyword_trigger_phrases: str = Field(
        default="再发一句语音,再来一句语音,发语音,发一句语音,来句语音,来一句语音,再说一句,再说句话,说句话,说一句,念一句,朗读,念出来,用语音说,语音说",
        description="逗号分隔的显式触发关键词",
    )
    keyword_default_text: str = Field(default="行吧，就再说一句。测试到这里差不多了。", description="只有触发词没有朗读内容时使用的默认文本")


class CacheConfig(PluginConfigBase):
    __ui_label__ = "缓存"
    __ui_icon__ = "database"
    __ui_order__ = 3

    expire_minutes: int = Field(default=30, description="缓存保留时间（分钟）")
    max_size_mb: int = Field(default=100, description="缓存最大容量（MB）")


class GPTSoVITSConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    vits: VitsConfig = Field(default_factory=VitsConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)


class GPTSoVITSV2TTSPlugin(MaiBotPlugin):
    config_model = GPTSoVITSConfig

    def __init__(self) -> None:
        super().__init__()
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_audio_cache")
        os.makedirs(self._cache_dir, exist_ok=True)

    async def on_load(self) -> None:
        if self.config.plugin.enabled:
            await self._ensure_session()
        self.ctx.logger.info("GPT-SoVITS TTS 插件加载完成")

    async def on_unload(self) -> None:
        await self._close_session()
        self.ctx.logger.info("GPT-SoVITS TTS 插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        del config_data, version
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            await self._close_session()
            if self.config.plugin.enabled:
                await self._ensure_session()

    @Action(
        "vits_tts_action",
        description="使用 GPT-SoVITS 语音合成将文本转换为语音发送",
        activation_type=ActivationType.KEYWORD,
        activation_keywords=["语音", "说话", "朗读", "念出来", "用语音说", "vits", "tts"],
        action_parameters={
            "text": "需要朗读的文本内容。优先按插件 config.toml 中 vits.language 指定的语言组织原句，例如 language=ja 时应传入自然日语。",
            "voice_id": "音色 ID，可选",
        },
        action_require=["用户明确要求语音、朗读、念出文本时使用", "待朗读文本应尽量使用 TTS 配置的目标语言"],
        associated_types=["text"],
    )
    async def handle_vits_action(self, stream_id: str = "", text: str = "", voice_id: str = "", **kwargs: Any):
        del kwargs
        if not self.config.components.action_enabled:
            return False, "关键词语音触发未启用"
        success, message, _ = await self._synthesize_and_send(
            text=text,
            stream_id=stream_id,
            voice_id=voice_id or None,
        )
        return success, message

    @Command("vits_tts_command", description="手动语音合成", pattern=r"^/vits\s+(?P<text>.+?)(?:\s+(?P<voice_id>\d+))?$")
    async def handle_vits_command(self, stream_id: str = "", **kwargs: Any):
        if not self.config.components.command_enabled:
            return False, "/vits 命令未启用", True

        matched_groups = kwargs.get("matched_groups")
        if not isinstance(matched_groups, dict):
            matched_groups = {}

        text = str(matched_groups.get("text") or "").strip()
        voice_id = str(matched_groups.get("voice_id") or "").strip() or None
        return await self._synthesize_and_send(text=text, stream_id=stream_id, voice_id=voice_id)

    @Command(
        "vits_keyword_command",
        description="显式关键词直接触发语音",
        pattern=r"(?<!/)(?:再发一句语音|再来一句语音|发语音|发一句语音|来句语音|来一句语音|再说一句|再说句话|说句话|说一句|念一句|朗读|念出来|用语音说|语音说)",
    )
    async def handle_vits_keyword_command(self, text: str = "", stream_id: str = "", **kwargs: Any):
        del kwargs
        if (
            not self.config.plugin.enabled
            or not self.config.components.action_enabled
            or not self.config.vits.keyword_trigger_enabled
        ):
            return False, None, False

        tts_text = self._extract_keyword_tts_text(text)
        if not tts_text:
            return False, None, False

        self.ctx.logger.info("TTS keyword trigger matched: raw=%s, tts_text=%s", (text or "")[:120], tts_text[:120])
        success, message, _ = await self._synthesize_and_send(text=tts_text, stream_id=stream_id)
        if not success and stream_id:
            await self.ctx.send.text(f"语音发送失败：{message}", stream_id)
        return success, message, True

    @Command("vits_clean_command", description="清理 TTS 缓存", pattern=r"^/vitsclean$")
    async def handle_vits_clean_command(self, stream_id: str = "", **kwargs: Any):
        del kwargs
        await self.clean_cache_task(force=True)
        if stream_id:
            await self.ctx.send.text("缓存已清理", stream_id)
        return True, "缓存已清理", True

    @Command("vits_mode_command", description="旧版自动 TTS 模式提示", pattern=r"^/vitsmode\s*(?P<mode>on|off)?\s*$")
    async def handle_vits_mode_command(self, stream_id: str = "", **kwargs: Any):
        del kwargs
        if stream_id:
            await self.ctx.send.text("新版 MaiBot 插件运行时暂不支持旧版全局自动 TTS 拦截，请使用 /vits <文本>。", stream_id)
        return False, "新版暂不支持旧版全局自动 TTS 拦截", True

    async def _synthesize_and_send(self, text: str, stream_id: str, voice_id: Optional[str] = None):
        if not self.config.plugin.enabled:
            return False, "TTS 插件未启用", True

        text = (text or "").strip()
        if not text:
            return False, "没有提供需要朗读的文本", True
        if not stream_id:
            return False, "缺少聊天流 stream_id", True

        audio_path = await self.synthesize_voice(text, voice_id=voice_id)
        if not audio_path:
            return False, "语音合成失败", True

        sent = await self.send_voice_file(audio_path, stream_id=stream_id, text=text)
        asyncio.create_task(self.clean_cache_task())
        if not sent:
            return False, "语音已合成但发送失败", True
        return True, "语音发送成功", True

    def _extract_keyword_tts_text(self, raw_text: str) -> Optional[str]:
        text = (raw_text or "").strip()
        if not text or text.startswith("/"):
            return None

        lowered = text.lower()
        for phrase in self._keyword_trigger_phrases():
            phrase_lower = phrase.lower()
            index = lowered.find(phrase_lower)
            if index < 0:
                continue

            after_payload = self._normalize_keyword_payload(text[index + len(phrase) :])
            if after_payload:
                return after_payload

            before_payload = self._normalize_keyword_payload(text[:index], strip_leading=True)
            if before_payload and not self._is_keyword_request_fluff(before_payload):
                return before_payload

            default_text = (self.config.vits.keyword_default_text or "").strip()
            return default_text or None

        return None

    def _keyword_trigger_phrases(self) -> list[str]:
        raw = self.config.vits.keyword_trigger_phrases or ""
        phrases = [item.strip() for item in re.split(r"[,，\n]+", raw) if item.strip()]
        return sorted(set(phrases), key=len, reverse=True)

    @staticmethod
    def _normalize_keyword_payload(text: str, strip_leading: bool = False) -> str:
        value = (text or "").strip().strip(" \t\r\n,，。.:：;；!！?？")
        prefixes = (
            "内容是",
            "内容为",
            "内容",
            "说一下",
            "说下",
            "说",
            "读一下",
            "读下",
            "读",
            "念一下",
            "念下",
            "念",
            "一下",
            "下",
            "一段",
            "一句",
            "这段话",
            "这句话",
            "这个",
        )
        if strip_leading:
            prefixes = ("请", "麻烦", "帮我", "帮忙", "把", "将", "让", "来", "再", "能不能", "能") + prefixes

        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if value.startswith(prefix):
                    value = value[len(prefix) :].strip(" \t\r\n,，。.:：;；!！?？")
                    changed = True

        if GPTSoVITSV2TTSPlugin._is_keyword_request_fluff(value):
            return ""
        return value

    @staticmethod
    def _is_keyword_request_fluff(value: str) -> bool:
        normalized = (value or "").strip().strip(" \t\r\n,，。.:：;；!！?？")
        return normalized in {
            "",
            "你",
            "您",
            "请",
            "麻烦",
            "帮我",
            "帮忙",
            "可以",
            "能不能",
            "能",
            "你再",
            "您再",
            "再",
            "吧",
            "嘛",
            "吗",
            "啦",
            "了",
            "呗",
            "啊",
            "呀",
            "呢",
            "哈",
            "欸",
            "看看",
            "试试",
            "一下",
            "下",
            "一条",
            "一句",
        }

    async def _ensure_session(self) -> None:
        if self._session and not self._session.closed:
            return
        timeout = aiohttp.ClientTimeout(total=max(1, int(self.config.vits.timeout)))
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def _close_session(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def send_voice_file(self, audio_path: str, stream_id: str, text: str = "") -> bool:
        try:
            async with aiofiles.open(audio_path, "rb") as f:
                audio_base64 = base64.b64encode(await f.read()).decode("ascii")
        except Exception as exc:
            self.ctx.logger.error("读取 TTS 音频失败: %s", exc)
            return False

        return bool(
            await self.ctx.send.custom(
                "voice",
                audio_base64,
                stream_id,
                processed_plain_text="[语音]" if not text else f"[语音] {text[:80]}",
            )
        )

    async def synthesize_voice(self, text: str, voice_id: Optional[str] = None) -> Optional[str]:
        await self._ensure_session()
        if not self._session:
            return None

        text = (text or "").strip()
        if not text:
            self.ctx.logger.warning("TTS 文本为空")
            return None

        api_urls = self._candidate_api_urls(self.config.vits.api_url)
        ref_path = self.config.vits.ref_audio_path
        language = self.config.vits.language
        retry_count = max(1, int(self.config.vits.retry_count))
        max_text_length = max(1, int(self.config.vits.max_text_length))

        if not ref_path:
            self.ctx.logger.warning("未配置参考音频路径 vits.ref_audio_path")
            return None
        if not os.path.exists(ref_path):
            self.ctx.logger.warning("参考音频不存在: %s", ref_path)
            return None

        try:
            spk_id = int(voice_id or self.config.vits.default_voice_id)
        except Exception:
            spk_id = 0

        tts_text = await self.prepare_tts_text(text, language=language, max_text_length=max_text_length)
        if not tts_text:
            self.ctx.logger.warning("TTS 文本语言改写失败，已阻止继续合成")
            return None
        self.ctx.logger.info("TTS 最终提交文本 language=%s text=%s", language, tts_text[:160])

        payload = {
            "text": tts_text,
            "speaker_id": spk_id,
            "text_lang": language,
            "prompt_lang": language,
            "ref_audio_path": ref_path,
            "speed": 1.0,
            "volume": 1.0,
        }

        last_error = None
        for attempt in range(1, retry_count + 1):
            for api_index, api_url in enumerate(api_urls):
                try:
                    self.ctx.logger.info("TTS 请求开始 attempt=%s/%s, url=%s", attempt, retry_count, api_url)
                    async with self._session.post(api_url, json=payload) as resp:
                        content_type = resp.headers.get("Content-Type", "")
                        content = await resp.read()

                        if resp.status != 200:
                            err_text = content.decode("utf-8", errors="ignore")
                            last_error = f"HTTP {resp.status}: {err_text[:500]}"
                            self.ctx.logger.warning("TTS API 返回错误: %s", last_error)
                            if resp.status == 404 and api_index < len(api_urls) - 1:
                                self.ctx.logger.info("TTS API 路径 404，尝试备用地址: %s", api_urls[api_index + 1])
                                continue
                            await asyncio.sleep(0.5)
                            continue

                        lowered = content_type.lower()
                        if "application/json" in lowered or "text/" in lowered:
                            err_text = content.decode("utf-8", errors="ignore")
                            last_error = f"API 返回的不是音频: content_type={content_type}, body={err_text[:500]}"
                            self.ctx.logger.warning(last_error)
                            await asyncio.sleep(0.5)
                            continue

                        if len(content) <= 1000:
                            err_text = content.decode("utf-8", errors="ignore")
                            last_error = f"音频内容过小: {len(content)} bytes, body={err_text[:500]}"
                            self.ctx.logger.warning(last_error)
                            await asyncio.sleep(0.5)
                            continue

                        filename = f"vits_{uuid.uuid4().hex[:8]}.{self.config.vits.audio_format or 'wav'}"
                        filepath = os.path.join(self._cache_dir, filename)
                        async with aiofiles.open(filepath, "wb") as f:
                            await f.write(content)

                        if os.path.getsize(filepath) > 1000:
                            self.ctx.logger.info("TTS 合成成功: %s", filepath)
                            return filepath

                        last_error = f"写入后的音频文件过小: {filepath}"
                        self.ctx.logger.warning(last_error)

                except asyncio.TimeoutError:
                    last_error = "TTS 请求超时"
                    self.ctx.logger.error(last_error)
                    await asyncio.sleep(0.5)
                except Exception as exc:
                    last_error = repr(exc)
                    self.ctx.logger.error("TTS 合成出错: %s", last_error)
                    await asyncio.sleep(0.5)

        self.ctx.logger.error("TTS 合成失败，最后错误: %s", last_error)
        return None

    @staticmethod
    def _candidate_api_urls(api_url: str) -> list[str]:
        raw = (api_url or "").strip()
        if not raw:
            return []

        urls = [raw]
        parsed = urlsplit(raw)
        path = parsed.path or "/"
        if parsed.scheme and parsed.netloc and path.rstrip("/") in {"", "/"}:
            tts_url = urlunsplit((parsed.scheme, parsed.netloc, "/tts", parsed.query, parsed.fragment))
            if tts_url not in urls:
                urls.append(tts_url)
        return urls

    async def prepare_tts_text(self, text: str, language: str, max_text_length: int) -> Optional[str]:
        text = (text or "").strip()
        if not text:
            return ""

        target_code, target_name = self._normalize_language(language)
        if not self.config.vits.auto_language_rewrite or target_code in {"", "auto"}:
            return text[:max_text_length]

        prompt = (
            "你是 TTS 朗读文本本地化器。请把原文改写为自然、口语、适合语音合成朗读的"
            f"{target_name}。\n"
            "要求：\n"
            "1. 只输出最终要交给 TTS 的文本，不要解释，不要引号，不要 Markdown。\n"
            "2. 保留原文含义、角色口吻、情绪、称呼和语气，不要添加新信息。\n"
            "3. 如果原文已经是目标语言，只做轻微口语化润色。\n"
            "4. 如果目标语言是日语，必须输出标准自然日语，不要把中文按日语读音硬转写。\n"
            "5. 数字、符号、缩写改成适合朗读的表达。\n\n"
            f"目标语言代码：{target_code}\n"
            f"目标语言：{target_name}\n"
            f"原文：{text}"
        )

        try:
            result = await self.ctx.llm.generate(
                prompt,
                model=self.config.vits.language_rewrite_model,
                temperature=0.2,
                max_tokens=max(128, min(1024, max_text_length * 2)),
            )
        except Exception as exc:
            self.ctx.logger.warning("TTS 语言改写失败: %s", exc)
            if self.config.vits.block_on_language_rewrite_failure:
                return None
            return text[:max_text_length]

        rewritten = ""
        if isinstance(result, dict):
            rewritten = str(result.get("response") or "").strip()
            if not result.get("success", True):
                self.ctx.logger.warning("TTS 语言改写返回失败: %s", result.get("error") or rewritten)
                if self.config.vits.block_on_language_rewrite_failure:
                    return None
                return text[:max_text_length]

        rewritten = self._clean_llm_text(rewritten)
        if not rewritten:
            self.ctx.logger.warning("TTS 语言改写结果为空")
            if self.config.vits.block_on_language_rewrite_failure:
                return None
            return text[:max_text_length]

        if rewritten != text:
            self.ctx.logger.info("TTS 文本已按 %s 改写: %s", target_code, rewritten[:120])
        return rewritten[:max_text_length]

    @staticmethod
    def _clean_llm_text(text: str) -> str:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned.strip().strip('"').strip("'").strip("「」『』“”‘’").strip()

    @staticmethod
    def _normalize_language(language: str) -> tuple[str, str]:
        code = (language or "").strip().lower().replace("_", "-")
        aliases = {
            "jp": "ja",
            "jpn": "ja",
            "japanese": "ja",
            "cn": "zh",
            "chinese": "zh",
            "zh-cn": "zh",
            "zh-hans": "zh",
            "en-us": "en",
            "en-gb": "en",
            "english": "en",
        }
        code = aliases.get(code, code)
        names = {
            "ja": "日语",
            "zh": "简体中文",
            "en": "英语",
            "ko": "韩语",
            "fr": "法语",
            "de": "德语",
            "es": "西班牙语",
            "ru": "俄语",
        }
        return code, names.get(code, code or "配置指定语言")

    async def clean_cache_task(self, force: bool = False) -> None:
        expire_seconds = int(self.config.cache.expire_minutes) * 60
        max_size_bytes = int(self.config.cache.max_size_mb) * 1024 * 1024
        now = time.time()

        try:
            files = []
            for name in os.listdir(self._cache_dir):
                path = os.path.join(self._cache_dir, name)
                if not os.path.isfile(path):
                    continue
                try:
                    stat = os.stat(path)
                    files.append((path, stat.st_mtime, stat.st_size))
                except FileNotFoundError:
                    continue

            if force:
                for path, _, _ in files:
                    try:
                        os.remove(path)
                    except FileNotFoundError:
                        pass
                self.ctx.logger.info("TTS 缓存已强制清理")
                return

            alive_files = []
            for path, mtime, size in files:
                if now - mtime > expire_seconds:
                    try:
                        os.remove(path)
                        self.ctx.logger.info("删除过期 TTS 缓存: %s", path)
                    except FileNotFoundError:
                        pass
                else:
                    alive_files.append((path, mtime, size))

            total_size = sum(size for _, _, size in alive_files)
            if total_size <= max_size_bytes:
                return

            alive_files.sort(key=lambda item: item[1])
            for path, _, size in alive_files:
                if total_size <= max_size_bytes:
                    break
                try:
                    os.remove(path)
                    total_size -= size
                    self.ctx.logger.info("删除超额 TTS 缓存: %s", path)
                except FileNotFoundError:
                    pass

        except Exception as exc:
            self.ctx.logger.error("TTS 缓存清理失败: %s", exc)


def create_plugin() -> GPTSoVITSV2TTSPlugin:
    return GPTSoVITSV2TTSPlugin()
