# Intelligence Lab v1.2

状态：v1.2 已实现并通过离线验收。本文是四项探索能力的工程契约；它们读取现有结构化事实库，
不自动把推断升级为已验证事实或投资结论。

## 目标与边界

Intelligence Lab 把 IntDog 从报告生成器扩展为可重复运行的研究闭环：识别证据缺口、
观察来源健康度、探索产业链冲击传播、形成下一轮研究议程。v1 使用确定性算法，
无需联网或模型；联网采集和模型可以消费其任务，但不是计算成功的前提。

## 四项能力

### Evidence Graph Compiler

`compile-evidence` 将当前 Claim–Evidence、实体和产业链覆盖编译成快照。每条当前主张记录
支持、反驳、限定证据数和独立发布者簇数，并按规则标记 `unsupported / single_source /
contested / corroborated`。产业链节点同时报告实体和证据覆盖。输出不能声称数据库之外的召回率。

### Source Observatory

`observe-sources` 统计每个来源及发布者簇的文档量、最后观测时间、认证状态、监控方式和
类别覆盖，标记 `unused / stale / unverified / active`。同一所有者簇不会被当成多个独立来源。
v1 不主动请求网页，因此“无数据”只表示本地尚未观察到，不等于来源失效。

### Temporal Supply-chain Twin

`simulate-chain --event ... [--chain ...]` 对当前产业链节点执行可解释的情景传播。
显式指定节点或名称命中的节点为 `direct`；优先沿带关系、方向、有效期、置信度和证据数的
`ValueChainEdge` 传播。没有正式边时才显式标记 `ordered_fallback`，按节点顺序回退。
每一步乘以不大于 1 的关系衰减因子，输出方向、距离、路径、边和依据，并生成安全转义的 Mermaid。
它是敏感性分析，不是因果模型、价格预测或投资建议。

v1.2 将分数命名为 `heuristic_exposure_score`，并为每一步记录传播语义、可能效应
`negative / positive / mixed / uncertain`、时间滞后、证据状态和敏感性区间。
`depends_on` 等关系按各自语义定向，不能套用 supplies 的方向。

### Knowledge Boundary Autopilot

`plan-boundaries` 综合证据图、来源观测和产业链覆盖，形成去重、可排序的研究议程。
优先级由严重度、产业链空白、证据独立性和来源缺口确定；每项必须给出目标、理由、
建议检索方向和可验证完成条件。再次运行更新同一议程项，不无限制造重复任务。用户可以
设置 `in_progress / done / dismissed`；已满足条件的旧开放项进入 `resolved_candidate`。

`run-lab` 依次执行以上四项（情景推演仅在提供 `--event` 时执行）。

## 数据模型与产物

Schema v8 增加：

- `analysis_artifacts`：不可变分析快照，保存输入哈希、算法版本、状态、内容和指标；
- `research_agenda_items`：稳定 ID 的研究议程，状态为 `open / in_progress / done / dismissed`。

Schema v9 增加 `value_chain_edges`。Lab 使用行业互斥锁和统一 Run 记录；数据库快照先提交为
事实源，JSON/Markdown/Mermaid 使用原子替换。相同算法版本和输入哈希复用已有快照；
每类保留最近 365 个不同快照。人工议程与审计记录不受快照清理影响。

Schema v10 增加 `chain_edge_evidence`、`research_agenda_history` 和 `research_tasks`。
正式产业链边必须关联边专属 Document、Claim 或引用 URL；只有节点级引用时边保持 candidate，
不得增加正式证据数。研究议程可生成带查询、来源类型、最大预算和验收条件的任务包，但不会
自动调用外部模型。情景及其他分析写入版本化 Artifact Bundle，Manifest 校验完整后才原子更新
latest 指针；同一事件不同参数不会互相覆盖。

来源观测同时报告来源链接、唯一来源、发布者簇、唯一文档、来源链接 HHI 和文档产出 HHI。
人工关注源状态为 `manual_watch`；地区统一为 china/international/unknown。

兼容产物位于 `DomainIntelData/<Industry>/one_time/intelligence/`：

- `evidence_graph.json` 与 `.md`；
- `source_observatory.json` 与 `.md`；
- `scenarios/<slug>.json`、`.md`、`.mmd`；
- `research_agenda.json` 与 `.md`。

SQLite 是结构化快照和议程的事实源；这些文件用于人工阅读和 App 展示。

版本包位于 `artifacts/<kind>/<artifact_id>/`，至少含 `artifact.json`、`artifact.md` 和
`manifest.json`；情景额外含 `graph.mmd`。`latest/<kind>.json` 是校验后更新的快捷指针。
`audit-artifacts [--repair-latest]` 可校验所有哈希并从最新有效包恢复指针。

## 验收标准

- 四个命令在空数据和已有数据行业上均能确定性完成，且不访问网络。
- 同一输入与算法版本复用快照；输入变化才创建新的不可变快照；议程 ID 稳定。
- Evidence 按 ID 去重；权威性、独立支持簇、反证和置信度分开呈现。
- 情景传播分数随距离单调不增，且每个受影响节点都有可检查边与路径。
- `unresolved` 在 Run、Artifact、CLI 和 App 中保持同一状态，不标成 completed。
- 边界规划不会把“本地未发现”表述为“不存在”，不会重复创建相同开放议程；
  已消失的开放缺口进入 `resolved_candidate`，done/dismissed 不被覆盖。
- 所有产物含 `generated_at`、`algorithm_version`、输入摘要和限制说明。
- 并发 Lab 任务被行业锁拒绝；文件写入失败不破坏上一份完整展示产物。
- 并行同权重边、循环图和多直接节点不会因优先队列比较非标量对象而崩溃。
- Artifact Bundle 的 Manifest 可验证、可恢复 latest；情景 ID 包含全部输入参数。
- MCP 只读暴露 Lab 快照、议程和路径，不提供未认证写入口。
- App 支持搜索、筛选、排序、滚动与分页，并直接绘制情景路径；来源与证据指标以可排序列呈现。
- 旧 Schema 与 JSON 保持可读，迁移可重复执行。

## v1 非目标

- 自动抓取来源可用性、分布式 Connector 市场或跨用户共享信誉；
- 经过历史回测的因果/财务预测；情景分数不是概率；
- 语义实体消歧、自动事实冲突裁决或无人值守发布；
- 将研究议程自动提交给付费模型或外部人员。
