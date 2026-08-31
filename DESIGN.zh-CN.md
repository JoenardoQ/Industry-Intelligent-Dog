# IntDog 当前架构

[English](DESIGN.md) · [用户指南](README.zh-CN.md) · [当前状态](IMPLEMENTATION_STATUS.zh-CN.md)

## 产品边界

IntDog 是本地优先的桌面行业情报工作台。Electron 管理原生生命周期和加密凭据边界；冻结的 Python sidecar 提供唯一的 localhost FastAPI 应用；React 是正式发布 UI。Windows、macOS、Linux 共享同一套源码，但分别生成并验证原生安装包。

它不内置大语言模型，不附带商业数据库权限，也不会把“检测到桌面 Agent”误报为“账户已登录”。任务包模式无需模型。直接生成必须使用已登录的 Codex/Claude CLI，或用户明确配置的 API Provider。

## 运行结构

```text
Electron
  ├─ safeStorage + 最小 preload IPC
  ├─ 在 127.0.0.1:随机端口启动冻结 Python sidecar
  └─ React renderer
       └─ 受会话保护的 FastAPI/OpenAPI
            ├─ intdog_core SQLite 事实与审计库
            ├─ 采集、研究、报告、调度和任务
            ├─ 只读 MCP
            └─ 受复核约束的 Agent Bridge
```

Electron 每次启动生成随机会话能力。Renderer 永远拿不到 API Key。Key 只通过 preload IPC 接收，由操作系统安全存储加密，再注入 sidecar 环境；系统无法提供安全加密时拒绝保存。

## 数据与证据

SQLite 与 `intdog_core` 是唯一业务写入权威。兼容 JSON/Markdown 继续作为可移植视图和产物。事实、主张、关系、来源、文档、Story、任务、运行和审计均使用稳定 ID。模型与外部 Agent 输出默认是 `draft_review_required`；没有证据时必须明确显示未知。

行业覆盖采用开放世界模型：子领域、产业链端点、地区、实体类型、来源类别、事件和时间跨度以缺口衡量，不把固定 Top 10 假设成完整。长周期采集同时受数量、时间桶和发布者多样性门槛约束。

## Agent 与 Provider 架构

`DomainIntelSearch/src/services/capability_manifest.py` 是国内外 Agent 与 API Provider 的唯一能力清单，统一定义 ID、地区、连接/执行方式、公开命令、认证、Web 能力、默认配置和可调度性。Provider 工厂继续使用显式、失败即拒绝的 adapter map。

- Codex CLI 与 Claude Code 有受限直接执行适配器。
- OpenAI、DeepSeek、Qwen、Azure OpenAI 使用显式 API 配置。
- DeepSeek Harness、Work Buddy、Qwen Code、CodeBuddy、Kimi CLI、Gemini CLI、OpenCode 和未知 Agent，在没有已验证适配器时使用只读 MCP 或任务包交接。
- Agent Bridge 导出任务，并把通过校验的结果原子写入待复核区；导入断言绝不直接写入事实库。

## 依赖方向

- `intdog_core`：Schema、Repository、确定性领域规则。
- `DomainIntelSearch/src`：采集和研究服务；依赖 core。
- `DomainIntelApp/runtime`：供应用使用的中立数据/任务兼容层。
- `DomainIntelWeb/api`：受保护应用边界；依赖 service/runtime。
- `DomainIntelWeb/src`：使用生成契约的 React 客户端；无文件系统权限。
- `DomainIntelDesktop`：只负责生命周期和打包；不写业务事实。

旧 v2 设计保存在[历史归档](docs/archive/DESIGN-v2-legacy.md)，不再是实施合同。

## 发行门禁

每个平台都必须运行完整 Python 套件、Web DOM 测试与生产构建、OpenAPI 漂移检查、仓库检查、桌面测试、冻结 sidecar 烟雾、renderer 首次工作流、重开持久化，以及安全存储可用时的凭据生命周期。未签名测试包只能作为 Pre-release。Windows 稳定版必须签名，macOS 稳定版必须签名并公证。

当前就绪结论和证据限制记录在 [IMPLEMENTATION_STATUS.zh-CN.md](IMPLEMENTATION_STATUS.zh-CN.md)；旧提交的通过记录不能证明已变化的工作树。
