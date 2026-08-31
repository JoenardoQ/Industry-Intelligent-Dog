# Agent 与首次使用周期 · 第一轮完整审查

[English](2026-08-31-agent-onboarding-round-1-review.md)

## 边界与新鲜度

- 基线：当前未提交工作树；可下载产品基线于 2026-08-31 关闭。
- 审查范围：根文档、Search/intdog_core、App runtime/packaging、Web API/React、
  Electron、安全边界、测试、配置、生成契约、三平台工作流和运行证据。
- 排除：生产行业数据的内容质量重审、真实付费模型调用、邮件、提交、push、发布与删除。
- 证据限制：本机 WSL 无可调试 Chrome；electron-builder 两次停在 packaging；没有本轮
  Windows/macOS/Linux 原生 runner 结果；没有真实 Agent/API 账户可用性证明。

## 库存

| 分区 | 当前权威职责 | 主要消费者/证据 |
| --- | --- | --- |
| `DomainIntelSearch/intdog_core` | Schema、事实库、迁移、实体/Story/证据/调度 | Search、Web API、MCP、161 项 Python 测试 |
| `DomainIntelSearch/src` | 采集、历史、研究、报告、Provider、MCP、CLI | sidecar CLI、Job Manager、报告/研究页面 |
| `DomainIntelApp/runtime` | 数据兼容层、持久 Job、单实例和通用运行时 | Electron sidecar、源码启动器、App 测试 |
| `DomainIntelWeb/api` | 本地受保护应用边界与调度所有者 | React、Electron、OpenAPI |
| `DomainIntelWeb/src` | 七页工作台、首次引导、任务与产物交互 | 桌面用户、6 项 DOM 工作流测试 |
| `DomainIntelDesktop` | Electron 生命周期、安全存储、原生打包 | 三平台安装包、sidecar、原生烟雾 |
| 文档/配置/生成契约 | 用户合同、设计、状态、发行和 Provider 配置 | 用户、维护者、CI |
| `.github/workflows` | 三平台构建、测试版/正式版发行门槛 | GitHub-hosted 原生 runner |
| `DomainIntelData` | 生产事实与可移植产物；不进入安装包 | App/Search；本轮不改写、不重审 |

## 必要性账本

| Subject/kind | Observed consumers and contract evidence | Status | Compatibility/dynamic-discovery risk | Result/rationale | Evidence limits |
| --- | --- | --- | --- | --- | --- |
| SQLite/intdog_core 事实内核 | Web、Search、MCP、迁移和全部行业数据 | necessary | 高；数据格式与外部 JSON 读取者 | 保留为唯一业务写入权威 | 未审计第三方读者 |
| 兼容 JSON/dirty view | 报告、可移植数据、旧数据迁移 | necessary | 高；现有数据与脚本 | 保留并继续双向对账 | 非核心附件不在事务内 |
| Search 采集/研究/报告 | 用户核心行业知识与持续情报结果 | necessary | 中；网络源与供应商变化 | 保留模块边界 | 未运行真实联网源 |
| 旧 Orchestrator/ArchiveStore 路径 | 部分旧 CLI/模块仍构造，邮件/扁平归档仍有调用 | candidate simplify | 高；动态模块注册与旧 CLI | 限制其对现代命令的隐式构造，暂不删除 | 调用图含动态 registry |
| Provider 工厂与 Agent 适配器 | 报告、bootstrap、覆盖、任务包执行 | necessary | 高；外部 CLI/API 演进 | 保留统一创建边界 | DeepSeek Harness 仍为开发者预览 |
| Agent 注册表 | `/api/setup`、首次引导、连接状态 | necessary | 中；PATH、自定义命令和版本差异 | 保留能力标签，避免把安装等同认证 | 未测真实账户 |
| MCP 只读服务 | Claude/Work Buddy/其他 Agent 读取 IntDog | necessary | 高；MCP 协议和客户端兼容 | 保留只读默认；任务写回需另设授权边界 | 仅合成协议测试 |
| Web API/OpenAPI | React 和桌面 sidecar 的唯一业务边界 | necessary | 高；客户端/生成类型 | 保留并让生成契约成为门禁 | 外部客户端未知 |
| React 七页工作台 | 唯一发布 UI | necessary | 中；可访问性与响应式布局 | 保留 | 本轮无真实浏览器视觉证据 |
| Electron + PyInstaller | 三平台独立可下载应用 | necessary | 高；签名、OS、安全存储 | 保留单一共享实现 | 新安装包未在原生 runner 验证 |
| Chrome app-mode 源码启动器 | 开发/兼容启动和现有快捷方式测试 | necessary | 中；用户可能仍用源码路径 | 作为开发入口保留，不作为发行产品 | 真实使用量未知 |
| Provider 枚举/能力定义 | 工厂、校验、CLI、UI、调度、文档均重复 | candidate merge | 高；遗漏会造成可选但不可执行 | 合并为后端权威 manifest | 需迁移手写 TS 类型 |
| 状态/设计/发行文档 | 用户安装与维护决策 | candidate simplify | 中；历史链接和证据需保留 | 版本化证据，归档历史设计，更新当前状态 | 历史读者未知 |
| 原生工作流 | 生产安装包构建与发布保护 | necessary | 高；三宿主差异 | 扩大门禁，不拆平台实现 | 本机不能复现三平台 |
| 测试体系 | 161 Python、6 DOM、Electron、sidecar、包烟雾 | necessary | 低；主要为内部契约 | 保留风险分层并补原生真实 UI 门禁 | 没有真实账号/付费 API |
| `DomainIntelData` 生产内容 | 用户长期行业事实库 | necessary | 极高；不可恢复数据风险 | 本轮只读、不得清理 | 内容质量不在本轮重审 |

