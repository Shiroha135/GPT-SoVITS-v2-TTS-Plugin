# _🎤 VITS TTS 插件说明文档_

## 一、📢 _插件介绍_

_GPT-soVITS-V2 TTS 插件是一款基于 Maibot 新版插件运行时的文本转语音插件，通过调用本地 API 实现 TTS 功能，支持 /vits 手动命令、显式关键词直触发和 Action 工具调用。该插件作为前端交互入口，负责接收用户指令并将文本发送给后端的 GPT-SoVITS-V2 服务进行语音合成，最终将合成结果返回至聊天平台。_

### _核心特性_：

#### 🎯 多触发方式：支持手动命令（/vits）、显式关键词触发、Action 工具调用；

#### 🔗 高兼容性：适配 Maibot 框架，支持 QQ 等主流聊天平台；

#### 🛡️ 鲁棒性设计：包含配置验证、API 重试机制、根路径与 /tts API 路径自动兼容；

#### ⚙️ 灵活配置：支持自定义 API 地址、参考音频路径、默认音色 ID、目标语言、关键词触发短语等参数。
# 二、🔧 前置准备：部署 GPT-SoVITS-V2 服务

## ⚠️ _重要：本插件仅为前端交互接口，不包含语音合成核心逻辑。您需要自行部署 GPT-SoVITS-V2 服务并启动其 API 功能。_

### 📥 下载 GPT-SoVITS-V2：

_<a href="https://github.com/v3ucn/GPT-SoVITS-V2" target="_blank" style="color: #4183c4; text-decoration: none;">前往 GPT-SoVITS-V2 GitHub 仓库（或您使用的其他 fork 版本）。</a>_

_按照其官方 README 指南，下载项目文件并完成环境配置（如安装 Python、PyTorch 及其他依赖库）。_

### 📁 准备模型文件：

_下载或训练好您需要的 VITS 模型（通常是 .pth 文件）和配置文件（config.json）。
将模型文件放置在 GPT-SoVITS-V2 项目指定的模型目录下（通常是 weights/ 或 models/）。_

### 🚀 启动 API 服务：

_进入 GPT-SoVITS-V2 项目的根目录。
运行 接口.bat 文件（Windows）或相应的启动脚本（Linux/macOS）。
启动成功后，控制台会显示类似 Running on local URL: http://127.0.0.1:9880 的信息，表示 API 服务已在本地 9880 端口运行。_

# 三、📥 插件安装步骤

## 1. 📋 环境依赖

### _Python 3.8+、Maibot 框架（已安装并配置）、依赖库：aiohttp（用于异步请求 GPT-SoVITS-V2 API）_

## 2. 安装方法

### 📂 _将插件文件夹 vits_tts_plugin 放入 Maibot 插件目录（plugins/）；_

### 📦 _安装依赖库：_


```bash
pip install aiohttp
```

### 🔄 _重启 Maibot 服务，插件自动加载。_

# 四、⚙️ 配置说明

## _插件配置文件为 config.toml，位于插件目录下，需根据您的 GPT-SoVITS-V2 服务和需求修改以下参数：_

