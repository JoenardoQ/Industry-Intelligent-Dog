# Industry Intelligence Operating System

**Version:** 3.0 Beta
**Authority:** 代码与 `IMPLEMENTATION_STATUS.md` 优先；README 是用户入口。

## 1. 产品目标

IIOS 面向任意行业建立开放世界、持续更新、可追溯的知识体系。系统不以固定问题或固定 Top N 作为完成条件，而是持续扩展：

- 子领域、产业链活动、产品和技术；
- 头部与长尾企业、初创公司、研究组、人物和机构；
- 标准、政策、市场、资本和事件；
- 主张、支持证据、限定证据、反证和未知边界。

Beginner / Intermediate / Expert 只改变解释深度与学习路径，不改变底层知识全集。

## 2. 架构

```text
Connectors → Ingestion/Normalization → intdog_core
                                      ├─ Intelligence/Knowledge
                                      ├─ Query/Reports
                                      └─ App/MCP/Email
```

| 边界 | 责任 |
|---|---|
| Connectors | RSS、网页、论文、GitHub、金融和模型 Provider |
| Pipelines | 抓取、规范化、去重、分类、聚类和抽取 |
| `intdog_core` | Schema、稳定 ID、事务、迁移、锁、Repository 和 application service |
| Intelligence | 实体关系、主张证据、覆盖矩阵、竞争格局和影响分析 |
| Presentation | 查询、报告、图表、App、MCP 和邮件 |

报告只能消费结构化事实与证据，不能反向授予事实状态。App 的业务写入必须经过 application service。

## 3. 输入

所有研究入口共享：`industry`、`level`、`region`、`lang`。行业名称可映射到档案和稳定数据目录；显示名称不能承担目录或实体主键职责。

执行模式：

- Codex 套餐：本机登录，无 API Key。
- API：OpenAI、DeepSeek、Qwen 或 Azure，显式认证和计费。
- 任务包：只生成 prompt，不伪装成成文结论。

Provider 统一通过 factory 创建，并声明联网搜索、认证和结构化输出能力。

## 4. 数据内核

`DomainIntelData/intdog.sqlite3` 是结构化事实库；JSON/Markdown 是可移植兼容产物。

核心对象：

| 对象 | 关键语义 |
|---|---|
| Industry | 行业注册与生命周期 |
| Source | 全局规范来源＋行业分类和监控状态 |
| Document | 去重文档、原始内容、发布时间和发现时间 |
| Entity | 全局规范企业/研究组/人物/技术/产品/产业链活动 |
| Relation | 有方向、带行业/时间/证据的实体关系 |
| Event | 行业事件及关联文档 |
| Claim | subject–predicate–object–qualifiers–valid time |
| Evidence | supports / contradicts / qualifies |
| Run | 阶段、状态、checkpoint、指标和错误 |
| Publisher | 规范发布者、官方域名、所有权/转载簇与认证状态 |
| ValueChainNode | 产业链节点、顺序/父子关系、覆盖状态和证据统计 |
| ValueChainEdge | 节点间 supplies/depends_on/enables/substitutes 等带时间和证据的有向边 |
| ChainEdgeEvidence | 对产业链边的 supports/contradicts/qualifies 证据，可关联文档、主张或 URL |
| EntityChainRole | 实体在某节点的时态角色、置信度与证据数 |
| AnalysisArtifact | 证据图、来源观测和产业链情景的不可变算法快照 |
| ResearchAgendaItem | 稳定、可排序、可关闭的知识边界研究项 |
| ResearchTask | 从议程生成的有预算、验收条件和结果关联的离线任务包 |

数据按 Raw、Normalized、Intelligence、Artifacts 四层组织。周/月/季是查询窗口，不是三套独立事实。

数据库要求：SQLite WAL、外键、busy timeout、顺序迁移、FTS5、行业互斥锁、原子事务。旧 JSON 使用 `migrate-data` 幂等导入，原文件不删除。

Repository 连接必须通过会关闭连接的上下文管理器使用；提交/回滚不等于关闭连接。
查询接口不得创建行业或修改注册表，只有显式创建、导入和写入入口可以注册行业。
SQLite 是规范事实源；兼容 JSON 属于物化视图。每次影响兼容视图的事务必须在同一事务内
标记对应视图为 dirty，JSON 成功落盘后才能标记 clean；进程中断后由对账器从 SQLite
重建 dirty 视图，不以旧 JSON 反向覆盖较新的数据库事实。

## 5. 时间与状态

时间字段区分：`published_at`、`observed_at`、`retrieved_at`、`valid_from/valid_to`。
发布者信任不采信模型或来源自行声明的 `tier`；只有系统注册的官方域名或已审计
发布者可提升先验。转载稿按原始发布者/所有权簇去重，不把多个转载站计为独立印证。

证据状态：`candidate → collected → verified/corroborated`；错误对象可进入 `rejected`。模型产物是 `draft_review_required`，只有明确人工流程能授予 `reviewed/published`。

历史事件主张采用追加与版本化语义。仅当同一主张被修正、否定或替代时才写入
`superseded_at`；条目离开当前采集/验证窗口不代表事实失效，不得整类覆盖历史主张。

## 6. 全面发现方法

```text
行业 → 子领域 → 产业链活动 → 产品/技术 → 企业/研究组/人物
     → 标准/政策 → 市场/资本 → 事件 → 主张/证据
```

系统同时保存已验证实体、待验证候选、明确排除项和未覆盖节点。覆盖矩阵至少包含：

