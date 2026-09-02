# Agent Connectivity and Conversations

IntDog connects to agents through native session protocols, managed local CLIs, model APIs, MCP, or reviewable task packages. It does not scan, inject into, or take over an already-open desktop window.

## Connection priority

1. Native session protocol for durable conversations, streamed events, interruption, and approvals.
2. Managed local CLI subprocess using that CLI's own sign-in state.
3. Model API configured explicitly by the user.
4. MCP for tools and task handoff; an MCP tool connection is not reported as a full chat connection.
5. Task packages for export to any agent and review-gated result import.

## Registered agents

| Agent | Preferred interface | Transport and session model | Maturity | Fallback |
| --- | --- | --- | --- | --- |
| Codex | [Codex App Server](https://developers.openai.com/codex/app-server/) | stdio JSONL; `initialize` → `initialized` → `thread/start|resume` → `turn/start`; streamed events and approvals | Supported interface; WebSocket remains experimental, so local stdio is the default | `codex exec`, OpenAI API, task package |
| Claude Code | [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) | Streamed SDK messages, `session_id`, resume and fork; IntDog does not attach to a Claude desktop window | Official SDK; capabilities are probed from the installed version | `claude -p`, Anthropic API, task package |
| Gemini CLI | [ACP implementation](https://github.com/google-gemini/gemini-cli/tree/main/packages/cli/src/acp) | ACP over stdio/NDJSON with multiple sessions, session loading, and permission requests | ACP interface; runtime capabilities are negotiated | Headless CLI, compatible Gemini API, task package |
| Qwen Code | [ACP/server protocol](https://github.com/QwenLM/qwen-code/blob/main/docs/developers/qwen-serve-protocol.md) | ACP stdio and an optional local HTTP/SSE service | ACP is available; the daemon protocol requires version constraints | stream-json CLI, DashScope API, task package |
| Kimi CLI | [ACP](https://github.com/MoonshotAI/kimi-cli/blob/main/src/kimi_cli/acp/AGENTS.md) | `kimi acp`; JSON-RPC, new/load session, streamed updates, permission requests | Multi-session mode enables unstable protocol features and must be negotiated | Kimi CLI, compatible API, task package |
| CodeBuddy Code | [ACP](https://www.codebuddy.ai/docs/cli/acp) | `codebuddy --acp` over stdio; Streamable HTTP and local HTTP API are also available | ACP is available; HTTP API is marked Beta | `codebuddy -p`, compatible API, task package |
| OpenCode | [OpenCode Server](https://dev.opencode.ai/docs/server/) | `opencode serve`; OpenAPI HTTP, SSE events, durable sessions, permission responses | Public server interface; embedded V2 SDK remains Beta | CLI, compatible API, task package |
| DeepSeek Harness | [SDK JSON-RPC](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/sdk/protocol/README.md) | Newline-delimited JSON-RPC over stdio with `initialize`, `session/prompt`, and session events | Developer Preview; currently lacks per-prompt cancel and session close | Headless CLI, DeepSeek API, task package |
| Work Buddy | [MCP Gateway](https://docs.work-buddy.ai/handbook/operations_mcp-gateway/) | MCP plus a sidecar; conversations use leases, generations, and acknowledgements | Integrated as a workflow/tool gateway, not as a generic model runtime | MCP, its managed Codex/Claude hosts, task package |

“Registered” means IntDog can identify the product and describe candidate connection modes. It does not mean the installed version has passed diagnosis or that every capability is implemented. Settings show the detected interface, effective capabilities, and actual fallback separately.

### Effective implementation in IntDog 4.1

- Enabled durable/basic sessions: Codex App Server and the shared ACP stdio adapter for Gemini, Qwen, Kimi, and CodeBuddy.
- Retained one-shot CLIs: `codex exec` and `claude -p`. For APIs without a native session, IntDog retains the industry conversation context.
- Registered but not enabled as native sessions: Claude Agent SDK, OpenCode Server, and DeepSeek Harness JSON-RPC. The UI does not report these as implemented adapters.
- Work Buddy remains an MCP/task-handoff integration. OpenAI, DeepSeek, DashScope, Azure OpenAI, and explicitly configured compatible APIs remain available; Anthropic API is catalogued but not claimed as a direct adapter.

## Shared ACP handshake

Gemini CLI, Qwen Code, Kimi CLI, and CodeBuddy Code share IntDog's ACP adapter:

1. IntDog starts the user-selected executable with an argv list and no shell.
2. It sends `initialize` over stdio and negotiates the protocol version and capabilities.
3. If authentication is unavailable, IntDog shows the official login path and never reads or copies private agent credentials.
4. It creates or loads the industry session with `session/new` or `session/load`.
5. It sends messages through `session/prompt` and consumes `session/update`.
6. IntDog never auto-approves `session/request_permission`. The basic ACP adapter immediately reports this limitation; an interactive Agent-tool permission card is not available yet.
7. The low-level adapter defines `session/cancel`, but the 4.1 conversation panel does not yet expose a reliable cross-request Stop action. Closing the browser request is not reported as Agent cancellation.

ACP implementations may support different protocol versions. The adapter trusts negotiated capabilities, safely ignores unknown events, and never infers completion from an unknown event. Version 4.1 stores conversation messages and external session IDs, not the complete protocol event stream.

## IntDog session and execution boundary

- Each industry owns an independent local conversation and message history.
- Conversation and execution are separate state machines. Ordinary answers render directly; reports, collection, knowledge mutations, and deletion produce an `action_proposal` only.
- A proposal includes industry, action, parameters, agent, data scope, revision, and expiry. Approval applies to that exact revision; any execution-relevant edit revokes it.
- Agents cannot call IntDog mutation routes directly. After confirmation, the Action Registry validates the proposal and submits it to the existing Job Queue.
- Sign-in state belongs to the external agent. IntDog stores executable bindings, capability diagnostics, and session IDs, but does not copy sign-in tokens.
- API credentials continue through the existing restricted credential channel and are excluded from conversations, logs, exports, and Git.

## Capability levels

| Level | Minimum behavior |
| --- | --- |
| Full session | Durable session, streamed events, explicit completion, interruption, approval requests |
| Basic session | Multi-turn context and deterministic completion; missing capabilities are visible in the UI |
| One-shot CLI | One request and one result, without reliable session resume |
| API conversation | IntDog persists conversation state; the provider API generates responses |
| Task handoff | Schema-validated task export and review-gated result import only |

Agent upgrades can change protocol behavior. IntDog diagnoses the version and handshake before selecting an adapter. A fallback must be visible to the user and must never silently switch to a different agent or paid provider.
