# 能力：深度研究（research-domain）

为某个行业生成一套"模型无关研究任务包"，交给**任何** LLM/agent 执行，
执行结果回写进 DomainIntelData 的行业知识库。

## 设计原则（为什么不绑定平台）
本程序**不直接调 LLM**，而是把研究拆成一个个任务包（`tasks/*.json`，含完整 prompt）。
你把这些任务包喂给任何模型——Codex、WorkBuddy、Claude Code、自写脚本调 API——都行。
模型可自由替换，系统不重写。

## 何时用
- 需要对某行业做一次系统研究（产业链、龙头公司、技术路线、高管、时间轴等）。

## 调用方式

```bash
# 1) Planner：生成整套研究计划（任务 DAG + 全部任务包）
python -m src.main plan --industry 半导体 --level beginner --region global

# 2) 运行单个研究 Agent（产出该方向的任务包）
python -m src.main agent --name company --industry 半导体
```

研究 Agent 共 7 个：`industry`（产业概览）/ `value_chain`（产业链）/ `company`（公司）/
`technology`（技术）/ `learning`（学习路径）/ `timeline`（时间轴）/ `leadership`（高管）。
可用 `python -m src.main modules` 查看。

## 任务包怎么执行（agent 中立）
1. 打开 `DomainIntelData/<Industry>/one_time/research/tasks/<agent>.json`。
2. 里面是若干任务，每个任务有 `summary`（要做什么）和 `extra.prompt`（完整提示词）。
3. 把 prompt 交给你的 LLM/agent 执行，把结果写成 Markdown 或 JSON。
4. 按 `extra.output_file` 回写到 `DomainIntelData/<Industry>/one_time/research/`。

> 引用规范（任务包已内置）：结论用 `[n]` 标注，文末附 `references[]`；
> JSON 输出必须带 `source_url`/`sources` 字段。保证每条结论可溯源。

## 输出位置
- 任务包：`DomainIntelData/<Industry>/one_time/research/tasks/*.json`
- 回写知识库：`DomainIntelData/<Industry>/one_time/research/`（md / json / mmd）
- 计划 DAG：`DomainIntelData/<Industry>/one_time/research/plan.mmd`

## 后续
研究产物可进一步结构化为知识图谱，见 `knowledge-graph.md`。
