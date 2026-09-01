# IntDog 需求—测试追踪矩阵

日期：2026-09-02

候选 revision：当前工作树；本地证据为 focused，最终统一门禁必须在候选 revision 重新运行。

## 测试合同

系统边界包括 Python/SQLite 核心、FastAPI/OpenAPI、React renderer、Electron/sidecar/后台服务、三平台安装包和 GitHub 发行门禁。真实用户数据、计费 API、管理员级攻击者、签名和公证不属于自动测试边界。公开免凭据联网验收与真实已登录 Agent 验收是受控外部门禁，不能由 mock 替代。

状态词含义：

- `planned`：已有明确测试 ID 和 oracle，但尚未实现；
- `implemented-focused`：冻结报告记录了对应 focused 测试通过，但不等于当前候选的完整回归证据；
- `implemented-unverified`：测试存在，但尚未在当前候选 revision 完整执行；
- `external-gate`：必须在指定原生 runner、公开网络或已登录 Agent 环境执行；
- `covered`：仅在当前 revision 的对应命令和证据通过后使用；
- `gap`：缺少可判定测试、环境或产品决策，不能声称覆盖。

下表记录当前实现证据。`implemented-unverified` 与 `implemented-focused` 都不代表发行通过；只有最终统一命令和单列外部门禁才能关闭对应行。冻结证据包括 SP1 task reports、SP2 unified repair、SP3 report、SP4 freeze 和 SP5 A/B reports。

## 覆盖矩阵

