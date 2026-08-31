# DomainIntelSearch

[English documentation](README.md)

IntDog 的研究与采集引擎。它是唯一直接访问网页、模型和外部接口的运行层；采集器、Provider 和报告器通过共享 `intdog_core` 写入结构化事实库与兼容产物，不依赖桌面 App。

## 安装

```bash
cd DomainIntelSearch
python -m pip install -e .
python -m src.main --help
```

默认数据目录为相邻的 `../DomainIntelData`。命令中的 `--industry` 接受行业名称或别名；需要精确控制时使用 `--folder AI`、`--folder Chips`。

## 执行模式

| 模式 | 参数 | 认证 | 行为 |
|---|---|---|---|
| Codex 套餐 | `--provider codex` | 本机 ChatGPT/Codex 登录 | 调用 Codex CLI 搜索并生成草稿 |
| API | `--provider openai/deepseek/qwen/azure` | 对应供应商 API Key | 通过 API 生成草稿，可能产生费用 |
| 任务包 | 不传 provider 或选择 task | 无 | 只写 prompt/任务 JSON，不生成成文报告 |

Codex 套餐模式不读取 `OPENAI_API_KEY`。若出现 `401 Unauthorized`，先在同一 Windows/WSL 环境重新登录 Codex，再单独运行一个最小命令确认登录有效。

## 推荐工作流

长周期产物会先检查分层历史覆盖，不能用最近一天的数据外推半年、两年或五年。
App 可在“研究助手 → 长周期证据覆盖”查看六个周期并直接采集；报告生成也会自动补齐。
命令行可显式预先回填：

```bash
python -m src.main backfill-history --folder AI --kind biennial
python -m src.main backfill-history --folder AI --kind fiveyear
```

回填按日/周/月时间桶从 GDELT、日期化 Google News RSS 和可选 OpenAlex 收集并去重，
支持 checkpoint 续跑与供应商熔断。OpenAlex 的正式规模使用需通过环境变量
`OPENALEX_API_KEY` 提供免费 Key；不配置时其他新闻源仍可独立满足时间覆盖门槛。
生成器检查总量、时间桶覆盖率与发布者多样性；不达标时拒绝伪装成完整报告。
完整方法见 [`docs/history-collection-method.md`](../docs/history-collection-method.md)。

```bash
# 1. 创建目录、种子来源和研究任务；不联网、不调用模型
python -m src.main init-industry --industry 人工智能

# 2. 搜索并审计来源，通过门槛后构建产业链和实体
python -m src.main bootstrap-industry --industry 人工智能 --provider codex

# 失败后从已保存阶段继续
python -m src.main resume-bootstrap --industry 人工智能 --provider codex

# 3. 每日采集
python -m src.main crawl-daily --industry 人工智能

# 4. 诊断覆盖与数据质量
python -m src.main doctor --industry 人工智能
python -m src.main verify --industry 人工智能
```

`bootstrap-industry` 的顺序是“信息源门槛 → 产业链门槛 → 实体覆盖门槛”。中间结果和失败状态会保存在 `one_time/research/bootstrap/`，下游阶段不会在上游失败时伪装成功。

## 全面研究方法

初始化的目标是建立可继续扩张的行业研究空间。系统从行业概念逐层展开：

```text
行业 → 子领域 → 产业链活动 → 产品/技术 → 企业/研究组/人物
     → 标准/政策 → 市场与资本 → 事件 → 主张与证据
```

发现过程遵循开放世界假设：数据库只代表“当前已发现”，不代表行业全集。每次初始化和刷新都应保留四类结果：已验证实体、待验证候选、明确排除项、尚未覆盖的节点。

覆盖不能只统计来源总数。诊断应按以下矩阵衡量空白：

```text
地域 × 子领域 × 产业链节点 × 实体类型 × 来源类型 × 事件类型 × 时间
```

头部公司之外，应主动搜索细分供应商、初创公司、大学实验室、独立研究机构、标准工作组和关键人物。搜索停止条件应由边际新增率、节点覆盖率和来源多样性共同决定，而不是达到固定的“Top 10”。

