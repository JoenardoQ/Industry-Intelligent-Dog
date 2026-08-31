# DomainIntelData 数据契约

> 本文件是人类可读的配置摘要，不是可执行 DSL。代码中的 Schema、迁移、Repository 和测试共同组成完整契约。改变字段后必须同步写入端、读取端、迁移和测试。

## 抓取领域

- 半导体 (semiconductor)
- 人工智能 (ai)

列表可增删；未列出的行业仍可通过行业档案或 App 创建。

## 保存格式

结构化事实库: intdog.sqlite3
数据库模式: SQLite WAL + 外键 + FTS5 + 顺序迁移 + 行业任务锁
行业目录: <行业文件夹>/
控制文件: <行业>/control.json
来源兼容视图: <行业>/sources.json
知识兼容视图: <行业>/one_time/knowledge/{industry,chains,entities}.json
报告: <行业>/one_time/reports/
每日兼容视图: <行业>/periodic/daily/<YYYY-MM-DD>/<类别>.json
周期产物: <行业>/periodic/{weekly,monthly,quarterly}/
回收站: _trash/
旧版归档: _archive/

核心对象: Industry | Source | Document | Entity | Relation | Event | Claim | Evidence | Run
稳定标识: source_id | document_id | entity_id | event_id | claim_id | evidence_id | run_id
每日类别: news | github | funding | hiring | ceo | papers
来源类别: official | associations | blogs | platforms | self_media | news | journals | financials | finance

文档必需字段: title | url | source | category | date
文档时间: published_at | observed_at | retrieved_at
事实有效期: valid_from | valid_to
证据状态: candidate | collected | verified | corroborated | rejected
审核状态: unreviewed | draft_review_required | reviewed | published
证据关系: supports | contradicts | qualifies

兼容可信度分数: credibility / credibility_score 为 0-1 数字
状态与分数分离: evidence_status 不能用总分替代
独立发布者: 同一域名、通讯社或共同上游只计算一个发布者簇
引用: references 必须指向支撑主张的原始页面，搜索结果页不能替代原文
金额: value + currency + unit + definition + as_of
时间: ISO 8601；时间点带时区
文本: UTF-8，显示名称允许 Unicode

知识模型: 全局规范实体 + 行业角色 + 多个产业链位置
实体范围: company | research_group | regulator | association | person | technology | product | facility | supply_chain_activity
关系范围: participates_in | supplies | competes_with | part_of | develops | regulates | invests_in | acquired | partners_with
开放世界: 未发现不等于不存在；保存候选、排除项、空白节点和失败记录

写入边界: App 和 Search 的业务写入统一经过 intdog_core application service
迁移: python -m src.main migrate-data；幂等导入且不删除旧文件
删除: 结构化记录软删除；兼容文件先备份到 _trash
密钥: 禁止写入 DomainIntelData；使用环境变量或系统凭据存储

## 用户待规定

可在这里补充特定行业的来源偏好、监控频率、报告语言、保留周期和人工审核规则。自定义要求不能降低路径安全、引用、证据状态、迁移和可恢复删除等系统底线。
