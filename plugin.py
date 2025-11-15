"""
VITS TTS 插件

基于本地 GPT-SoVITS-V2 API 的文本转语音插件，支持多种语言、手动命令/自动模式。
解决点：统一插件实例获取方式，彻底解决 'get_plugin' 不存在的问题。
"""

from typing import List, Tuple, Type, Optional
import aiohttp
import asyncio
import tempfile
import uuid
import os
from src.common.logger import get_logger
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.apis.plugin_register_api import register_plugin
from src.plugin_system.base.base_action import BaseAction, ActionActivationType
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ComponentInfo
from src.plugin_system.base.config_types import ConfigField

logger = get_logger("vits_tts_plugin")


# ===== 共享工具类：VITS API 调用封装 =====
class VitsAPIClient:
    """VITS API客户端，统一处理语音合成请求"""

    @staticmethod
    async def call_vits_api(api_url: str, text: str, voice_id: str, language: str, ref_audio_path: str, timeout: int) -> \
    Optional[str]:
        """调用 GPT-SoVITS-V2 API 生成语音"""
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
            logger.debug(f"VITS API 请求参数：{payload}")

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.post(api_url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"VITS API 失败（状态码：{response.status}），错误信息：{error_text}")
                        return None

                    content_type = response.headers.get("content-type", "").lower()
                    if "audio" not in content_type:
                        logger.error(f"VITS API 响应格式错误（非音频）：{content_type}")
                        return None

                    # 生成临时音频文件
                    temp_dir = tempfile.gettempdir()
                    audio_filename = f"gpt_sovits_tts_{uuid.uuid4().hex[:8]}.wav"
                    audio_path = os.path.join(temp_dir, audio_filename)

                    with open(audio_path, "wb") as f:
                        f.write(await response.read())

                    # 验证音频有效性（避免空文件）
                    if os.path.getsize(audio_path) < 1024:
                        os.remove(audio_path)
                        logger.error(f"生成的音频文件无效（体积过小：{os.path.getsize(audio_path)} 字节）")
                        return None

                    logger.info(f"VITS 语音合成成功，音频路径：{audio_path}")
                    return audio_path

        except asyncio.TimeoutError:
            logger.error(f"VITS API 请求超时（超时时间：{timeout} 秒）")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"VITS API 网络错误：{str(e)}")
            return None
        except Exception as e:
            logger.error(f"VITS 语音合成异常：{str(e)}", exc_info=True)
            return None


# ===== Action组件：关键词触发语音合成 =====
class VitsTTSAction(BaseAction):
    """关键词触发的VITS语音合成动作（如“语音说你好”）"""

    action_name = "vits_tts_action"
    action_description = "通过关键词触发VITS文本转语音"
    activation_type = ActionActivationType.KEYWORD
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    parallel_action = False

    activation_keywords = ["语音", "说话", "朗读", "念出来", "用语音说", "vits", "tts"]
    keyword_case_sensitive = False

    action_parameters = {
        "text": "待合成文本（必需）",
        "voice_id": "音色ID（可选，默认0）",
        "ref_audio_path": "参考音频路径（可选，默认读取配置）"
    }
    action_require = ["用户明确要求语音回复时触发"]
    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        """执行动作：合成并发送语音"""
        try:
            text = self.action_data.get("text", "").strip()
            voice_id = self.action_data.get("voice_id", "")
            if not text:
                await self.send_text("❌ 动作执行失败：缺少待合成文本")
                return False, "缺少文本参数"

            # 核心修复：统一使用插件类的 instance 属性获取实例
            plugin = VitsTTSPlugin.instance
            if plugin is None:
                await self.send_text("❌ 动作执行失败：VITS 插件未加载")
                return False, "插件实例未找到"

            api_url = plugin.get_config("vits.api_url", "http://localhost:9880/")
            ref_audio_path = plugin.get_config("vits.ref_audio_path", "")
            default_voice_id = plugin.get_config("vits.default_voice_id", "0")
            timeout = plugin.get_config("vits.timeout", 120)
            max_text_len = plugin.get_config("vits.max_text_length", 500)

            if not ref_audio_path or not os.path.exists(ref_audio_path):
                await self.send_text("❌ 动作执行失败：参考音频路径未配置或文件不存在")
                return False, "参考音频无效"
            if len(text) > max_text_len:
                text = text[:max_text_len] + "..."
                logger.warning(f"文本过长，已截断（原长度：{len(text)}，限制：{max_text_len}）")

            voice_id = voice_id if voice_id else default_voice_id
            logger.info(f"Action触发VITS合成：文本={text[:30]}..., 音色ID={voice_id}")

            audio_path = await VitsAPIClient.call_vits_api(
                api_url=api_url,
                text=text,
                voice_id=voice_id,
                language=plugin.get_config("vits.language", "zh"),
                ref_audio_path=ref_audio_path,
                timeout=timeout
            )

            if audio_path:
                await self.send_custom(message_type="voiceurl", content=os.path.abspath(audio_path))
                return True, f"语音合成成功"
            else:
                await self.send_text("❌ 动作执行失败：语音合成请求失败")
                return False, "API调用失败"

        except Exception as e:
            logger.error(f"VitsTTSAction 执行异常：{str(e)}", exc_info=True)
            await self.send_text(f"❌ 动作执行出错：{str(e)}")
            return False, f"执行异常：{str(e)}"


