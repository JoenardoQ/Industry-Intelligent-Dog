# DomainIntelData

[English documentation](README.md)

IntDog 的本地数据层。这里不运行爬虫或模型，只保存各行业的配置、来源、研究过程、情报和报告。目录可以独立备份，也可以被 App 直接读取。

## 当前目录契约

```text
DomainIntelData/
├── intdog.sqlite3                   # 结构化事实库、全文索引、任务和审计
├── _jobs/                          # App 长任务运行清单与终态
├── _trash/                         # App 删除后的可恢复数据
└── <Industry>/
    ├── config.json                 # 名称、别名、关键词等
    ├── sources.json                # 9 类来源及审计信息
    ├── one_time/
    │   ├── knowledge/              # 子领域、产业链、实体、学习模块
    │   ├── landscape/              # 竞争分层、Watchlist、历史快照
    │   ├── intelligence/           # 证据图、来源观测、情景与研究议程
    │   ├── reports/                # 行业/深度报告、图表、任务
    │   ├── research/bootstrap/     # 初始化候选、日志和阶段状态
    │   └── tasks/                  # 一次性研究任务
    └── periodic/
        ├── daily/<date>/           # 每日六类 JSON
        ├── weekly/                 # 周聚合、任务、Markdown、图表
        ├── monthly/                # 月度产物
        └── quarterly/              # 季度产物
```

Schema v8 在 SQLite 中保存不可变的 `analysis_artifacts` 分析快照和可更新状态的
`research_agenda_items`；Schema v9 增加带方向、时间、置信度和证据数的 `value_chain_edges`。
Schema v10 增加边证据、议程历史与研究任务；边证据数由关联记录计算，不接受自报计数。
其可读镜像位于行业目录的 `one_time/intelligence/`，包括证据图、
来源观测、产业链情景和知识边界议程；这些是分析结果，不是已审核事实。

`one_time/intelligence/artifacts/<kind>/<artifact_id>/` 是版本化分析包，包含内容、Markdown、
可选 Mermaid 与哈希 Manifest；`latest/<kind>.json` 只在整个包验证通过后更新。根目录旧文件
继续作为兼容视图，不是版本事实源。

`research_tasks` 及 `one_time/intelligence/tasks/<task_id>.json` 保存从研究议程生成的受限任务：
查询式、验收条件、最多读取文档数和结果关联。创建任务不会自动调用模型或产生费用；状态变更
写入 `research_agenda_history`，便于审计是谁在何时推进或关闭了缺口。

某些可选目录（例如 impact 或 deep report）只会在对应功能运行后出现。缺少可选目录不代表行业损坏。
`_jobs/` 是运行审计数据，不是报告正文；App 异常退出后会把遗留的运行中任务收敛为
`interrupted`，但业务步骤是否续跑仍取决于 Search checkpoint。

## 写入责任

| 写入方 | 可以修改的内容 |
|---|---|
| Search | 初始化研究、抓取结果、验证状态、知识结构和报告 |
| App | 行业注册、手动来源、任务配置、批量删除和移入 `_trash` |
| 用户 | 建议只通过 App 或受版本控制的迁移脚本编辑 |

App 与 Search 可能在不同时间写入同一行业，因此不要同时手工修改正在运行的 JSON。复制备份前应停止采集和 App 调度。

结构化写入统一经过 `intdog_core` repository/application service，使用事务、WAL、行业锁、原子兼容写入和版本迁移。JSON 仍作为可移植兼容产物；不应绕过服务同时手工编辑正在运行的文件。

SQLite 是规范事实源，JSON 是可重建的兼容物化视图。来源、每日条目、实体和产业链发生变更时，
数据库事务会同步记录 dirty view；JSON 原子替换成功后才清除标记。若写文件时断电或失败，
后续启动/显式对账从 SQLite 重建对应 JSON。对账方向默认是 SQLite → JSON；只有明确运行
旧数据迁移时才会把现有 JSON 导入 SQLite。
规范层同时保存发布者/转载簇、产业链节点、实体时态角色、别名外部标识和覆盖状态。
`chains.json`、`sources.json` 和 `entities.json` 是可移植兼容视图，不是第二个事实源。

## 每日条目

不同采集器允许扩展字段，但核心字段保持一致：