## 覆盖账本

| Dimension | Evidence | Status | Result | Limits |
| --- | --- | --- | --- | --- |
| 用户结果/范围 | 双语 README、onboarding 合同、首次本地工作流 | Finding | 无模型首个任务可用；“Agent 交接”仍缺一键配置/写回旅程 | 无原生视觉 |
| 领域模型/术语/所有权 | intdog_core、ProviderCapabilities、AgentSpec、任务/产物状态 | Finding | Agent、模型 Provider、MCP 客户端三种概念已分开，但枚举所有权分散 | 外部 Agent 版本变化 |
| 架构/依赖方向 | Search→core，Web API→service，Electron→sidecar | Finding | 主方向合理；旧 Orchestrator 仍可能被现代 CLI 隐式构造 | 动态模块调用图有限 |
| 数据/Schema/生命周期 | Schema v13、兼容视图、Job/Trash/Audit | no change justified | 当前加法迁移、恢复与路径边界充分支持本轮目标 | 附件跨介质 ACID 未覆盖 |
| 算法/资源边界 | 分页、历史分桶、覆盖门槛、CLI 超时 | no change justified | 已有数量/时间桶/发布者与上下文上限 | 未做新生产规模基准 |
| 接口/协议/版本 | OpenAPI、MCP 2024-11-05、CLI/API adapters | Finding | MCP 只读可发现，但 UI 不输出客户端配置；Provider 列表多源重复 | 未做多客户端互操作 |
| 正确性/边界/并发 | Job 锁、调度 claim、provider gate、首次重试 | Finding | 手动/自动任务在 Provider 未就绪时不入队；原生烟雾仍不验证 React 操作 | 多日休眠未测 |
| 安全/隐私/供应链 | safeStorage、preload、CSP、session token、HTTPS | Finding | Key 不进 DOM/API/日志；原生安全存储生命周期和依赖审计不在 CI 完整门禁 | 无签名/公证 |
| 性能/成本 | 50 行分页、500 上下文、8 秒诊断超时 | no change justified | 本轮新增诊断有界并并发 | 未测慢 WSL/大量 Agent CLI |
| 可靠性/恢复/可观测 | logs、job manifests、retry、shutdown、marker | Finding | sidecar 可观测；安装烟雾 API-first，React 白屏仍可能漏检 | AppImage 本机构建阻塞 |
| 可维护性/重复/扩展 | 工厂、Schema literal、两处 select、CLI help、registry | Finding | 新 Agent 需要多处同步，已形成明确漂移风险 | 未统计所有第三方扩展 |
| 测试/夹具/静态检查 | 161 Python、6 DOM、Node、compile/check_repo | Finding | 本地覆盖强；原生 workflow 未执行全 Python/DOM/OpenAPI drift | 无覆盖率百分比 |
| 开发体验/文档 | README、四子系统 README、DESIGN、STATUS | Finding | 安装指南改善；设计/状态/发行证据存在版本漂移和过时计数 | 历史文档需保留出处 |
| UX/可访问性/本地化 | 首次向导、中文 UI、响应式 CSS、DOM roles | Finding | 首次建行业已合并；Agent 长清单与真实字体/缩放仍未视觉验收 | 无 Chrome/CDP |
| 构建/发行/回滚 | 三平台 workflow、签名门槛、旧 pre-release | Finding | 结构正确；新源码未有三平台证据，旧 READY 结论不适用于当前 diff | 无发布授权 |
| 兼容/迁移/采用风险 | CLI/JSON、源码启动器、MCP、旧 Orchestrator | Finding | 加法兼容应保留；直接删除旧路径风险高 | 用户采用数据未知 |

## 三遍审查结论