# ===== Command组件1：手动触发语音合成（/vits）=====
class VitsTTSCommand(BaseCommand):
    """手动命令触发VITS合成（格式：/vits 文本 [音色ID]）"""

    command_name = "vits_tts_command"
    command_description = "手动触发VITS文本转语音"
    command_pattern = r"^/vits\s+(?P<text>.+?)(?:\s+(?P<voice_id>\d+))?$"
    command_help = "用法：/vits <待合成文本> [音色ID]\n示例：/vits 你好世界 0\n说明：音色ID默认0，需先配置参考音频路径"
    command_examples = ["/vits 今天天气不错", "/vits こんにちは 1"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行命令：解析参数并合成语音"""
        try:
            text = self.matched_groups.get("text", "").strip()
            voice_id = self.matched_groups.get("voice_id", "")
            if not text:
                await self.send_text(f"❌ 命令参数错误！\n{self.command_help}")
                return False, "缺少文本参数", True

            # 核心修复：统一使用插件类的 instance 属性获取实例
            plugin = VitsTTSPlugin.instance
            if plugin is None:
                await self.send_text("❌ 命令执行失败：VITS 插件未加载")
                return False, "插件实例未找到", True

            api_url = plugin.get_config("vits.api_url", "http://localhost:9880/")
            ref_audio_path = plugin.get_config("vits.ref_audio_path", "")
            default_voice_id = plugin.get_config("vits.default_voice_id", "0")
            timeout = plugin.get_config("vits.timeout", 120)
            max_text_len = plugin.get_config("vits.max_text_length", 500)

            if not ref_audio_path or not os.path.exists(ref_audio_path):
                await self.send_text("❌ 命令执行失败：参考音频路径未配置或文件不存在\n请在config.toml中填写正确路径")
                return False, "参考音频无效", True
            if len(text) > max_text_len:
                text = text[:max_text_len] + "..."
                await self.send_text(f"⚠️  文本过长（限制{max_text_len}字符），已自动截断")

            voice_id = voice_id if voice_id else default_voice_id
            logger.info(f"Command触发VITS合成：文本={text[:30]}..., 音色ID={voice_id}")

            audio_path = await VitsAPIClient.call_vits_api(
                api_url=api_url,
                text=text,
                voice_id=voice_id,
                language=plugin.get_config("vits.language", "zh"),
                ref_audio_path=ref_audio_path,
                timeout=timeout
            )

            if audio_path:
                await self.send_custom(message_type="voiceurl", content=os.path.abspath(audio_path))
                return True, f"语音合成成功", True
            else:
                await self.send_text("❌ 命令执行失败：语音合成请求失败\n请检查API服务或参考音频路径")
                return False, "API调用失败", True

        except Exception as e:
            logger.error(f"VitsTTSCommand 执行异常：{str(e)}", exc_info=True)
            await self.send_text(f"❌ 命令执行出错：{str(e)}")
            return False, f"执行异常：{str(e)}", True


# ===== Command组件2：自动TTS模式切换（/vitsmode）=====
class VitsModeCommand(BaseCommand):
    """切换全局自动TTS模式（/vitsmode on/off）"""

    command_name = "vits_mode_command"
    command_description = "开启/关闭全局自动TTS（文本自动转语音）"
    command_pattern = r"^/vitsmode\s*(?P<mode>on|off)\s*$"
    command_help = "用法：\n/vitsmode on - 开启自动TTS（所有文本回复转语音）\n/vitsmode off - 关闭自动TTS（恢复文本回复）"
    command_examples = ["/vitsmode on", "/vitsmode off"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, str, bool]:
        """执行命令：切换自动TTS状态"""
        try:
            mode = self.matched_groups.get("mode")
            if not mode:
                await self.send_text(f"❌ 无效命令！\n{self.command_help}")
                return False, "无效模式参数", True

            # 同样使用 instance 属性获取实例
            plugin_instance = VitsTTSPlugin.instance
            if not plugin_instance:
                await self.send_text("❌ 切换失败：VITS 插件未加载")
                return False, "插件实例缺失", True

            mode = mode.lower()
            if mode == "on":
                plugin_instance.set_auto_tts_mode(True)
                await self.send_text("✅ 全局自动TTS模式已开启！\n后续所有文本回复将自动转为语音发送")
                return True, "自动TTS开启成功", True
            elif mode == "off":
                plugin_instance.set_auto_tts_mode(False)
                await self.send_text("✅ 全局自动TTS模式已关闭！\n后续回复恢复为文本形式")
                return True, "自动TTS关闭成功", True
            else:
                await self.send_text(f"❌ 无效参数！仅支持：\n/vitsmode on 或 /vitsmode off")
                return False, "无效模式参数", True

        except Exception as e:
            logger.error(f"VitsModeCommand 执行异常：{str(e)}", exc_info=True)
            await self.send_text(f"❌ 切换自动TTS失败：{str(e)}")
            return False, f"执行异常：{str(e)}", True


# ===== 核心插件类：管理配置、状态和组件 =====
@register_plugin
class VitsTTSPlugin(BasePlugin):
    """VITS TTS插件主类（核心：自动TTS逻辑+组件注册）"""

    plugin_name = "vits_tts_plugin"
    plugin_description = "基于GPT-SoVITS-V2的文本转语音插件，支持手动命令/自动模式/关键词动作"
    plugin_version = "1.8.14"
    plugin_author = "Augment Agent"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ["aiohttp>=3.8.0"]

    priority = 1

    # 类属性：用于存储插件实例，供所有组件访问
    instance = None

    config_section_descriptions = {
        "plugin": "插件基础开关",
        "components": "Action/Command组件启用控制",
        "vits": "GPT-SoVITS-V2 API核心配置"
    }
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件")
        },
        "components": {
            "action_enabled": ConfigField(type=bool, default=True, description="是否启用关键词Action组件"),
            "command_enabled": ConfigField(type=bool, default=True, description="是否启用手动Command组件（/vits）"),
            "mode_command_enabled": ConfigField(type=bool, default=True,
                                                description="是否启用自动模式Command组件（/vitsmode）")
        },
        "vits": {
            "api_url": ConfigField(
                type=str,
                default="http://localhost:9880/",
                description="GPT-SoVITS-V2 API地址"
            ),
            "default_voice_id": ConfigField(type=str, default="0", description="默认音色ID"),
            "language": ConfigField(type=str, default="zh", description="默认语言"),
            "ref_audio_path": ConfigField(
                type=str,
                default="",
                description="参考音频绝对路径（必需！）"
            ),
            "timeout": ConfigField(type=int, default=120, description="API请求超时时间"),
            "max_text_length": ConfigField(type=int, default=500, description="单次合成最大文本长度"),
            "retry_count": ConfigField(type=int, default=2, description="API调用失败重试次数")
        }
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._auto_tts_enabled = False
        # 在插件初始化时，将实例保存到类属性中
        VitsTTSPlugin.instance = self

    def set_auto_tts_mode(self, enabled: bool):
        self._auto_tts_enabled = enabled
        logger.info(f"全局自动TTS模式状态更新：{'开启' if enabled else '关闭'}")

    def is_auto_tts_enabled(self) -> bool:
        return self._auto_tts_enabled

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        components = []
        try:
            action_enabled = self.get_config("components.action_enabled", True)
            command_enabled = self.get_config("components.command_enabled", True)
            mode_command_enabled = self.get_config("components.mode_command_enabled", True)
        except AttributeError:
            action_enabled = command_enabled = mode_command_enabled = True

        if action_enabled:
            components.append((VitsTTSAction.get_action_info(), VitsTTSAction))
        if command_enabled:
            components.append((VitsTTSCommand.get_command_info(), VitsTTSCommand))
        if mode_command_enabled:
            components.append((VitsModeCommand.get_command_info(), VitsModeCommand))

        logger.info(f"插件组件注册完成，共注册 {len(components)} 个组件")
        return components

    async def send(self, message_type: str, content: str, *args, **kwargs):
        if message_type == "text":
            logger.info(f"拦截到文本消息发送，触发自动TTS：{content[:50]}...")
            await self.send_text(content, *args, **kwargs)
        else:
            logger.info(f"非文本消息，直接发送：{message_type}")
            await super().send(message_type, content, *args, **kwargs)

    async def send_text(self, text: str, *args, **kwargs):
        logger.info(f"=== 自动TTS处理开始 ===")
        logger.info(f"自动TTS状态：{self._auto_tts_enabled}")
        logger.info(f"待发送文本：{text[:50]}...")

        if not self._auto_tts_enabled:
            logger.info("自动TTS关闭，直接发送文本")
            await super().send_text(text, *args, **kwargs)
            logger.info(f"=== 自动TTS处理结束 ===\n")
            return

        try:
            api_url = self.get_config("vits.api_url", "http://localhost:9880/")
            ref_audio_path = self.get_config("vits.ref_audio_path", "")
            default_voice_id = self.get_config("vits.default_voice_id", "0")
            language = self.get_config("vits.language", "zh")
            timeout = self.get_config("vits.timeout", 120)
            max_text_len = self.get_config("vits.max_text_length", 500)
            retry_count = self.get_config("vits.retry_count", 2)

            if not ref_audio_path or not os.path.exists(ref_audio_path):
                error_msg = f"参考音频路径无效"
                logger.error(f"配置验证失败：{error_msg}")
                await super().send_text(f"⚠️  自动TTS降级为文本（原因：{error_msg}）\n{text}", *args, **kwargs)
                return

            text_to_speak = text.strip()
            if len(text_to_speak) > max_text_len:
                text_to_speak = text_to_speak[:max_text_len] + "..."
                logger.warning(f"文本过长，已截断")

            audio_path = None
            for retry in range(retry_count + 1):
                logger.info(f"语音合成尝试 {retry + 1}/{retry_count + 1}")
                audio_path = await VitsAPIClient.call_vits_api(
                    api_url=api_url,
                    text=text_to_speak,
                    voice_id=default_voice_id,
                    language=language,
                    ref_audio_path=ref_audio_path,
                    timeout=timeout
                )
                if audio_path:
                    break
                if retry < retry_count:
                    await asyncio.sleep(1)

            if audio_path and os.path.exists(audio_path):
                logger.info(f"语音合成成功，发送语音")
                await self.send_custom(message_type="voiceurl", content=os.path.abspath(audio_path))
            else:
                error_msg = "语音合成失败"
                logger.error(f"{error_msg}")
                await super().send_text(f"⚠️  自动TTS降级为文本（原因：{error_msg}）\n{text}", *args, **kwargs)

        except Exception as e:
            error_msg = f"处理异常：{str(e)}"
            logger.error(f"自动TTS未知错误：{error_msg}", exc_info=True)
            await super().send_text(f"⚠️  自动TTS降级为文本（原因：{error_msg}）\n{text}", *args, **kwargs)

        logger.info(f"=== 自动TTS处理结束 ===\n")