默认 Web 工作台把覆盖单元和每次查询尝试持久化到 SQLite：模型提出的 URL 和数量先标为
`planned`，在实际抓取、规范化和验证之前其来源/实体增量均记为 0。尝试完成后才记录真实
边际产出、证据和停止原因，因此“模型列出”不等于“系统已覆盖”。

## 命令地图

| 目标 | 命令 | 主要结果 |
|---|---|---|
| 初始化骨架 | `init-industry` | 配置、种子来源、任务 JSON |
| 完整行业初始化 | `bootstrap-industry` / `resume-bootstrap` | 来源、产业链、实体和审计状态 |
| 更新来源 | `refresh-sources` / `discover-sources` / `enrich-sources` | `sources.json` 与候选审计 |
| 每日采集 | `crawl-daily` | 六类每日 JSON |
| 周/月/季聚合 | `crawl-weekly` / `crawl-monthly` / `crawl-quarterly` | 聚合数据和任务元信息，不等于成文报告 |
| 周/月/季成文 | `generate-period` | Markdown 与可视化 JSON |
| 行业报告 | `report-tasks` / `generate-report` | prompt 或半年/两年/五年报告 |
| 深度研究 | `generate-deep-report` | 产业链、公司、技术等专题报告 |
| 事件影响 | `impact` / `generate-impact` | 影响任务或成文分析 |
| 竞争格局 | `landscape` | 分层、Watchlist 和历史快照 |
| 知识查询 | `knowledge` / `kg` / `modules` / `query` | 知识结构与学习模块 |
| 质量检查 | `verify` / `doctor` | 结构、链接、覆盖和可信度诊断 |
| 情报实验室 | `compile-evidence` / `observe-sources` / `simulate-chain` / `plan-boundaries` / `run-lab` | 证据缺口、来源观测、情景传播与研究议程 |
| 数据迁移 | `migrate-data` | 幂等导入旧 JSON，不删除原文件 |
| 数据对账 | `reconcile-data` | 从 SQLite 重建 dirty 的来源、每日和实体 JSON 视图 |
| Agent 接入 | `mcp-serve` | 本地 MCP 服务 |

`crawl-daily` 使用可机读结果契约：六类均成功为 `completed`，部分失败为
`partial`，全部失败为 `failed`。`partial/failed` 会返回非零退出码，App 不会推进
调度 checkpoint，下次 tick 可重试。邮件、验证和日志是后处理，不会把六类采集失败
伪装成成功。

默认 Web 调度不会调用邮件后处理；它为每个任务显式设置 `INTDOG_DISABLE_EMAIL=1`。
CLI 的可选邮件能力为兼容用途保留，但不属于当前 App 工作流。

历史 `reports_event` 主张只追加/更新同一主张；离开近期验证窗口不会被标记为
superseded。

CLI 使用真正的子命令解析；查看某个命令的参数：

```bash
python -m src.main generate-period --help
```

根帮助只列出命令，子命令帮助列出该命令可接受的兼容参数。历史调用顺序
`python -m src.main <command> [options]` 保持不变。

Intelligence Lab 常用命令：

```bash
python -m src.main run-lab --folder AI
python -m src.main simulate-chain --folder Chips --event "先进封装产能受限" --chain 先进封装
python -m src.main create-research-task --folder AI --agenda-id <id> --budget 20
python -m src.main audit-artifacts --folder AI --repair-latest
```

## 来源策略

`sources.json` 使用 9 类来源：`official`、`associations`、`blogs`、`platforms`、`self_media`、`news`、`journals`、`financials`、`finance`。

- 政府、监管、统计、标准、公司披露和同行评审材料优先。
- 新闻媒体用于交叉验证；自媒体和社交帖子只作为线索。
- 国内与外文占比是覆盖目标，不是硬凑配额；系统会扩大国内来源回看窗口并在 `doctor` 中报告实际结果。
- 无 RSS、付费墙或反爬但有价值的来源可保留为 `recommended_manual`，供人工关注，不冒充自动抓取。
- 手动添加的来源与 RSS 会在刷新时保留，不同行业可以复用同一来源。

