"""
GPT-soVITS-V2_TTS_Plugin_Fixed
修改说明：
1. 增加了手动清理缓存命令 /vitsclean
2. 增加了自动TTS概率控制功能
3. 更新插件名称和作者信息
"""

from typing import List, Tuple, Type, Optional, Dict
import aiohttp
import asyncio
import uuid
import os
import threading
import random
from src.common.logger import get_logger

# 提前初始化logger
logger = get_logger("gpt_sovits_v2_tts_plugin_fixed")

from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.apis.plugin_register_api import register_plugin
from src.plugin_system.base.base_action import BaseAction, ActionActivationType
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ComponentInfo
from src.plugin_system.base.config_types import ConfigField


# 全局状态兼容类（无GlobalState模块也能正常运行）
class GlobalState:
    _state = {}
    _lock = threading.Lock()

    @staticmethod
    def set(key, value):
        with GlobalState._lock:
            GlobalState._state[key] = value

    @staticmethod
    def get(key, default=None):
        with GlobalState._lock:
            return GlobalState._state.get(key, default)


# ===== VITS API客户端（极简稳定版）=====
class VitsAPIClient:
    @staticmethod
    async def call_vits_api(api_url: str, text: str, voice_id: str, language: str, ref_audio_path: str, timeout: int) -> \
            Optional[str]:
        try:
            payload = {
                "text": text,
                "speaker_id": int(voice_id),
                "text_lang": language,
                "prompt_lang": language,
                "ref_audio_path": ref_audio_path,
                "speed": 1.0,
                "volume": 1.0
            }
            logger.debug(f"VITS API 请求：{api_url}，参数：{payload}")

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.post(api_url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API失败（{response.status}）：{error_text}")
                        return None

                    if "audio" not in response.headers.get("content-type", "").lower():
                        logger.error(f"响应非音频：{response.headers.get('content-type')}")
                        return None

                    audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_audio_cache")
                    os.makedirs(audio_dir, exist_ok=True)
                    audio_path = os.path.join(audio_dir, f"vits_{uuid.uuid4().hex[:8]}.wav")

                    with open(audio_path, "wb") as f:
                        f.write(await response.read())

                    if os.path.getsize(audio_path) < 1024:
                        os.remove(audio_path)
                        logger.error(f"音频无效（{os.path.getsize(audio_path)}字节）")
                        return None

                    logger.info(f"合成成功：{audio_path}（{os.path.getsize(audio_path)}字节）")
                    return audio_path
        except Exception as e:
            logger.error(f"API调用异常：{str(e)}", exc_info=True)
            return None


# ===== 动作（规划器驱动）=====
class VitsTTSAction(BaseAction):
    action_name = "vits_tts_action"
    action_description = "使用VITS进行语音回复。支持关键词触发或全局TTS模式自动触发。"
    activation_type = ActionActivationType.KEYWORD
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    parallel_action = False
    weight = 300
    activation_keywords = ["语音", "说话", "朗读", "念出来", "用语音说"]
    keyword_case_sensitive = False

    action_parameters = {
        "text": {
            "type": "string",
            "description": "需要转换为语音的文本内容。"
        }
    }

    action_require = [
        "用户的查询中包含'语音'、'说话'等关键词。",
        "OR：全局TTS模式已开启（通过 /vitsmode on 开启）。"
    ]
    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        try:
            text = self.action_data.get("text", "").strip()
            if not text:
                logger.warning("VitsTTSAction 未接收到有效的 'text' 参数。")
                return False, "缺少待合成的文本"

            plugin = GPTSoVITS_V2_TTS_Plugin_Fixed.instance
            if not plugin:
                logger.error("VitsTTSAction：插件实例未找到。")
                return False, "插件未加载"

            # 概率控制判断
            if not plugin.should_trigger_tts():
                logger.info(f"TTS概率控制生效，本次不触发语音合成")
                return False, "概率控制未触发"

            logger.info(f"VitsTTSAction 开始合成语音，文本预览：{text[:50]}...")
            audio_path = await plugin._synthesize_voice(text)

            if audio_path:
                await self.send_custom(message_type="voiceurl", content=os.path.abspath(audio_path))
                asyncio.create_task(plugin._clean_cache())
                return True, "语音合成与发送成功"
            else:
                logger.error("VitsTTSAction：语音合成失败。")
                return False, "语音合成失败"
        except Exception as e:
            logger.error(f"VitsTTSAction 执行异常：{str(e)}", exc_info=True)
            return False, "执行过程中发生错误"


# ===== 手动命令（/vits）=====
class VitsTTSCommand(BaseCommand):
    command_name = "vits_tts_command"
    command_pattern = r"^/vits\s+(?P<text>.+?)(?:\s+(?P<voice_id>\d+))?$"
    command_help = "用法：/vits <文本> [音色ID]\n示例：/vits 你好 0"
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        text = self.matched_groups.get("text", "").strip()
        voice_id = self.matched_groups.get("voice_id", "0")
        if not text:
            await self.send_text(f"❌ 参数错误！\n{self.command_help}")
            return False, "缺少文本", True

        plugin = GPTSoVITS_V2_TTS_Plugin_Fixed.instance
        if not plugin:
            await self.send_text("❌ 插件未加载")
            return False, "插件未加载", True

        audio_path = await plugin._synthesize_voice(text, voice_id)
        if audio_path:
            await self.send_custom(message_type="voiceurl", content=os.path.abspath(audio_path))
            return True, "合成成功", True
        await self.send_text("❌ 合成失败，请检查API和参考音频")
        return False, "合成失败", True


# ===== 模式切换命令（/vitsmode）=====
class VitsModeCommand(BaseCommand):
    command_name = "vits_mode_command"
    command_pattern = r"^/vitsmode\s*(?P<mode>on|off)\s*$"
    command_help = "用法：\n/vitsmode on - 开启自动TTS\n/vitsmode off - 关闭自动TTS"
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        mode = self.matched_groups.get("mode")
        if not mode:
            await self.send_text(f"❌ 无效命令！\n{self.command_help}")
            return False, "无效参数", True

        plugin = GPTSoVITS_V2_TTS_Plugin_Fixed.instance
        if not plugin:
            await self.send_text("❌ 插件未加载")
            return False, "插件未加载", True

        if mode == "on":
            plugin.set_auto_tts_mode(True)
            await self.send_text("✅ 自动TTS已开启！")
            return True, "开启成功", True
        else:
            plugin.set_auto_tts_mode(False)
            await self.send_text("✅ 自动TTS已关闭！")
            return True, "关闭成功", True


# ===== 清理缓存命令（/vitsclean）=====
class VitsCleanCommand(BaseCommand):
    command_name = "vits_clean_command"
    command_pattern = r"^/vitsclean$"
    command_help = "用法：/vitsclean - 手动清理TTS音频缓存"
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        plugin = GPTSoVITS_V2_TTS_Plugin_Fixed.instance
        if not plugin:
            await self.send_text("❌ 插件未加载")
            return False, "插件未加载", True

        try:
            await self.send_text("🔍 开始清理TTS音频缓存...")
            await plugin._clean_cache()
            await self.send_text("✅ TTS音频缓存清理完成")
            return True, "缓存清理成功", True
        except Exception as e:
            logger.error(f"清理缓存异常：{str(e)}", exc_info=True)
            await self.send_text("❌ 清理缓存失败")
            return False, "缓存清理失败", True


# ===== 核心插件类 =====
@register_plugin
class GPTSoVITS_V2_TTS_Plugin_Fixed(BasePlugin):
    plugin_name = "GPT-soVITS-V2_TTS_Plugin_Fixed"
    plugin_description = "GPT-SoVITS-V2 TTS插件（带概率控制和缓存清理功能）"
    plugin_version = "1.9.4"
    plugin_author = "HatsuYukiAya初雪绫"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ["aiohttp>=3.8.0"]
    priority = 300
    instance = None
    _auto_tts_enabled = False
    _state_lock = threading.Lock()
    _audio_cache_dir = ""
    _use_fallback_intercept = False

    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用VITS TTS插件")
        },
        "vits": {
            "api_url": ConfigField(type=str, default="http://localhost:9880/",
                                   description="GPT-SoVITS-V2 API 完整路径"),
            "default_voice_id": ConfigField(type=str, default="0", description="默认音色ID"),
            "language": ConfigField(type=str, default="zh", description="默认合成语言"),
            "ref_audio_path": ConfigField(type=str, default="", description="参考音频绝对路径（必填）"),
            "timeout": ConfigField(type=int, default=60, description="API请求超时时间（秒）"),
            "max_text_length": ConfigField(type=int, default=500, description="单次合成最大文本长度"),
            "retry_count": ConfigField(type=int, default=3, description="API调用失败重试次数"),
            "auto_tts_probability": ConfigField(type=float, default=1.0,
                                                description="自动TTS触发概率（0.0-1.0，1.0为100%）")
        },
        "cache": {
            "expire_minutes": ConfigField(type=int, default=30, description="音频缓存过期时间（分钟）"),
            "max_size_mb": ConfigField(type=int, default=100, description="音频缓存最大大小（MB）")
        }
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        GPTSoVITS_V2_TTS_Plugin_Fixed.instance = self
        self._init_cache_dir()

        # 检查 context 是否可用
        if not hasattr(self, 'context') or self.context is None:
            logger.warning("未检测到全局上下文(context)。将自动启用 '终极拦截' 模式作为降级方案。")
            self._use_fallback_intercept = True
        else:
            logger.info("检测到全局上下文(context)。将使用规划器驱动模式。")
            self._use_fallback_intercept = False

        # 初始同步一次状态
        self.set_auto_tts_mode(False)

        logger.info(f"{self.plugin_name} 初始化完成（作者：{self.plugin_author}）")

    def _init_cache_dir(self):
        self._audio_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_audio_cache")
        os.makedirs(self._audio_cache_dir, exist_ok=True)
        os.chmod(self._audio_cache_dir, 0o755)
        logger.info(f"缓存目录：{self._audio_cache_dir}")

    def set_auto_tts_mode(self, enabled: bool):
        """设置自动TTS模式，并尝试同步到全局上下文"""
        with self._state_lock:
            self._auto_tts_enabled = enabled

        logger.info(f"自动TTS模式：{'开启' if enabled else '关闭'}")

        # 仅当 context 可用时才尝试同步
        if hasattr(self, 'context') and self.context:
            try:
                self.context.set('vits_auto_tts_enabled', enabled)
                logger.debug("TTS状态已成功同步到全局上下文。")
            except Exception as e:
                logger.error(f"同步TTS状态到全局上下文失败：{e}")
                # 如果同步失败，启用降级模式
                if not self._use_fallback_intercept:
                    logger.warning("状态同步失败，自动切换到 '终极拦截' 模式。")
                    self._use_fallback_intercept = True

    def is_auto_tts_enabled(self) -> bool:
        """获取自动TTS状态"""
        with self._state_lock:
            return self._auto_tts_enabled

    def should_trigger_tts(self) -> bool:
        """根据配置的概率判断是否触发TTS"""
        if not self.is_auto_tts_enabled():
            return False

        prob = self.get_config("vits.auto_tts_probability", 1.0)
        # 确保概率在有效范围内
        prob = max(0.0, min(1.0, prob))
        return random.random() <= prob

    async def _synthesize_voice(self, text: str, voice_id: str = None) -> Optional[str]:
        try:
            api_url = self.get_config("vits.api_url", "http://localhost:9880/")
            ref_audio_path = self.get_config("vits.ref_audio_path", "")
            default_voice_id = self.get_config("vits.default_voice_id", "0")
            language = self.get_config("vits.language", "zh")
            timeout = self.get_config("vits.timeout", 60)
            max_len = self.get_config("vits.max_text_length", 500)
            retry_count = self.get_config("vits.retry_count", 3)

            if not ref_audio_path or not os.path.exists(ref_audio_path):
                logger.error("参考音频路径无效或不存在！")
                return None
            text = text.strip()[:max_len] + ("..." if len(text) > max_len else "")
            voice_id = voice_id or default_voice_id

            audio_path = None
            for retry in range(retry_count):
                audio_path = await VitsAPIClient.call_vits_api(
                    api_url=api_url, text=text, voice_id=voice_id,
                    language=language, ref_audio_path=ref_audio_path, timeout=timeout
                )
                if audio_path:
                    break
                logger.warning(f"语音合成失败，正在进行第 {retry + 1}/{retry_count} 次重试...")
                await asyncio.sleep(min(2 ** retry, 10))
            return audio_path
        except Exception as e:
            logger.error(f"合成异常：{str(e)}", exc_info=True)
            return None

    async def send(self, message_type: str, content: str, *args, **kwargs):
        """终极拦截（仅降级模式下生效）"""
        # 如果不是降级模式，或者不是文本消息，直接调用父类方法
        if not self._use_fallback_intercept or message_type != "text" or not (
                isinstance(content, str) and len(content.strip()) > 0):
            await super().send(message_type, content, *args, **kwargs)
            return

        # 降级模式启用，且是文本消息
        logger.info(f"[降级拦截] TTS模式: {self.is_auto_tts_enabled()}")

        if self.is_auto_tts_enabled():
            # 应用概率控制
            if not self.should_trigger_tts():
                logger.info("TTS概率控制生效，本次发送文本")
                await super().send_text(content, *args, **kwargs)
                return

            audio_path = await self._synthesize_voice(content)
            if audio_path:
                logger.info("合成成功，发送语音")
                await super().send("voiceurl", os.path.abspath(audio_path), *args, **kwargs)
                asyncio.create_task(self._clean_cache())
                return

        # TTS关闭或合成失败，发送文本
        logger.info("发送文本")
        await super().send_text(content, *args, **kwargs)

    async def _clean_cache(self):
        try:
            if not os.path.exists(self._audio_cache_dir):
                return
            expire = self.get_config("cache.expire_minutes", 30) * 60
            max_size = self.get_config("cache.max_size_mb", 100) * 1024 * 1024
            now = asyncio.get_event_loop().time()
            files = []
            for filename in os.listdir(self._audio_cache_dir):
                if filename.startswith("vits_"):
                    file_path = os.path.join(self._audio_cache_dir, filename)
                    try:
                        mtime = os.path.getmtime(file_path)
                        size = os.path.getsize(file_path)
                        files.append((file_path, mtime, size))
                    except OSError as e:
                        logger.warning(f"访问缓存文件 {file_path} 时出错：{e}")

            # 删除过期文件
            for file_path, mtime, _ in files:
                if now - mtime > expire:
                    try:
                        os.remove(file_path)
                        logger.debug(f"已删除过期缓存：{os.path.basename(file_path)}")
                    except OSError as e:
                        logger.warning(f"删除过期缓存 {file_path} 时出错：{e}")

            # 控制缓存大小
            total_size = sum(size for _, _, size in files)
            if total_size > max_size:
                files.sort(key=lambda x: x[1])  # 按修改时间排序， oldest first
                for file_path, _, size in files:
                    if total_size <= max_size:
                        break
                    try:
                        os.remove(file_path)
                        total_size -= size
                        logger.debug(f"为控制缓存大小，已删除旧缓存：{os.path.basename(file_path)}")
                    except OSError as e:
                        logger.warning(f"删除旧缓存 {file_path} 时出错：{e}")
        except Exception as e:
            logger.error(f"缓存清理异常：{str(e)}", exc_info=True)

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        components = []
        try:
            if self.get_config("plugin.enabled", True):
                components.append((VitsTTSAction.get_action_info(), VitsTTSAction))
                components.append((VitsTTSCommand.get_command_info(), VitsTTSCommand))
                components.append((VitsModeCommand.get_command_info(), VitsModeCommand))
                components.append((VitsCleanCommand.get_command_info(), VitsCleanCommand))
        except Exception:
            components = [(VitsTTSAction.get_action_info(), VitsTTSAction),
                          (VitsTTSCommand.get_command_info(), VitsTTSCommand),
                          (VitsModeCommand.get_command_info(), VitsModeCommand),
                          (VitsCleanCommand.get_command_info(), VitsCleanCommand)]
        logger.info(f"注册组件：{len(components)}个")
        return components

    async def on_unload(self):
        logger.info(f"{self.plugin_name} 插件卸载，开始清理缓存...")
        try:
            if os.path.exists(self._audio_cache_dir):
                for filename in os.listdir(self._audio_cache_dir):
                    if filename.startswith("vits_"):
                        file_path = os.path.join(self._audio_cache_dir, filename)
                        try:
                            os.remove(file_path)
                        except OSError as e:
                            logger.warning(f"删除缓存文件 {file_path} 时出错：{e}")
                os.rmdir(self._audio_cache_dir)
        except Exception as e:
            logger.error(f"卸载时清理缓存异常：{e}")
        GPTSoVITS_V2_TTS_Plugin_Fixed.instance = None
        logger.info(f"{self.plugin_name} 插件卸载完成")