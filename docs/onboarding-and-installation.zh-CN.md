# IntDog 安装、首次启动与智能体连接合同

[English](onboarding-and-installation.md)

## 用户结果

面向第一次接触 IntDog 的桌面用户，安装完成后无需阅读源码即可：

1. 看见明确的首次启动向导；
2. 确认本地后端、数据目录和模型 Provider 的真实状态；
3. 选择已检测的本机 Agent、显式 API 或无模型任务包；
4. 创建第一个行业并运行一次可观察的初始化任务；
5. 从任务中心判断成功、失败原因和下一步操作。

安装包只包含 IntDog 桌面壳、Web 工作台和本地 Python sidecar。它不包含 ChatGPT
账号、Codex CLI 登录或 OpenAI API 额度。界面不得把“IntDog 已启动”显示成“智能体已连接”。

## 支持边界

| 平台 | 测试版架构 | 安装产物 | 模型前提 |
| --- | --- | --- | --- |
| Windows 10/11 | x64 | NSIS `.exe` | Codex/Claude CLI、显式 API 或任务包 |
| macOS | Apple Silicon arm64 | `.dmg` | Codex/Claude CLI、显式 API 或任务包 |
| Linux | x64 | `.AppImage` | Codex/Claude CLI、显式 API 或任务包 |

当前测试版未签名。Windows SmartScreen 或 macOS Gatekeeper 可能要求用户手动允许；这不等于
绕过安全检查。Intel Mac 不在当前测试版支持范围内。

## 安装与卸载

### Windows 10/11 x64

1. 从 Windows Pre-release 下载 `IntDog-<version>-windows-x64.exe` 和 `.sha256`，不要下载源码压缩包。
2. 在 PowerShell 执行 `Get-FileHash .\IntDog-<version>-windows-x64.exe -Algorithm SHA256` 核对摘要。
3. 运行 NSIS 安装器，再从开始菜单或桌面快捷方式打开 IntDog。
4. 日志与数据分别位于 `%APPDATA%\intdog-desktop\logs` 和 `%APPDATA%\intdog-desktop\data`；安装目录不保存用户数据库。

### macOS Apple Silicon

1. 下载 `IntDog-<version>-macos-arm64.dmg`，运行 `shasum -a 256 IntDog-<version>-macos-arm64.dmg` 核对摘要。
2. 挂载 DMG，把 IntDog 拖入 Applications。当前 Beta 未签名；确认摘要与发行来源后，才使用 Finder 的“打开”例外。
3. 日志与数据位于 `~/Library/Application Support/intdog-desktop/logs` 和 `~/Library/Application Support/intdog-desktop/data`。

### Linux x64

1. 下载 AppImage，执行 `chmod +x IntDog-<version>-linux-x64.AppImage`。
2. 用 `sha256sum IntDog-<version>-linux-x64.AppImage` 核对摘要后启动。
3. 日志与数据默认位于 `~/.config/intdog-desktop/logs` 和 `~/.config/intdog-desktop/data`；设置 `XDG_CONFIG_HOME` 时跟随该目录。

卸载前先在系统状态中撤销/停用后台权限，并确认已停用。卸载只删除应用和快捷方式，用户数据默认“卸载保留”；备份或永久删除数据目录必须单独操作。安装兼容的新版本会复用保留的数据。

## Provider 状态机

```text
未检测 → 未安装 / 未登录 / 已连接 / 检测失败
                     ↓
             创建行业 → 首次任务 → 查看日志与产物
```

- **Codex 套餐**：IntDog 必须在同一操作系统和用户账户中找到可执行的 Codex CLI，并确认登录状态。自动检测失败时，用户可通过系统文件选择器选择 `codex.exe` 或 `codex.cmd`。产品不默认跨 Windows/WSL 调用。
- **OpenAI API**：用户必须提供 API Key 和模型。桌面应用通过 Electron `safeStorage`
  使用操作系统凭据存储的加密能力保存 Key；后端只通过一次性匿名管道接收解密值，使用后清空传输对象。不得写入仓库、
  日志、URL、localStorage 或 API 响应。
- **任务包**：无需模型和密钥，可创建结构化 prompt，但不会直接生成完整研究报告。

### Agent 接口矩阵

| 接口 | 直接生成 | 自动检测 | 连接方式与边界 |
| --- | --- | --- | --- |
| Codex CLI | 是 | CLI + 公开登录状态 | 与 IntDog 同系统；可自动发现或手动选择命令文件 |
| Claude Code | 是 | CLI + `auth status` | 官方 `-p` 非交互模式，使用 plan 权限模式 |
| DeepSeek Harness | 否（实验性识别） | `dsh` | 开发者预览；使用 MCP/任务包，不伪装稳定一次性 CLI |
| Work Buddy | 否 | 可执行文件 | 它是 Claude Code 上的工作流层，通过 MCP/任务包交接 |
| Qwen Code、CodeBuddy Code、Kimi CLI | 否 | 可执行文件 | 国内 Agent 的 MCP/任务包交接入口 |
| Gemini CLI、OpenCode | 否 | 可执行文件 | 海外/中立 Agent 的 MCP/任务包交接入口 |
| 自定义 CLI | 否 | 受校验 UI Profile 或 `INTDOG_CUSTOM_AGENT_COMMAND` | 只保存公开 argv；默认只允许交接 |
| OpenAI、DeepSeek、Qwen、Azure OpenAI API | 是 | 环境或桌面安全存储 | Key 不进入浏览器、仓库、日志或 API 响应 |