“来源质量高”与“某条事实已被印证”是两个维度。单条内容只有满足一手证据或独立发布者交叉验证条件时，才能标记为 verified/corroborated。

来源能力由结构化 adapter 字段决定，不从 `note` 文本猜测。自动源统一记录 `fresh / stale /
degraded / failed`，人工源记录 `manual`，未配置源记录 `unconfigured`；失败保留最近成功时间并
使用有上限的退避，不把空结果伪装成成功。

## 算法演进目标

当前命令已形成来源、产业链和实体三道门槛；后续算法按以下顺序增强，未实现部分不得在报告中伪装为已完成能力：

1. **查询规划**：由行业本体展开中英文别名、技术、产品、节点、实体和事件查询；按论文、政策、公司披露等来源生成不同检索式。
2. **四级去重**：已具备 URL 规范化、内容哈希、持久 Story 及人工合并/拆分审计。跨语言自动
   合并要求规范实体、结构化事件键和时间窗；继续建设真实标注集、语义召回、转载与共同上游识别。
3. **实体消歧**：已使用跨行业稳定 ID 和别名表；继续建设历史名、外部标识和语义消歧。
4. **主张—证据抽取**：已落地主张、supports/contradicts/qualifies 与双时间存储；继续扩展自动抽取和冲突识别。
5. **多目标排序**：综合相关性、来源质量、时效性、重要性、证据强度、新颖性和多样性；重要性与可信度分别展示。
6. **离线评测**：持续测量相关率、召回率、重复率、实体链接准确率、引用有效率、产业链分类准确率和报告数字可追溯率。

两个媒体转载同一公告不能算两个独立证据；存在冲突的数据应保存各自口径、日期和适用范围，而不是让模型强行选择单一答案。

所有结果写入 `DomainIntelData/<Industry>/`；目录、字段、状态和写入责任见 [Data 契约](../DomainIntelData/README.md)。
四项确定性研究闭环的算法、限制和验收标准见 [Intelligence Lab](INTELLIGENCE_LAB.md)。

## 故障排查

- **一直 Planning**：初始化会执行多阶段搜索。查看 App 日志或 `one_time/research/bootstrap/bootstrap_status.json`，确认当前阶段；失败后使用 `resume-bootstrap`，不要重复清空数据。
- **401 Unauthorized**：Codex 登录凭据缺失或当前环境不可见；重新登录。API 模式则检查 Key 是否注入启动进程。
- **API 密钥**：只从供应商环境变量或 `INTDOG_LLM_API_KEY` 读取；不把真实密钥写入
  受版本控制的 YAML。非本机 API Base 必须使用 HTTPS。
- **采集 API**：NewsAPI、GNews 和 Semantic Scholar 密钥分别使用 `NEWSAPI_KEY`、
  `GNEWS_API_KEY`和 `SEMANTIC_SCHOLAR_API_KEY`；SMTP 使用 `INTDOG_SMTP_PASSWORD`。
- **本地分享**：`serve` 默认只监听 `127.0.0.1`；只有确认局域网可见风险后才使用
  `--host 0.0.0.0`。该简易服务没有身份认证。
- **403/429/超时**：通常是目标站反爬、限流或网络限制。系统应保留失败记录并继续其他来源，不把失败页当正文。
- **有任务、没有报告**：`report-tasks` 和周期 crawl 只生成任务/聚合；使用 `generate-report` 或 `generate-period` 才会生成 Markdown。
- **国内内容偏少**：先检查国内来源是否可达，再运行 `enrich-sources` 和 `doctor`；来源数量比例不能保证当天事件比例。

## 验证

```bash
python -m unittest discover -s tests -v
python scripts/check_repo.py
```

模型输出均为 `draft_review_required` 草稿。市值、进出口、政策和投资判断等时效性或高风险内容必须核对日期、币种、原始披露与引用。
