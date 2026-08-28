# IntDog / IIOS 实现状态

更新日期：2026-08-28　版本：2.1 Beta

本文件用于区分“已经由代码执行的能力”“需要 Agent 执行的任务包”和“路线图”。
README 面向使用，DESIGN.md 保留完整设计背景；发生冲突时以代码和本文件为准。

## 已由确定性代码实现

- 按行业独立存储：`DomainIntelData/<行业>/`。
- 新闻、论文、GitHub，以及基于行业+事件双重匹配的融资/招聘/高管候选采集。
- URL 规范化、去重、抓取时间、原文时间、内容哈希和分类命中原因。
- 来源质量与独立印证分离的可信度字段。
- 日/周确定性邮件摘要；邮件默认关闭，密码优先读取环境变量。
- 桌面端调度：按配置时间运行、串行等待结果、仅成功后更新 checkpoint、保留失败详情。
- 行业专属 Agent 工作区：`one_time/research/`；知识图谱数据库位于行业自己的 `db/`。
- 只读 MCP 查询、路径越界保护、2MB 单文件读取限制。
- `doctor` 只读审计数据新鲜度、字段完整性、来源多样性、旧分类和知识实体引用。
- OpenAI Responses API 可选执行模式；其他供应商使用兼容 Chat API。API 调用不是默认行为。
- `execute-tasks` 可执行保存的任务包；输出路径受行业目录边界保护，运行结果保留 manifest。

## 已生成任务包，但不会自动成为正式结论

- 子领域与产业链研究。
- 各产业链层级的中国/全球公司榜单及公司深度画像。
- 技术地图、SOTA 导览、学习路径和历史时间轴。
- 月度、季度、竞争格局、市场和事件影响研究。

这些产物默认状态为 `draft`。执行任务包的 Agent 必须回写引用、数值口径和 claims；
在完成人工复核前，不应作为投资结论或正式数据库事实发布。

## 尚未实现

- 商业数据库级融资、招聘、海关进出口和全球实时行情覆盖。
- 社交平台官方 API 的完整领导层帖子采集。
- 自动实体消歧、公司层级关系、转载链识别和事实冲突仲裁。
- 审核工作台、多人权限、正式发布流、向量检索和服务端高可用部署。
- 文档中曾规划的 PostgreSQL/Qdrant/Neo4j/S3、FastAPI 和 Next.js 产品形态。

## 可信度语义

`credibility` 表示“该记录作为证据的可靠程度”，不是结论正确概率：

- `source_quality`：官方一手、原始记录、主流媒体、普通二手、社区信号的来源先验。
- `source_count`：独立发布者数量，同一域名只计一次。
- `corroborated/verified`：是否至少有两个独立发布者报道同一事件。
- `evidence_type`：证据类型。官方单一来源可以很可靠，但仍不会被标记为多源印证。

## 开发验证

```bash
cd DomainIntelSearch
python -m unittest discover -s tests -v
python -m src.main modules
python -m src.main plan --industry ai --level intermediate
```

联网采集、邮件和付费 LLM API 必须另外做集成测试；单元测试不会触发这些外部调用。
