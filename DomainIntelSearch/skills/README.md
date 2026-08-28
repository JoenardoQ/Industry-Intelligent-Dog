# DomainIntelSearch 能力库（skills）

> 这里存放 DomainIntelSearch 的**可复用能力说明**。每个文件描述一项能力：
> 它做什么、怎么调用、输入输出是什么、结果落到 DomainIntelData 的哪里。
>
> **这些能力不绑定任何 agent 平台**——无论你用 Codex、WorkBuddy、Claude Code、
> 自写脚本，还是直接命令行运行，都遵循同样的约定。agent 只需读对应文件即可上手。

## 能力清单

| 文件 | 能力 | 一句话说明 |
|------|------|-----------|
| `collect-intel.md` | 情报采集 | 从新闻 RSS / arXiv / 金融政策源抓取领域信息，写入 DomainIntelData |
| `research-domain.md` | 深度研究 | 生成"模型无关研究任务包"，由任意 LLM/agent 执行并回写知识库 |
| `knowledge-graph.md` | 知识图谱 | 把研究产物结构化为实体/关系/事件图谱，支持邻居查询 |
| `save-format.md` | 保存格式契约 | 如何读 spec.md，并按约定格式把结果写进 DomainIntelData（含引用溯源） |
| `setup-email.md` | 邮件推送 | 配置 SMTP，把报告推送到邮箱 |

## agent 如何使用（通用三步）

1. **读契约**：先看 `save-format.md`，了解数据要写到哪、写成什么样。
2. **选能力**：按任务从上面挑一个文件，照里面的命令运行。
3. **落数据**：所有产出都进入 `DomainIntelData/`（路径见每个文件末尾「输出位置」）。

## 关键约定（所有能力共用）

- 所有命令都在 `DomainIntelSearch/` 目录下、用 `python -m src.main ...` 运行。
- 所有产出写入 `DomainIntelData/`（文本 + 图片），**不写到别处**。
- 每条情报必须带 `url` 与 `references[]`（来源链接），保证可溯源。
- 抓取哪些领域、保存成什么格式，以 `DomainIntelData/skill/spec.md` 为准（唯一契约）。
