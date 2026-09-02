# Agent 连接与对话

IntDog 可以通过原生会话协议、本机 CLI、模型 API、MCP 或任务包连接 Agent。系统按能力选择连接方式，不会扫描、注入或接管已经打开的桌面窗口。

## 连接优先级

1. 原生会话协议：支持持续会话、流式事件、中断和审批时优先使用。
2. 本机 CLI：由 IntDog 启动受管理的子进程，复用该 CLI 自己的登录状态。
3. 模型 API：用户显式配置服务地址、模型与凭据。
4. MCP：用于工具与任务交接；不把 MCP 工具连接误报为完整对话连接。
5. 任务包：无法直接运行时导出、人工交给任意 Agent，再导回待复核结果。

## 已登记 Agent

| Agent | 首选接口 | 传输与会话 | 成熟度 | 回退方式 |
| --- | --- | --- | --- | --- |
| Codex | [Codex App Server](https://developers.openai.com/codex/app-server/) | stdio JSONL；`initialize` → `initialized` → `thread/start|resume` → `turn/start`；流式事件与审批 | 正式接口；WebSocket 仍为实验性，因此本机默认 stdio | `codex exec`、OpenAI API、任务包 |
| Claude Code | [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) | SDK 流式消息、`session_id`、恢复/分叉；IntDog 不连接 Claude 桌面窗口 | 官方 SDK；具体能力按已安装版本探测 | `claude -p`、Anthropic API、任务包 |
| Gemini CLI | [ACP 实现](https://github.com/google-gemini/gemini-cli/tree/main/packages/cli/src/acp) | ACP over stdio/NDJSON；多会话、加载会话、权限请求 | ACP 接口；按运行时版本协商能力 | Headless CLI、Gemini 兼容 API、任务包 |
| Qwen Code | [ACP/服务协议](https://github.com/QwenLM/qwen-code/blob/main/docs/developers/qwen-serve-protocol.md) | ACP stdio；也可使用本地 HTTP/SSE 服务 | ACP 可用；HTTP 守护协议仍需版本约束 | stream-json CLI、DashScope API、任务包 |
| Kimi CLI | [ACP](https://github.com/MoonshotAI/kimi-cli/blob/main/src/kimi_cli/acp/AGENTS.md) | `kimi acp`；JSON-RPC、会话新建/加载、流式更新、权限请求 | 多会话实现启用了不稳定协议能力，必须协商后使用 | Kimi CLI、兼容 API、任务包 |
| CodeBuddy Code | [ACP](https://www.codebuddy.ai/docs/cli/acp) | `codebuddy --acp` stdio；也支持 Streamable HTTP 和本地 HTTP API | ACP 可用；HTTP API 标记为 Beta | `codebuddy -p`、兼容 API、任务包 |
| OpenCode | [OpenCode Server](https://dev.opencode.ai/docs/server/) | `opencode serve`；OpenAPI HTTP、SSE 事件、持久 Session 与权限响应 | Server 接口公开；嵌入式 V2 SDK 仍为 Beta | CLI、兼容 API、任务包 |
| DeepSeek Harness | [SDK JSON-RPC](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/sdk/protocol/README.md) | stdio 换行分隔 JSON-RPC；`initialize`、`session/prompt`、session 事件 | Developer Preview；当前缺少逐 Prompt 取消与关闭，不能宣称完整对话控制 | Headless CLI、DeepSeek API、任务包 |
| Work Buddy | [MCP Gateway](https://docs.work-buddy.ai/handbook/operations_mcp-gateway/) | MCP + sidecar；会话操作有租约、generation 与 acknowledge 语义 | 作为工作流/工具网关接入，不当作通用模型运行时 | MCP、其托管的 Codex/Claude、任务包 |

“已登记”表示 IntDog 知道如何识别该产品及其可能的连接方式，不等于当前安装版本已经通过诊断，也不等于所有能力均已实现。设置页会分别显示检测到的接口、可用能力和实际回退路径。

### IntDog 4.1 的实际实现状态

- 已启用持续/基础会话：Codex App Server；Gemini、Qwen、Kimi、CodeBuddy 的共用 ACP stdio 适配器。
- 已保留单次 CLI：`codex exec` 与 `claude -p`。对不支持原生会话的 API，由 IntDog 保存行业对话上下文。
- 已登记但尚未启用原生会话：Claude Agent SDK、OpenCode Server、DeepSeek Harness JSON-RPC。它们不会在 UI 中显示为“原生适配器已实现”。
- Work Buddy 继续作为 MCP/任务交接接口。OpenAI、DeepSeek、DashScope、Azure OpenAI 和显式配置的兼容 API 继续保留；Anthropic API 目前只登记，不宣称直接适配。

## 通用 ACP 握手

Gemini CLI、Qwen Code、Kimi CLI 和 CodeBuddy Code 可以共用 IntDog 的 ACP 适配层：

1. IntDog 以参数列表启动用户选定的可执行文件，不经过 shell。
2. 通过 stdio 发送 `initialize`，协商协议版本和双方能力。
3. 认证未就绪时只显示官方登录指引，不读取或复制 Agent 私有凭据。
4. 通过 `session/new` 或 `session/load` 建立行业会话。
5. 使用 `session/prompt` 发送消息，消费 `session/update`。
6. Agent 发出 `session/request_permission` 时，IntDog 不会自动批准。当前基础 ACP 适配器会立即报告该限制；尚未提供交互式 Agent 工具权限卡。
7. 底层适配器已定义 `session/cancel`，但 4.1 对话面板尚未提供可靠的跨请求“停止”操作；关闭浏览器请求不能被表述为 Agent 已取消。

ACP 实现可能处于不同协议版本。适配器以握手返回的能力为准；未知事件会被安全忽略，不能据此推断任务成功。4.1 保存对话消息和外部会话 ID，不保存完整协议事件流。

## IntDog 会话与执行边界

- 每个行业拥有独立的本地会话和消息历史；切换行业不会混用上下文。
- 对话和执行是两个状态机。普通回答直接显示；生成报告、采集、修改知识或删除数据只能形成 `action_proposal`。
- 提案包含行业、动作、参数、Agent、数据范围、revision 和过期时间。确认只对当前 revision 有效；任何参数变化都会撤销旧确认。
- Agent 不能直接调用 IntDog 的写接口。用户确认后，由 IntDog 的 Action Registry 验证提案，再进入现有 Job Queue。
- CLI 或原生协议的登录状态归对应 Agent 所有。IntDog 只保存可执行文件绑定、能力诊断和会话 ID，不复制登录令牌。
- API 凭据继续使用现有受限凭据通道，不写入对话、日志、导出文件或 Git。

## 能力等级

| 等级 | 最低能力 |
| --- | --- |
| 完整会话 | 持久 Session、流式事件、明确完成状态、中断、审批请求 |
| 基础会话 | 多轮上下文和可判定完成状态；缺失能力在 UI 中明确标注 |
| 单次 CLI | 一次请求/一次结果，无可靠会话恢复 |
| API 对话 | 由 IntDog 保存对话状态，Provider API 负责生成 |
| 任务交接 | 只导出/导入经过 Schema 校验的任务与待复核结果 |

版本升级可能改变协议能力。IntDog 必须先做版本与握手诊断，再选择适配器；失败时降级必须由用户看见，不能静默换成不同 Agent 或不同付费来源。
