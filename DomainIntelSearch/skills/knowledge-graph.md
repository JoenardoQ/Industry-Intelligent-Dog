# 能力：知识图谱（knowledge-graph）

把研究产物（公司、技术、人物、事件）结构化为实体 / 关系 / 事件图谱，
存入 DomainIntelData 的 SQLite，可查询实体邻居子图。

## 何时用
- 深度研究回写完成后，想把零散结论连成可查询的关系网。

## 调用方式

```bash
# 构建 / 更新图谱（读取 DomainIntelData/industry/<行业>/ 下回写文件）
python -m src.main kg --industry 半导体 --build

# 查询某实体的邻居子图（默认深度 1，可用 --depth 调）
python -m src.main kg --industry 半导体 --entity 台积电 --depth 2
```

## 数据来源
- `industry/<行业>/companies/*.json` → 公司（companies 表 + scores 表）
- `industry/<行业>/value_chain.json` → 产业链层级 → 实体与上下游关系
- `industry/<行业>/timeline*.json` → 事件（events 表）
- 其余 md 中被解析到的实体 → entities / edges

## 输出位置
- 结构化图谱：`DomainIntelData/db/intelligence.db`（entities / edges / events / companies / scores 表）
- 可视化：`DomainIntelData/industry/<行业>/knowledge_graph/graph.mmd`（Mermaid）

## 保证
- 同一实体按 `类型|名称` 归一（不重复建点）。
- 同一关系重复出现只累加权重，不重复建边。
- 图谱随研究产物增量更新，可反复安全执行。

## 给 agent 的建议
- 想改图谱结构：改回写 JSON 里的 `companies/edges/events` 字段即可，重建时自动合并。
