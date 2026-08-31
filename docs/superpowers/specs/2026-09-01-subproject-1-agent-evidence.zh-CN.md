# 子项目 1：权威契约与 Agent 证据闭环规格

状态：已批准，待实施验证
上位规格：`2026-09-01-complete-local-first-product-design.zh-CN.md`

## 目标

把当前 Agent 任务导出与 JSON 导入升级为可阅读、可审计、不可越级的证据闭环，并消除 Agent Bridge 未声明响应 Schema、复核信息不足和文件索引分散的问题。

## 范围

- 为 Agent Profile、任务包、结果列表、结果详情、复核和核验响应定义完整 Pydantic/OpenAPI Schema。
- 建立可扩展能力 Manifest 和本机安全发现：已验证的 CLI/API 才能直接执行，其余 Agent 使用 MCP、任务包或受限自定义 CLI；“被发现”不等于“可直接控制”。
- 原始导入文件继续作为不可变审计产物；SQLite 保存索引、断言、引用、复核和核验状态。
- 用户逐条查看断言与引用，选择 `rejected`、`opinion` 或 `submitted_for_verification`。
- 核验器检查引用可达性、发布者身份、时间有效性、实体对齐、现有事实冲突、引用内容的语义支持、证据定位、数值/单位/币种/期间一致性和声明类型所需的独立佐证。
- 只有全部适用门槛通过的原子断言才能把现有 `claims.status` 提升为 `accepted`；缺少可复现证据定位、语义只部分支持、数值限定不一致或佐证不足时必须保持 `candidate`，明确矛盾进入 `disputed` 或 `rejected`。

## 数据模型

Schema 14 新增：

- `agent_results`：结果 ID、行业、任务、Agent、原始文件、内容哈希、状态、创建时间。
- `agent_assertions`：断言文本、类型、状态、关联 claim、核验摘要。
- `agent_citations`：规范 URL、可达性、Source/Document 关联和核验时间。
- `agent_result_reviews`：动作、操作者、说明和时间。

导入与人工复核层的状态转换为：

`draft_review_required → rejected / opinion / submitted_for_verification → candidate / disputed / accepted`

禁止从 `draft_review_required` 或 `opinion` 直接进入 `accepted`。重复导入按内容哈希幂等，并保留已有复核状态。

上位规格中的 `raw → candidate → corroborated / disputed / rejected → accepted` 描述证据/事实层；这里的状态描述 Agent 导入与人工复核层。`submitted_for_verification` 通过核验后才可映射到证据层的 `candidate`、`disputed`、`rejected` 或 `accepted`，两层不得混用。

## 声明级证据充分性

每条断言先拆为主体、谓词、客体、时间、地区、数值和限定词均明确的原子声明。每个支持项必须保存可复现定位器：文档内容哈希，以及 HTML selector/文本偏移、PDF 页码/表格单元格或结构化 API 字段路径之一；只保存 URL 不构成支持证据。

语义判定输出 `supported / partial / contradicted / unknown`，并记录支持片段、定位器和理由。`partial` 或 `unknown` 不能进入 accepted。同一 Agent 或同一次模型调用既生成断言又给自己打分，不能作为唯一核验依据。

数值声明必须对数值、正负号、单位、币种、数量级、统计口径和期间逐项匹配。允许换算时必须保存原值、目标值、换算公式、汇率/基准来源和容差；无法确定的默认容差为零并保持 candidate。

佐证策略由声明类型决定：

- 身份、监管状态和公司正式披露：一条已验证且适用的官方一手记录可充分；
- 事件、交易和产业链关系：一条直接当事方一手披露，或两个所有权独立的合格发布者集群；
- 市场规模、份额、估值和非官方统计：至少两个所有权独立来源，并保留口径差异；
- 财务数字：适用期间的监管申报/审计报表优先；二手来源必须另有独立佐证；
- 技术性能：标准、官方规格或可定位的学术论文结果，并保留实验条件；泛化超出原文范围时不得 accepted；
- 因果推断、预测、投资判断和观点：不得自动提升为事实，只能保留为 opinion/candidate，除非拆出的可观察子声明分别通过其类型门槛。

## API

- `GET /api/agent-bridge/profiles`
- `POST /api/agent-bridge/profiles`
- `DELETE /api/agent-bridge/profiles/{profile_id}`
- `GET /api/industries/{folder}/agent-bridge/tasks`
- `GET /api/industries/{folder}/agent-bridge/tasks/{task_id}`
- `GET /api/industries/{folder}/agent-bridge/results`
- `GET /api/industries/{folder}/agent-bridge/results/{result_id}`
- `POST /api/industries/{folder}/agent-bridge/results`
- `POST /api/industries/{folder}/agent-bridge/results/{result_id}/review`
- `POST /api/industries/{folder}/agent-bridge/results/{result_id}/verify`
- `GET /api/agent-bridge/capabilities`
- `POST /api/agent-bridge/discover`
- `POST /api/agent-bridge/profiles/{profile_id}/diagnose`

所有响应都必须有 `response_model`，分页列表限制 1–100 条。Profile 总量限制 100，文件限制 256 KiB；结果限制 500 KiB；损坏或超限文件安全失败。

## UI

研究助手显示独立复核区：结果摘要、Agent、任务、导入时间、状态、每条断言和可点击引用。操作必须显示语义明确的“驳回”“保留为观点”“提交核验”，核验结果展示每个门槛及失败原因。

## 安全与迁移

- 导入只接受已知行业和任务；拒绝绝对路径、穿越、未知字段越权和无 HTTP(S) 引用断言。
- 原始导入原子写入行业目录，数据库索引与审计在事务中完成。
- Schema 14 迁移只新增表；现有 JSON 结果在首次读取时幂等索引，不改写原文件。
- 核验不得因单个 URL 超时而接受断言，也不得把 Agent 自报来源等级当作可信身份。
- 自动发现只检查 PATH、明确的应用标识和用户选择的可执行文件，不遍历用户文档或读取凭据内容；命令使用 argv 白名单、版本探测、超时和输出上限，不经过 shell。

## 验收

- OpenAPI 不再为 Agent Bridge 返回匿名 `{}`。
- UI 可以查看断言和引用并执行三种复核动作。
- 状态机拒绝所有非法越级和重复副作用。
- 重复导入不会抹去复核状态或重复审计。
- 事实统计只在声明级语义支持、定位、数值和类型化佐证全部通过后变化。
- Codex、Claude 等具有稳定安全 CLI 的 Agent 可经原生适配器诊断；DeepSeek/Qwen 等兼容 API、MCP/任务包 Agent 和其他未知 Agent 经能力 Manifest 接入，UI 不虚报直接执行能力。
- 需求 `AG-01` 至 `AG-08` 的测试 ID、oracle、优先级、平台和未闭合缺口记录在双语需求—测试追踪矩阵中。