1. **广度遍**：所有代码根、入口、测试、配置、Schema、依赖、构建、生成文件、文档和运行证据均入账；生产内容仅确认边界。
2. **跨层遍**：Agent 扩展困难、UI 下拉漂移和调度校验来自同一根因——能力清单没有单一所有者；“可下载”风险来自 native workflow 只测壳和 sidecar，没有运行完整产品合同。
3. **完整性挑战**：保留 SQLite、兼容 JSON、源码启动器和只读 MCP 有实际消费者；没有证据支持删除。旧 Orchestrator 可简化但不宜本轮直接移除。没有把商业数据库、完整社交 API或本地大模型包装成可低风险完成项。

## 完整提案集（等待选择）

### 1. P0 — 把三平台门禁升级为产品门禁

- 问题：`_native-package.yml` 只运行 Desktop Node 测试、sidecar 健康和 API-first 桌面烟雾；不运行完整 Python、DOM、OpenAPI drift，也不能证明 React 首次引导可操作。
- 变更：每个平台运行 Python/DOM/类型/OpenAPI/check_repo；桌面烟雾通过 renderer DOM 验证首次引导、创建行业、任务中心、第二次启动持久化，并在安全存储可用时验证加密写入/清除且不泄露测试 Key。
- 收益：安装包门槛与“用户下载可用”一致。
- 成本/风险：中等；原生任务时间增加，macOS/Windows DOM 驱动需处理时序。可逆，只改测试/工作流和 E2E 钩子。
- 验收：三 runner 全绿；任一 Web 构建、DOM、Python、OpenAPI、sidecar、首次任务、重开或凭据泄露失败均阻止 artifact。

### 2. P0 — 完成 Agent Bridge 的用户闭环

- 问题：Setup 能检测 9 类 Agent，但 `mcp_command` 未展示/复制；MCP 只读；自定义 Agent 只能靠环境变量；任务包没有可视化“领取—执行—导入—待复核”闭环。
- 变更：在连接设置生成 Codex/Claude/Work Buddy/通用 MCP 配置片段并可复制；提供受校验的自定义 CLI profile；增加任务包清单、导出与结果导入。写回只进入 `draft_review_required`，限制行业路径、大小、Schema、引用字段并保留审计；MCP 默认仍只读，写入能力必须显式启用并受桌面会话授权。
- 收益：未内置适配器的国内外 Agent 也真正可用，而非只出现在列表里。
- 成本/风险：高；需要新 API/Schema/UI/审计与安全测试。兼容性为加法，可通过只读默认回滚。
- 验收：至少 Codex、Claude、Work Buddy 和通用客户端配置可生成；未知 Agent 可导出任务并导入合规结果；越界、超限、错误 Schema、未授权写回全部拒绝且无部分写入。

### 3. P1 — 建立唯一的能力 Manifest

- 问题：Provider/Agent ID 和能力重复在 `provider_factory.py`、`llm_service.py`、Pydantic Literal、Repository 校验、CLI help、React 两个 select、TypeScript union 和文档中。
- 变更：后端 manifest 统一 ID、地区、连接类型、直接执行、Web search、认证、模型/API base 和文档；API 返回类型化 manifest，UI/调度动态渲染；工厂保留显式 adapter map，未知值 fail closed。
- 收益：新增 Agent/API 只改一个权威定义和一个必要适配器，消除“能选但不能跑”。
- 成本/风险：中等；涉及跨层契约和生成类型。加法迁移，旧 Provider ID 保留。
- 验收：代码搜索不存在第二份手写 provider 下拉/allow-list；manifest、工厂、API、调度和 UI 的集合契约测试一致。

### 4. P1 — 收敛当前文档与版本化发行证据

- 问题：`IMPLEMENTATION_STATUS.md` 未记录新 Agent/引导且测试数过时；`DESIGN.md` 仍以 v2 历史架构为主体并含乱码；发行合同的 `READY_FOR_PUBLIC_TESTING` 属于旧提交，但当前工作树已使证据失效。
- 变更：把当前架构/状态压缩为双语权威文档；历史设计移动到明确 archive；原生证据按 commit/diff 绑定，并把当前结论标为 `NOT_READY_PENDING_NATIVE_GATES`；README 只保留用户路径和链接。
- 收益：用户不会下载旧 EXE 后误以为具备新引导，维护者不会照旧架构实现。
- 成本/风险：低到中；主要是文档迁移，需保持历史链接。完全可逆。
- 验收：中英文结构语义一致；所有命令可执行；版本、测试数、支持平台、Agent 边界和当前 release 结论与代码/证据一致；无乱码与冲突架构声明。

## 依赖与建议顺序

建议选择 `1 → 3 → 2 → 4`。提案 3 先为提案 2 提供稳定能力数据；但提案 1 可独立先建立防回归门槛。任何提交、push、CI 执行或发布仍需单独授权。