| Requirement ID | Priority | Evidence source | Partitions and boundaries | States and interactions | Failure modes | Test ID | Test level and oracle | Platform | Status / gaps |
|---|---|---|---|---|---|---|---|---|---|
| AG-01 | P0 | 子项目 1 数据模型 | Schema 13→14、新建/重复导入 | draft、review、candidate、accepted | 越级、重复副作用、迁移中断 | `AG-T01` `test_agent_evidence.py::test_schema14_and_review_state_machine` | SQLite 状态与审计行精确匹配；只有合法转换成功 | all Python | implemented-unverified |
| AG-02 | P0 | 子项目 1 声明级充分性 | supported/partial/contradicted/unknown | 生成 Agent 与核验器相同/不同 | 有效 URL 但正文不支持 | `AG-T02` `test_agent_evidence.py::test_semantic_support_required` | 只有带支持片段和独立判定的 supported 可继续；其余非 accepted | all Python | implemented-unverified；语义 verifier 实现待选但不得由生成调用单独裁决 |
| AG-03 | P0 | 子项目 1 证据定位 | HTML、PDF、结构化 API；哈希相同/变化 | 快照更新、定位重放 | 仅 URL、selector 失效、页码错误 | `AG-T03` `test_agent_evidence.py::test_reproducible_evidence_locator` | 用哈希+定位器重取同一支持内容；失败保持 candidate | all Python | implemented-unverified |
| AG-04 | P0 | 子项目 1 数值规则 | 正负号、单位、币种、数量级、期间、口径 | 原值与合法换算 | 10×错误、USD/CNY 混淆、季度/年度错配 | `AG-T04` `test_agent_evidence.py::test_quantitative_consistency` | 手工 fixture 的规范值/换算记录精确相等；未知容差不通过 | all Python | implemented-unverified |
| AG-05 | P0 | 子项目 1 类型化佐证 | 身份、事件、财务、市场、技术、因果/预测 | 0/1/2 发布者集群、同所有者 | 伪独立、多数票、观点事实化 | `AG-T05` `test_agent_evidence.py::test_claim_type_corroboration_table` | 决策表逐格断言 disposition；因果/预测永不自动 accepted | all Python | implemented-unverified |
| AG-06 | P0 | 子项目 1 冲突规则 | 已有 accepted 与新断言一致/冲突 | 并发核验、重复核验 | 后写覆盖、简单多数覆盖 | `AG-T06` `test_agent_evidence.py::test_conflict_is_disputed_idempotently` | accepted 保持不变，新断言进入同一 conflict group | all Python | implemented-unverified |
| AG-07 | P1 | Agent Gateway | native CLI、API、MCP、taskpack、restricted CLI | ready/not installed/auth invalid | shell 注入、超时、超大输出 | `AG-T07` `test_agent_discovery.py` | 能力与执行等级精确；未知默认 import-only；无 shell | Win/mac/Linux | implemented-unverified |
| AG-08 | P1 | Agent Bridge API/UI | 空/损坏/超限结果、分页 1/100/101 | 导入、复核、核验、重开 | 路径穿越、匿名 OpenAPI Schema | `AG-T08` API+DOM contracts | 确定状态码和生成类型；逐断言/引用/失败原因可见 | Python + renderer | implemented-unverified |
| SRC-01 | P0 | 子项目 2 活动状态机 | 九类别、中英查询、候选不足/充足 | round 1/2/N、resume | 一轮即收敛、重复候选算新增 | `SRC-T01` `test_source_campaigns.py::test_two_round_convergence` | 至少两轮且连续两轮零新增合格项才 converged | all Python | implemented-unverified |
| SRC-02 | P0 | 子项目 2 暂停语义 | 403、429、超时、预算、登录/付费墙 | paused→resume | 错把依赖失败写成 converged | `SRC-T02` source fault-injection table | 每种依赖失败为 paused 且保留 checkpoint/reason | all Python | implemented-unverified |
| SRC-03 | P1 | 来源审查 | 官方、媒体、平台、自媒体、个人 | auto/manual/reject/reassess | 仅因可达即 active | `SRC-T03` governance decision table | 只有身份/所有权/URL 全通过的官方一手源可自动 active | all Python | implemented-unverified |
| SRC-04 | P1 | 跨行业 Publisher | 同 Publisher 加入两个行业 | 共享身份/健康，独立启停/优先级 | 复制 Publisher、跨行业状态串扰 | `SRC-T04` repository integration | Publisher ID 相同，industry membership 状态独立 | all Python | implemented-unverified |
| SRC-05 | P0 | Document 去重 | URL 参数、镜像、转载、跨语言事件 | 输入顺序置换 | 合并丢证据、同所有者伪独立 | `SRC-T05` property/metamorphic dedup | 任意输入顺序得到同一 canonical groups，关系数不减少 | all Python | implemented-unverified |
| ENT-01 | P1 | 实体覆盖矩阵 | 10 类对象×地区×端点 | 2/3/8/10 深度、空单元 | Top 10 冒充全景、复制实体凑数 | `ENT-T01` `test_entity_coverage.py::test_adaptive_coverage_frontier` | 适用单元 3 个初始门槛，高价值端点 8–10；不足输出 gap | all Python | implemented-unverified |
| ENT-02 | P0 | 实体消歧 | 别名、同名异体、更名、并购 | auto/manual merge | 错合并、时间身份丢失 | `ENT-T02` entity-resolution decision table | 只有标识/官网/隶属/时间一致才自动 merge；歧义 manual | all Python | implemented-unverified |
| ENT-03 | P0 | 产业链关系 | node/edge 有/无 Document/Assertion | 新增、更新、冲突 | 模型描述直接生成正式边 | `ENT-T03` chain repository integration | 无 evidence ID 的边不能进入 accepted 图；方向和有效期持久化 | all Python | implemented-unverified |
| TASK-01 | P0 | Schema 21 任务账本 | 九状态、合法/非法转换 | retry/cancel/pause/interrupted | partial 推进成功边界 | `TASK-T01` `test_task_runtime.py` | 状态机和 last-success 数据逐项精确匹配 | all Python | implemented-unverified |
| TASK-02 | P0 | 租约与单实例 | App/Worker 同 tick、过期/有效租约 | crash→takeover | 双重执行、僵尸租约 | `TASK-T02` concurrency integration | 同一周期键恰有一个 owner/output；过期后一次接管 | all Python | implemented-unverified |
| TASK-03 | P0 | 时间窗 | 04:00、首次、周期不足、DST、时区变化 | last success/partial | 重复/遗漏周期、错误推进 | `TASK-T03` `test_time_windows.py` | 固定时钟下 start/end/period key 与手工表一致 | all Python | implemented-unverified |
| TASK-04 | P1 | 长周期采集 | 两年/五年、稀疏/事件峰值 | resume、source exhaustion | 近期集中、重复凑数 | `TASK-T04` history bucket tests | 3–5/日目标、≥90%适用月桶、单桶≤3×中位数或有 overflow 理由 | all Python | implemented-unverified |
| SEC-01 | P0 | 后台凭据通道 | argv/env/pipe/file | start/read/close/crash | 密钥出现在进程环境或日志 | `SEC-T01` Desktop canary lifecycle | 唯一 canary 在 argv/env/日志/账本/状态/临时目录匹配数为 0；pipe 读一次后 EOF | Win/mac/Linux | implemented-unverified + native external-gate |
| SEC-02 | P0 | 后台授权撤销 | Provider×行业×任务作用域 | queued/running/request sent | 撤销后仍领取、明文降级 | `SEC-T02` authorization state table | 撤销后新 claim=0，未发送任务 cancelled/paused；已发送限制可见 | Python + Desktop | implemented-unverified |
| SEC-03 | P1 | 安全存储不可用 | locked/unavailable/corrupt | background wake | 回退到 env/file 明文 | `SEC-T03` Desktop fault injection | 任务 paused、确定错误；所有不安全通道仍为 0 canary | Win/mac/Linux | implemented-unverified + native external-gate |
| NOM-01 | P0 | 无模型最小有用流程 | 空数据目录、公开免凭据网络 | success/partial/offline | 只生成 taskpack/种子却报成功 | `NOM-T01` `test_product_closure_b.py` + native no-model smoke | `public_credential_free`；≥3 发布者/2 类、≥6 非重复文档/2 独立发布者、≥5 实体/3 类、≥3 节点/2 证据边、Provider 调用=0 | Win/mac/Linux + public network | implemented-unverified + external-gate；本地 oracle/adapter 已实现，但实时源可用性与安装实例 provenance 未验证 |
| UI-01 | P1 | 完整 UI 状态 | loading/empty/partial/stale/error/ready | 路由切换、后台任务 | 空白页、阻塞导航 | `UI-T01` route-wide DOM | 每状态有语义文本/行动；导航保持可用 | renderer | implemented-unverified |
| UI-02 | P1 | 每日/行业管理 | 排序、跨页全选、恢复删除、导入导出 | 重开、失败恢复 | 来源误署名、不可恢复删除 | `UI-T02` content workflow DOM | 数据顺序、selection set、trash/restore 和来源标签与 fixture 精确匹配 | renderer | implemented-unverified |
| UI-03 | P1 | Markdown/可访问性 | GFM、长中英、恶意 HTML、200% | 键盘/焦点/窄屏 | XSS、截断、焦点丢失 | `UI-T03` ArtifactReader+axe+renderer | sanitize 后无脚本/危险 URL；axe 无 serious/critical；焦点顺序确定 | renderer | implemented-unverified |
| SIG-01 | P1 | 跨日信号动量 | 首次/重复、缺日、04:00、并列排名、转载 | new/heating/tracking/cooling/unresolved、版本切换 | 重跑漂移、转载造势、日期边界错误 | `SIG-T01` `test_signal_observability.py`（含 batch/N+1 合同）+ renderer | 不可变日观测重算得到固定状态/差值/七日趋势；同输入幂等，转载不增加独立来源 | all Python + renderer | implemented-unverified |
| SIG-02 | P1 | 系统自身漂移 | 七/三十日、零分母、固定评估集、算法版本 | baseline→alert→diagnose | 只报采集量、升级误报漂移、无原始证据 | `SIG-T02` drift decision table | 每项含分母/基线/阈值/版本/观测链接；固定集退化触发确定告警 | all Python + renderer | implemented-unverified |
| ART-01 | P1 | 成品质量门 | 缺证据、空泛/短/占位/重复、坏 sidecar/链接/锚点 | generated→partial/ready | 格式完整冒充研究成功 | `ART-T01` `test_artifact_quality.py` + `test_product_closure_b.py` | 决策表逐项返回机器可读原因；任一必需项失败为 partial，且不改变 Fact 状态 | all Python | implemented-unverified |
| ART-02 | P1 | 便携单文件简报 | Markdown/HTML、禁网、后端关闭、恶意内容 | 搜索/筛选/收藏/打印 | CDN 依赖、数据不一致、脚本注入 | `ART-T02` offline renderer contract | HTML 无外部资源，离线交互可用；与 Markdown manifest/hash 相同；危险内容已转义 | renderer | implemented-unverified |
| SCALE-01 | P2 | 列式分析触发器 | 499999/500000+ 文档、P95 1 秒边界、写阻塞、备份体积 | inactive→prototype-candidate | 过早依赖、双写 Schema、阈值无基准 | `SCALE-T01` benchmark decision table | 未触发时无 DuckDB/Parquet 运行依赖；触发只允许 SQLite→派生层单向原型 | Python + packaging | implemented-unverified；备份“不可接受”阈值需基准阶段量化 |
| PKG-01 | P0 | 冻结 sidecar | serve/cli/worker、资源清单 | install path 空格/Unicode | 缺模块、混入数据/venv | `PKG-T01` packaged-command/resource tests | 三入口 exit/health 正确；manifest 与允许集一致、拒绝集为零 | Win/mac/Linux | implemented-unverified + native external-gate |
| PKG-02 | P0 | 原生生命周期 | 安装、启动、后台、重开、卸载 | crash/timeout/residual process | 假 GUI 验收、卸载删数据 | `PKG-T02` native lifecycle smoke | 每阶段 marker+超时诊断；卸载后数据 hash 不变 | Win/mac/Linux | external-gate |
| PKG-03 | P1 | Agent 接入验收 | reference harness 与真实登录 CLI | export/run/import/review | mock 冒充真实 Agent | `PKG-T03A/B` | A 确定合同全部通过；B 真实 CLI exit=0、结构化导入且断言仍 review-required | harness + one user-controlled native host | external-gate；登录状态未验证 |
| REL-01 | P0 | 同 revision 三平台 | artifact SHA/version/name | rerun/partial platform | 混合旧包、无 checksum | `REL-T01` workflow/native reports | 三报告 commit SHA 相同；每包 SHA-256 与下载字节匹配 | GitHub native runners | external-gate |
| REL-02 | P1 | Issue/Pre-release 幂等 | 现有 #1–#3 / 缺失项 | rerun、失败重试 | 重复 Issue/Release | `REL-T02` release orchestration contract | 按平台 label/title/tag 查询；存在 update，不存在 create；第二次运行数量不增 | GitHub | implemented-unverified + external readback |
| CLEAN-01 | P1 | 旧架构退役 | import/docs/install/replacement 四证据 | retain/migrate/delete | 误删测试或用户数据 | `CLEAN-T01` retired-surface contract | 每个删除项四证据齐全；发行清单无目标；全回归通过 | repository | implemented-unverified |
| DOC-01 | P2 | 双语文档 | README/安装/状态/设计 | EN/ZH 结构变化 | 一方缩写或命令漂移 | `DOC-T01` release-doc contract | 标题、命令、能力/限制和 revision 状态语义对齐 | repository | implemented-unverified |

## 适用性与剩余缺口

- 正常/异常、边界、重复、乱序、状态迁移、恢复、并发、时间、权限、依赖失败、资源限制、Schema、Unicode/时区、可访问性和原生生命周期均有矩阵行。
- 管理员/root、调试器、内核和物理内存攻击超出产品威胁模型；文档必须明确这一排除，不能宣称绝对内存清除。
- 语义支持 oracle 的实现仍需在 `AG-T02` RED 阶段确定。无论选用规则、模型或组合，都必须保存定位片段，并禁止同一生成调用成为唯一裁判；在该测试通过前自动 accepted 功能保持关闭。
- `NOM-01`、真实 Agent、Windows/macOS/Linux 原生生命周期和 GitHub 幂等 readback 都需要外部环境证据；本地 mock、reference harness 或历史 release 不能关闭这些行。
- 已实现行具有本地 focused 证据，但当前候选仍须运行统一 Python、Web、Desktop、静态、OpenAPI drift 与 build 门禁。NOM-01 实时采集、真实登录 Agent、原生生命周期/服务/keychain、签名/公证、下载字节校验与 GitHub 幂等 readback 仍为外部门禁。
