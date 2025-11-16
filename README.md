# _🎤 VITS TTS 插件说明文档_

## 一、📢 _插件介绍_

_GPT-soVITS-V2 TTS 插件是一款基于 Maibot 框架的文本转语音插件，通过调用本地API实现TTS功能，支持手动命令触发、自动 TTS 模式和两种核心功能。该插件作为前端交互入口，负责接收用户指令并将文本发送给后端的 GPT-SoVITS-V2 服务进行语音合成，最终将合成结果返回至聊天平台。_

### _核心特性_：

#### 🎯 多触发方式：支持手动命令（/vits）、自动模式（/vitsmode）；

#### 🔗 高兼容性：适配 Maibot 框架，支持 QQ 等主流聊天平台；

#### 🛡️ 鲁棒性设计：包含配置验证、API 重试机制，合成失败时自动降级为文本发送；

#### ⚙️ 灵活配置：支持自定义 API 地址、参考音频路径、默认音色 ID、文本长度限制等参数。
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

action_enabled = true  # 是否启用关键词触发功能（true/false）

command_enabled = true  # 是否启用手动命令功能（true/false）

mode_command_enabled = true  # 是否启用自动模式切换命令（true/false）

[vits]
#GPT-SoVITS-V2 API 服务地址。请确保与你运行“接口.bat”后显示的地址一致。

api_url = "http://localhost:9880/"

#参考音频绝对路径（必需，用于音色匹配）。

#该音频文件应与你在 GPT-SoVITS-V2 中使用的参考音频一致。

ref_audio_path = "D:/GPT-SoVITS-v2/参考音频/我的声音.wav"

#默认音色 ID（需根据你加载的 VITS 模型配置填写）。

#如何查看音色ID？请参考本文档“五、常见问题”第3点。

default_voice_id = "0"

#默认语言（zh/en/jp 等，需与模型支持和 GPT-SoVITS-V2 API 期望的格式一致）

language = "zh"

#API 请求超时时间（秒）

timeout = 120

#单次合成最大文本长度（避免超长文本导致失败）

max_text_length = 500

#API 调用失败重试次数

retry_count = 2
```

## 关键配置说明：
### 🌐 api_url：指向您已启动的 GPT-SoVITS-V2 API 服务地址。默认值为 http://localhost:9880/ 如果您修改了 ***接口.bat*** 中的端口，请同步更新此处。
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
## 2. 🔄 自动 TTS 模式
#### 开启自动模式后，插件会自动将所有文本回复转为语音发送，无需手动触发。
### 命令格式：
### 🟢 开启自动模式：
```plaintext
/vitsmode on
```
### 🔴 关闭自动模式：

```plaintext
/vitsmode off
```
_示例：
发送 /vitsmode on，开启自动模式；
后续发送的所有文本消息（如 “你干嘛哈哈哎哟”）会自动转为语音发送；
发送 /vitsmode off，关闭自动模式，恢复文本发送。_

# 六、❓ 常见问题
## 1. 🚫 插件加载失败 / 无响应
_检查 config.toml 中 enabled 参数是否为 true；
确认 Maibot 框架版本兼容（建议使用最新版）；
查看 Maibot 日志（logs/），排查依赖库缺失或配置错误。_
## 2. ❌ 语音合成失败 / 返回错误（如 “API 调用失败”）
_首要检查：确保 GPT-SoVITS-V2 的 接口.bat 已成功运行，且控制台没有报错。
检查 api_url 是否正确，可尝试在浏览器中访问 http://localhost:9880/docs 看是否能打开 API 文档页面。
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
## 4. ⚠️ 自动模式不生效
_确认已发送 /vitsmode on 开启自动模式；
检查 config.toml 中 mode_command_enabled 参数是否为 true；
确保发送的消息为纯文本（不含图片、表情等非文本内容）。_
# 七、📜 版本更新记录
## v1.8.15 🐛（最新版）
_修复自动模式下特殊符号（如emoji、特殊标点）导致合成失败的问题；
新增文本预处理过滤功能，自动清理无效字符，提高合成稳定性。_

## v1.8.14 🚀
_统一插件实例获取方式，修复 get_plugin 方法不存在的问题；
优化配置验证逻辑，添加参考音频路径有效性检查；
增强日志输出，方便排查合成失败原因。_

## v1.8.13 🔧
_修复 VitsTTSAction 组件无法获取插件实例的 bug；
新增插件实例空值判断，避免运行时崩溃。_

## v1.8.12 🐛
_修复 VitsTTSCommand 组件 get_plugin 方法报错问题；
优化自动模式下的文本拦截逻辑，提高合成成功率。_
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
### GitHub 仓库：[<a href="[https://github.com/Shiroha135/GPT-SoVITS-v2-TTS-Plugin" target="_blank" style="color: #4183c4;">点我进入</a>]
### QQ:751732347