```toml
[plugin]

enabled = true  # 是否启用插件（true/false）

[components]

action_enabled = true  # 是否启用 Action 和显式关键词触发

command_enabled = true  # 是否启用 /vits 命令

mode_command_enabled = true  # 是否启用 /vitsmode 提示命令

[vits]
# GPT-SoVITS-V2 API 服务地址。
# 可填 http://localhost:9880/；如果根路径返回 404，插件会自动尝试 http://localhost:9880/tts。
# 如果你的 GPT-SoVITS API 明确要求 /tts，也可以直接填 http://localhost:9880/tts。

api_url = "http://localhost:9880/"

#参考音频绝对路径（必需，用于音色匹配）。

#该音频文件应与你在 GPT-SoVITS-V2 中使用的参考音频一致。

ref_audio_path = "D:/GPT-SoVITS-v2/参考音频/我的声音.wav"

#默认音色 ID（需根据你加载的 VITS 模型配置填写）。

#如何查看音色ID？请参考本文档“五、常见问题”第3点。

default_voice_id = "0"

#默认语言（zh/en/ja 等，需与模型支持和 GPT-SoVITS-V2 API 期望的格式一致）

language = "ja"

#API 请求超时时间（秒）

timeout = 120

#单次合成最大文本长度（避免超长文本导致失败）

max_text_length = 500

#API 调用失败重试次数

retry_count = 2

# 发送到 TTS 前，是否按 language 自动改写合成文本。
# 例如 language = "ja" 时，会先把中文请求改写成自然日语，再提交给 GPT-SoVITS。
auto_language_rewrite = true

# 语言改写使用的模型任务名。留空可能被 Maibot 路由到错误任务，建议使用 utils 或你的可用文本模型任务。
language_rewrite_model = "utils"

# 语言改写失败时是否阻止继续合成，避免把中文硬塞给日语模型导致奇怪发音。
block_on_language_rewrite_failure = true

# 是否启用显式关键词直触发。
keyword_trigger_enabled = true

# 逗号分隔；命中这些短语会直接触发语音，不再依赖 Planner 主动调用 Action。
keyword_trigger_phrases = "再发一句语音,再来一句语音,发语音,发一句语音,来句语音,来一句语音,再说一句,再说句话,说句话,说一句,念一句,朗读,念出来,用语音说,语音说"

# 只有触发词、没有指定朗读内容时使用的默认文本。
keyword_default_text = "行吧，就再说一句。测试到这里差不多了。"
```

## 关键配置说明：
### 🌐 api_url：指向您已启动的 GPT-SoVITS-V2 API 服务地址。默认值为 http://localhost:9880/。不同 GPT-SoVITS 版本的接口路径可能不同：有的接受根路径 /，有的必须使用 /tts。本插件会在根路径 404 时自动尝试 /tts，也可直接配置为 http://localhost:9880/tts。
### 🎧 ref_audio_path：参考音频的绝对路径（需为 WAV 格式）。这个文件用于告诉 GPT-SoVITS-V2 使用哪种音色进行合成，必须填写且应与后端服务中的设置逻辑相符。
### 🔊 default_voice_id：默认音色 ID。如果您的模型支持多说话人，需要在此指定一个默认的 ID。
### 📝 max_text_length：单次合成的最大文本长度（超过该长度会自动截断，建议设置为 500-1000 字）。
# 五、🎮 使用方法
## 1. 🖋️ 手动命令触发
_通过发送 /vits 命令手动触发文本转语音，支持自定义音色 ID。_
### 命令格式：
```plaintext
/vits <待合成文本> [音色ID]
```
_示例：
基础用法（使用默认音色）：_
```plaintext
/vits 你好，欢迎使用 VITS TTS 插件！
```
_自定义音色（指定音色 ID 为 1）：_
```plaintext
/vits 这是自定义音色的语音 1
```
## 2. 🎯 显式关键词触发
_发送含有配置中关键词的消息时，插件会在进入 Planner 前直接触发语音。_

_示例：_
```plaintext
再发一句语音
再说一句嘛
用语音说你好
请朗读这段话：欢迎使用 GPT-SoVITS TTS 插件
```

_如果只有触发词、没有指定朗读内容，会使用 keyword_default_text。句尾语气词如“嘛、啊、呀、呢”等不会被误当成合成文本。_

## 3. 🔄 旧版自动 TTS 模式
#### 新版 Maibot 插件运行时暂不支持旧版全局自动 TTS 拦截，/vitsmode 目前只会返回提示信息。
### 命令格式：
```plaintext
/vitsmode on
```
```plaintext
/vitsmode off
```