```json
{
  "title": "事件标题",
  "abstract": "事实摘要，不是营销复述",
  "url": "https://example.com/original",
  "source": "发布者名称",
  "date": "2026-08-29",
  "category": "news",
  "origin": "domestic",
  "source_tier": 1,
  "credibility": "collected",
  "source_count": 1,
  "references": ["https://example.com/original"],
  "ranking_score": 0.78,
  "classification_reason": "与行业关键词及实体匹配"
}
```

`origin` 描述来源地区，不能根据语言或域名草率推断。`references` 应指向支撑该条结论的页面；聚合页和搜索结果页不能替代原始引用。

## 结构化数据模型

数据内核按四层组织：

| 层 | 内容 |
|---|---|
| Raw | 原始响应、网页、附件、抓取时间和内容哈希；只追加，不静默改写 |
| Normalized | 标准化文档、发布者、作者、语言、正文和规范 URL |
| Intelligence | 实体、事件、主张、证据、关系、覆盖空白和冲突 |
| Artifacts | 报告、图表、任务包和导出文件 |

周、月、季是查询和生成窗口，不是三套独立事实。结构化核心数据进入 SQLite；原始网页、Markdown 和大型附件保留在文件系统，JSON 作为交换和兼容格式。

核心对象使用稳定 ID：`source_id`、`document_id`、`entity_id`、`event_id`、`claim_id`、`evidence_id`、`report_id` 和 `run_id`。名称、标题和 URL 都不能单独承担主键职责。

实体与事实还应保存：

- `published_at`、`observed_at`、`retrieved_at` 和 `valid_from/valid_to`，区分发布时间、系统发现时间和现实有效期。
- 中文名、英文名、别名、历史名、外部标识、地域和消歧置信度。
- `supports`、`contradicts`、`qualifies` 三类主张—证据关系。
- 模型/provider、prompt 版本、输入文档 ID、代码版本、参数和人工编辑记录，保证报告可复现。
- 覆盖空白和失败记录；“没有采集到”不能被编码为“该对象不存在”。

## 状态语义

| 状态 | 含义 |
|---|---|
| `candidate` | 搜索候选，尚未完成审计 |
| `collected` | 已抓取，尚未证明事实成立 |
| `verified` / `corroborated` | 有一手材料或多个独立发布者支持 |
| `draft_review_required` | 模型生成的报告草稿，等待人工检查 |
| `reviewed` / `published` | 只能由明确的人工审核流程授予 |

来源等级、可达性、交叉验证和报告审核状态必须分开保存，不能用一个“可信分”替代。

`verified` 应授予具体主张，而不是整篇文档或整个实体。不同来源对同一主张的支持、限定和反驳需要同时保存；转载同一上游材料的多个页面只计算一个独立证据簇。

## 数据格式规则

- JSON 使用 UTF-8；展示名称可保留中文和其他 Unicode 字符。
- 目录标识应稳定且适合跨平台路径；显示名称与目录名不要混为一个字段。
- 日期使用 ISO `YYYY-MM-DD`，时间应带时区。
- 金额必须同时保存数值、币种、口径和截至日期。
- URL 应规范化去重，但不可删除用于审计的原始引用。
- 新增或改名字段时，必须同步 Search 写入端、App 读取端和测试；当前旧文件不保证带 `schema_version`，读取器应兼容缺省值。

数据库使用顺序迁移注册表；旧 JSON 可运行 `python -m src.main migrate-data` 幂等导入。任何算法生成的分数都应保存组成项、算法版本与阈值，不能只留下不可解释的总分。

人类可读的业务约束入口是 [`skill/spec.md`](skill/spec.md)；真正可执行的契约还包括 Search/App 中的 schema、读写逻辑和测试，任何一处都不能单独视为完整事实来源。

## 备份与恢复

1. 停止 App 定期更新和正在运行的 Search 命令。
2. 整体复制 `DomainIntelData/`，保留目录层级和 UTF-8 编码。
3. App 删除的行业或条目优先从 `_trash/` 恢复；清空 `_trash` 后可能无法恢复。
4. 恢复旧备份后运行 `verify` 与 `doctor`，检查缺失字段、断链和来源可达性。

密钥不应写入本目录。API Key 应通过环境变量或系统凭据存储提供；公开仓库前还应检查研究日志中是否意外包含私人 prompt、邮箱或访问令牌。
