# IntDog 安装与首次使用

[English](onboarding-and-installation.md)

本指南面向桌面安装版用户。IntDog 本地保存行业数据，但安装包不包含模型账号、API 额度或第三方付费数据。当前为未签名测试版；请只从项目 Release 下载，并核对随附的 SHA-256。

## 支持平台

| 平台 | 当前架构 | 安装包 |
| --- | --- | --- |
| Windows 10/11 | x64 | `IntDog-<version>-windows-x64.exe` |
| macOS | Apple Silicon arm64 | `IntDog-<version>-macos-arm64.dmg` |
| Linux | x64 | `IntDog-<version>-linux-x86_64.AppImage` |

Intel Mac 和其他 CPU 架构不在当前测试范围。三个安装包是独立构建产物，不能互换。

## 安装

### Windows 10/11 x64

1. 下载 Windows `.exe` 和对应 `.sha256`，不要下载 GitHub 自动生成的 Source code。
2. 在 PowerShell 运行：

   ```powershell
   Get-FileHash .\IntDog-<version>-windows-x64.exe -Algorithm SHA256
   ```

3. 摘要一致后运行安装器，再从开始菜单或桌面快捷方式启动。
4. 未签名测试包可能触发 SmartScreen。核对发布来源和摘要后，再自行决定是否继续。

日志位于 `%APPDATA%\intdog-desktop\logs`，本地数据位于 `%APPDATA%\intdog-desktop\data`。

### macOS Apple Silicon

1. 下载 DMG，并运行 `shasum -a 256 IntDog-<version>-macos-arm64.dmg`。
2. 打开 DMG，把 IntDog 拖入 Applications。
3. 未签名测试包可能被 Gatekeeper 阻止。确认摘要后，可在“隐私与安全”中选择是否允许。

日志和数据分别位于 `~/Library/Application Support/intdog-desktop/logs` 与 `~/Library/Application Support/intdog-desktop/data`。

### Linux x64

```bash
chmod +x IntDog-<version>-linux-x86_64.AppImage
sha256sum IntDog-<version>-linux-x86_64.AppImage
./IntDog-<version>-linux-x86_64.AppImage
```

日志和数据默认位于 `~/.config/intdog-desktop/logs` 与 `~/.config/intdog-desktop/data`；设置 `XDG_CONFIG_HOME` 后跟随该目录。

## 首次启动

首次启动会准备本地后端和数据目录，然后显示四步向导：环境诊断、研究连接、行业、首轮结果。

### 1. 环境诊断

确认本地运行组件和数据目录可用。这里显示的是 IntDog 自身状态，不代表模型已经连接。

### 2. 选择研究连接

可以选择三种模式：

- **本机 Agent**：Agent CLI 必须安装在与 IntDog 相同的操作系统和用户账户中，并已登录。IntDog 先检查 `PATH` 和有限的常见安装目录；失败时可手动选择 CLI 命令文件。它不会接管已经打开的 Agent GUI，也不默认跨 Windows/WSL 连接。
- **API**：选择 Provider，填写精确模型 ID、API Key、可选 HTTPS API Base 和认证方式。`OpenAI` 是 Provider 名称，不是模型 ID。
- **任务包**：无需模型或 Key，只生成可交给兼容 Agent 的任务包，不等于完成研究。

API Key 由桌面主进程通过系统凭据加密能力保存；浏览器界面、日志、URL 和 API 响应不会返回 Key。若系统安全存储不可用，IntDog 会拒绝明文降级。

API 已配置后仍可：

- 编辑模型、API Base 或认证方式；Key 留空会保留同一 Provider 的现有密钥；
- 更换 Provider，但必须填写新 Key；
- 点击“测试 API 连接”执行真实最小调用；
- 清除 API 配置，且不会删除行业数据。

真实探针会核验认证、模型，并在初始化需要时核验联网搜索工具。它可能消耗少量 API 额度。测试成功只能证明本次最小调用成功，不保证后续研究内容质量。

### 3. 创建行业

填写行业显示名称和本地数据文件夹。提交后会直接开始初始化，无需再次确认任务包。相同行业的变更任务按提交顺序排队；其他行业可以独立运行。

### 4. 首轮结果

直接初始化按顺序执行：

1. 信息源发现、可达性检查与来源门槛；
2. 产业链节点、有向边和引用门槛；
3. 实体引用、中国/海外与产业链覆盖门槛；
4. 发布待复核知识草稿。

界面显示固定的三行阶段状态与真实里程碑。等待 Provider 时只显示当前阶段和已用时间，不虚构内部进度。

- `已完成`：三道门槛已通过并发布待复核草稿；模型输出仍不是正式事实。
- `部分完成`：某道门槛未通过；已完成检查点和候选材料保留，下游阶段不会伪装成成功。
- `失败`：Provider、配置、网络或解析失败；任务中心显示脱敏后的具体原因。
- `排队中`：同一行业已有变更任务；可以在启动前取消。
- `任务包已创建`：只是交接文件，尚未执行行业研究。

“恢复并重试”会先重新检查 Provider，并在行业、模型、工作流和输入指纹一致时复用已通过阶段；否则从第一个无效阶段重新开始。

## Agent 连接边界

IntDog 目前可直接执行已通过诊断的 Codex CLI 与 Claude Code；其他已登记 Agent 根据实际适配器使用 ACP、MCP、API 或任务包。完整清单、握手方式和成熟度见[Agent 连接说明](agent-connectivity.zh-CN.md)。

“已检测”“已安装”“已登录”“可直接执行”不是同一状态。选择 ChatGPT GUI 的 `chatgpt.exe` 不能代替 Codex CLI。未知或仅有 GUI 的 Agent 不会被冒充为可调用模型。

## 后台、数据与卸载

后台运行默认关闭。启用前 IntDog 会请求权限；可在系统状态中撤销。撤销只移除系统调度入口，不删除计划、行业数据或凭据。

卸载应用会删除程序和快捷方式，但用户数据默认“卸载保留”。升级兼容版本会继续使用这些数据。要迁移或备份，请复制整个平台数据目录；不要只复制 SQLite 文件。

## 故障排查

- **应用无窗口**：查看平台日志目录下的 `backend.log`。分享前删除个人路径、令牌和 Key。
- **Agent 未找到**：确认安装的是受支持 CLI，在同一系统终端运行其版本和登录命令，再回到 IntDog 重新检测或选择命令文件。
- **401 / authentication**：在同一操作系统和用户账户中登录 Agent，或重新填写 API Key。
- **invalid_model**：从 Provider 控制台复制精确模型 ID；不要填写 Provider 名称。
- **unsupported_tool**：当前模型或端点不支持初始化所需的联网搜索；更换明确支持该工具的模型或 Provider。
- **quota / rate_limit**：检查额度和限流，等待后安全重试。
- **部分完成**：查看未通过检查；这是研究覆盖不足，不是界面格式错误。

本地合成测试不能证明真实付费账号可用。公开测试版仍需分别通过 Windows、macOS 和 Linux 原生安装、首次启动、关闭与重开门槛。