# 六、❓ 常见问题
## 1. 🚫 插件加载失败 / 无响应
_检查 config.toml 中 enabled 参数是否为 true；
确认 Maibot 框架版本兼容（建议使用最新版）；
查看 Maibot 日志（logs/），排查依赖库缺失或配置错误。_
## 2. ❌ 语音合成失败 / 返回错误（如 “API 调用失败”）
_首要检查：确保 GPT-SoVITS-V2 的 接口.bat 已成功运行，且控制台没有报错。
检查 api_url 是否正确，可尝试在浏览器中访问 http://localhost:9880/docs 看是否能打开 API 文档页面。
如果日志中出现 HTTP 404 {"detail":"Not Found"}，通常是 API 路径不对。请尝试将 api_url 改为 http://localhost:9880/tts，或使用本插件的新版自动备用路径逻辑。
验证 ref_audio_path 是否为绝对路径，且音频文件存在、格式正确（WAV）。
查看 Maibot 日志和 GPT-SoVITS-V2 的控制台输出，获取更详细的错误信息（如文本过长、模型未找到等）。
调整 timeout 或 max_text_length 参数。_
## 3. 🔍 如何查看音色 ID？
_音色 ID 取决于您在 GPT-SoVITS-V2 中加载的模型。
方法一：查看模型配置文件找到您使用的模型对应的 config.json 文件，在其中搜索 speakers 或 speaker_id_map 等字段。通常会是一个列表或字典，例如：_
```json
"speakers": [
  {"id": 0, "name": "female_calm"},
  {"id": 1, "name": "male_energetic"}
]
```
_其中的数字 0, 1 就是音色 ID。
方法二：查看 GPT-SoVITS-V2 API 文档如果 API 服务已启动，访问 http://localhost:9880/docs 在 tts 相关的接口描述中，可能会有关于 speaker_id 的说明或示例值。_
## 4. ⚠️ 关键词触发不生效
_确认 config.toml 中 action_enabled 和 keyword_trigger_enabled 均为 true；
确认消息中包含 keyword_trigger_phrases 里的显式触发短语；
如果只是讨论“语音插件”这类普通文本，插件会尽量避免误触发。_

## 5. 🌐 language = "ja" 但合成出来不像日语
_确认 auto_language_rewrite = true，language_rewrite_model 指向可用的文本生成模型任务，例如 utils。
如果语言改写失败，日志会显示“TTS 文本语言改写失败，已阻止继续合成”。这时需要检查 Maibot 的模型任务配置，避免被路由到 embedding 模型。_
# 七、📜 版本更新记录
## v3.2.0（最新版）🚀
_适配 Maibot 新版插件运行时；
新增显式关键词直触发，避免 Planner 不调用 TTS Action；
新增按 language 自动改写合成文本，language=ja 时优先提交自然日语；
新增根路径与 /tts API 路径自动兼容，根路径 404 时自动尝试 /tts；
优化“再说一句嘛”等请求解析，避免把句尾语气词当成合成文本。_

## v3.1.0 🔧
_修复新版配置缺少 plugin.config_version 导致加载失败；
升级 manifest v2；
支持 send.custom 发送语音。_

## v1.8.13 及更早版本 🔧
_修复 VitsTTSAction 组件无法获取插件实例的 bug；
新增插件实例空值判断，避免运行时崩溃；
修复 VitsTTSCommand 组件 get_plugin 方法报错问题。_
# 八、⚠️ 注意事项
_本插件必须配合运行中的 GPT-SoVITS-V2 API 服务才能工作。请确保在启动 Maibot 前，已成功运行 接口.bat。_
### 🌐 网络环境：
_Maibot 所在机器需能访问 api_url 所指向的地址（本地部署则无需担心）。_
### 🎧 格式要求：
_参考音频文件需与 GPT-SoVITS-V2 服务期望的格式和内容匹配，否则可能导致合成效果不佳或失败。_
### 📝 长度要求：
_避免频繁发送超长文本，可能导致 API 请求超时或合成失败。_
### ⏱️ 参数要求：
_若使用远程 API 服务，建议配置较短的 timeout 参数，避免等待时间过长。_
### 🚫 注意事项
_本插件仅用于文本转语音功能，请勿用于非法或违规内容的传播，使用时需遵守相关法律法规和平台规定。_
# 九、📜 协议声明
## _本项目遵循 <a href="https://opensource.org/licenses/MIT" target="_blank" style="color: #4183c4;">MIT 许可证</a> 开源_
# 十、📞 联系方式
## 若遇到问题或需要功能扩展，可通过以下方式反馈：
### GitHub 仓库：[待补充]
### QQ:751732347