“检测到”只证明公开命令存在；“已连接”还要求适配器的公开认证检查通过。IntDog 不扫描
ChatGPT、Claude 或其他 GUI 应用的私有账户目录。未列出的 Agent 可复制首次设置中的通用 MCP 配置读取 IntDog，
或在“研究助手 → Agent 任务交接”导出任务 JSON；完成后把结果 JSON 导回待复核区。新增直接执行适配器必须先固定输入、输出、认证、
权限、超时和错误契约。

Provider 不可用时，生成类操作必须在入队前被阻止并给出可执行修复步骤；纯本地浏览、行业管理、
任务包和不依赖模型的采集仍可使用。

### Agent 结果格式

导入对象必须包含 `task_id`、`agent_id`、`summary` 和至少一条 `assertions`；每条断言必须有 HTTP(S) `citations`。系统拒绝未知任务、无引用、错误 Schema、超过 500 KiB 和命令路径/shell 语法；合规结果只写入 `one_time/agent_results/` 的 `draft_review_required` 草稿并保留审计，不直接修改事实库。

## 首次启动旅程

1. 应用显示“本地运行组件 → 数据目录 → 智能体”的三项诊断，而不是空白工作台。
2. 用户选择 Provider：
   - Codex：显示安装状态、登录状态、执行路径和官方安装/登录链接；
   - API 模式：选择 Provider，输入 Key、模型和可选 HTTPS API Base，保存后安全重启；
   - 任务包：明确说明不会调用模型。
3. Provider 达到可用状态，或用户明确选择任务包后，才能完成向导。
4. 创建行业，运行“初始化行业研究”。应用跳转任务中心并持续显示阶段、日志、错误和产物。
5. 首次成功后，概览必须出现信息源、文档、实体或明确的“待采集”状态。

任务包与无模型真实采集不是同一结果。任务包只是交接；`NOM-01` 必须从公开免凭据来源取得发布者、文档、实体、产业链、内容哈希和零 Provider 调用证据。partial/offline 仍是外部缺口。

## 后台权限与撤销

后台调度默认关闭。用户启用后，IntDog 安装当前账户的 Windows 任务计划、macOS LaunchAgent 或 Linux systemd user timer。设置页显示安装/启用/最近运行/错误状态。撤销权限会移除系统调度入口，不删除计划、研究数据或凭据。关闭窗口后，已授权计划可以继续，但不得绕过 Provider 授权或安全存储状态。

## 故障与恢复

- EXE 无窗口：显示启动错误框并指向用户数据目录下的 `logs/backend.log`；不能静默退出。
- Codex 未安装：显示实际探测路径和官方安装链接，不自动安装第三方工具。
- Codex 未登录或 401：显示“在 IntDog 所在的同一操作系统和用户账户中登录”，提供重新检测和重新选择命令文件。
- API Key 无效：不持久化测试响应或 Key；显示供应商返回的脱敏错误。
- 后端提前退出：保留日志，应用不得显示“已连接”。
- 安全存储不可用：拒绝保存 API Key，允许用户改用任务包；桌面 App 不降级为明文或环境变量传递。

## P0 验收与测试覆盖

| ID | 风险/行为 | 状态与交互 | 判定方式 |
| --- | --- | --- | --- |
| O1 | 安装后首次启动 | 全新用户目录、第二次启动、路径含空格/中文 | 原生安装包启动并取得后端、UI 与日志证据 |
| O2 | Provider 诊断 | 无 CLI、自动发现、手动选择、`.cmd` 包装器、未登录、已登录 | 合成可执行文件/状态输出与 API 决策表 |
| O3 | API 凭据 | 空 Key、有效格式、重启、无 safeStorage | Key 不出现在文件明文、日志、DOM、API 响应 |
| O4 | 引导状态 | 首次、任务包、完成、重新打开设置 | DOM/可访问性测试验证状态转换和按钮门槛 |
| O5 | 首次任务 | 可用 Provider、不可用 Provider、任务失败 | 不可用时不入队；可用时跳转任务中心并可见日志 |
| O6 | 安装包完整性 | sidecar/Web/图标/卸载器缺失 | 安装后资源清单和启动前检查 |
| O7 | 诊断能力 | 后端退出、超时、Provider 401 | 用户可定位日志且错误信息不泄露凭据 |
| O8 | Agent 扩展 | 原生执行、MCP 交接、实验接口、未知 CLI | 注册表不把“存在”误报为“已认证/可直接生成” |

本地合成测试不证明真实 ChatGPT 账号或付费 API 可用。公开测试版只有在三个原生 runner
重新通过安装、引导、Provider 诊断、关闭和重开后才可发布。
