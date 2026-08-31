# 能力：知识图谱

把企业、研究组、人物、技术、产品、产业链节点和事件写入共享
`DomainIntelData/intdog.sqlite3`。

```bash
python -m src.main kg --industry 半导体 --build
python -m src.main kg --industry 半导体 --entity 台积电 --depth 2
```

- 全局规范实体、别名和外部标识；
- 行业中的多个角色和产业链位置；
- 带 `valid_from/valid_to`、置信度和证据数的时态角色；
- 方向关系、事件、主张及 supports/contradicts/qualifies 证据。

`one_time/knowledge/chains.json` 和 `entities.json` 是可移植视图，由 dirty-view 对账从
SQLite 重建。不要使用旧的 `industry/<行业>/` 或 `db/intelligence.db` 路径。