```text
地域 × 子领域 × 产业链节点 × 实体类型 × 来源类型 × 事件类型 × 时间
```

停止扩展由边际新增率、节点覆盖率、来源独立性和长尾发现率共同决定，不由固定数量决定。

## 7. 可信度

来源权威性与事实印证分开：

- 官方披露、监管、统计、标准和同行评审是一手证据候选；
- 新闻用于交叉验证；社交和自媒体只作为线索；
- 多个页面若来自同一公告或通讯社，只计算一个发布者簇；
- 冲突结论保存各自口径、日期、适用范围和证据，不强行合并；
- `credibility_score` 是可解释评分，`evidence_status` 是生命周期状态。

## 8. 算法管线

1. 本体驱动的中英文查询扩展。
2. URL、内容指纹、事件和转载链四级去重。
3. 稳定 ID、别名、外部标识和地域辅助的实体消歧。
4. 事件聚类与 Claim–Evidence 抽取。
5. 相关性、权威性、时效性、重要性、新颖性和多样性重排。
6. Precision、Recall、重复率、实体链接、引用有效率和数字可追溯率评测。

未实现的语义能力必须在产物中标为候选或路线图，不得伪装为确定结果。

Intelligence Lab 在该管线之上执行四个离线闭环：按发布者簇编译证据状态、按本地文档
观测来源健康度、按产业链相邻位置执行衰减情景传播、将覆盖空白编译为稳定研究议程。
情景传播是可解释敏感性分析，不是因果预测。算法契约见
[`INTELLIGENCE_LAB.md`](INTELLIGENCE_LAB.md)。

同一 Lab 分析运行必须由 application service 建立行业锁和 Run；Artifact 状态、Run 终态、
CLI 语义与 App 展示必须一致。结构化快照是事实源，展示文件使用原子替换。重复输入可复用
同算法版本快照，但不得修改历史快照内容。

边的 `evidence_count` 必须由 `chain_edge_evidence` 计算，禁止由节点引用或模型自报数字赋值。
情景输出必须称为启发式暴露度而非概率；关系方向、效应、时间滞后和回退拓扑均可检查。
Artifact Bundle 的 Manifest 是展示层版本边界，只有全部文件哈希通过后才能成为 latest。

## 9. 任务执行

每次长任务记录 `run_id`、kind、stage、status、checkpoint、metrics、错误和开始/结束时间。
终态区分 `completed`、`partial`、`failed`、`cancelled`和 `interrupted`。进程退出码 0
只表示命令成功履行了其结果契约；每日采集还必须报告成功/失败类别。全部失败为
`failed`，部分失败为 `partial`；两者均不推进调度 checkpoint。
同一行业使用互斥锁；嵌套子阶段可重入。幂等、可恢复、可取消并保留失败原因是验收目标；
当前可靠取消、跨重启恢复和进程树状态收敛尚未全部达到，见 `IMPLEMENTATION_STATUS.md`。

桌面端进程任务由独立 Job Runner 管理：启动时创建独立进程组，实时日志通过回调交给 UI，
状态清单原子持久化，取消终止进程组而非只关闭弹窗。App 关闭时请求取消全部本次会话任务，
并在限时后强制回收仍存活的进程组；同步调度和异步弹窗任务使用相同的等待语义。
下次启动将遗留的 running/cancelling 清单标为 interrupted。UI 视图不得自行持有重复的
Popen/线程生命周期实现。

## 10. 接口

- CLI：初始化、采集、验证、覆盖诊断、全文查询、报告、迁移和 Intelligence Lab。
- App：行业/来源管理、每日情报、知识图、覆盖统计、报告和任务日志。
- MCP：只读结构化查询，拒绝路径越界。
- Email：只发送已生成摘要和原始链接；默认关闭。

## 11. 验收

- Schema 迁移可重复执行，旧数据迁移幂等。
- 所有 Repository 连接在成功和异常路径都会关闭，测试不得产生连接 `ResourceWarning`。
- 查询不存在的行业返回明确错误且数据库行数不变。
- SQLite 提交后若兼容 JSON 写入失败，对账器可重建来源、每日数据和实体视图。
- App 和 Search 不产生不同的业务写入规则。
- 同一实体或来源跨行业只保存一份规范对象。
- 文档删除保留恢复材料，运行冲突被锁拒绝；完整恢复工作台仍是后续验收项。
- 每个 verified/corroborated 主张可追溯到证据文档。
- 报告中的关键数字包含日期、币种、单位、口径和引用。
- `doctor` 展示覆盖空白，而不是只输出总数量。
- Evidence Graph 区分支持、反驳、限定和独立发布者簇；同源转载不增加独立性。
- 产业链情景的传播分数随跳数单调不增，未命中节点时返回 unresolved 而不是猜测。
- 研究议程使用稳定 ID 重入更新；分析快照不可变，相同输入可复用，每类保留最近 365 个差异快照。
- 正式产业链边优先于位置回退；传播步骤暴露关系、方向、证据和衰减依据。
- 相同输入快照可去重，差异快照可比较；保留策略不得删除人工议程或审计记录。
- 来源总量按唯一对象和行业链接分别统计，跨类别链接不能重复增加唯一文档数。
- MCP 对 Lab 保持只读；研究任务执行结果必须关联 Run、Artifact 和验收记录。

商业数据库、完整社交 API、高级语义消歧、转载链识别、多人审核和服务端高可用仍属于后续能力。
