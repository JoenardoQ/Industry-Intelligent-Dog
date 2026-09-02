# 能力：情报采集（collect-intel）

从互联网抓取领域信息（新闻 / 学术论文 / 金融政策），按 spec.md 格式写入 DomainIntelData。

## 何时用
- 需要持续监控某个行业的新闻、论文、政策、投融资。
- 需要先积累一批原始情报，再交给 LLM 做深度研究。

## 前置条件
- 已 `pip install -r requirements.txt`（pyyaml / requests / feedparser）。
- `config/settings.yaml` 里填好目标领域与 RSS 源（或用 `--industry` 指定行业档案）。
- 联网。

## 调用方式（在 DomainIntelSearch/ 目录下）

```bash
# 当前主路径：按行业写入六类每日情报
python -m src.main crawl-daily --industry 半导体 --days 1

# 只抓取原始数据（不生成报告）
python -m src.main collect --industry 半导体 --days 3

# 每周金融政策简报
python -m src.main weekly --industry 半导体 --days 7

# 近一年发展轨迹
python -m src.main timeline --industry 半导体 --days 365
```

> `--industry` 可换成 `config/industries/` 下任何档案（ai / new_energy / robotics / biomed），
> 或省略则用 `settings.yaml` 的默认领域。`--days` 是回溯天数窗口。

## 输入
- 行业档案（`config/industries/<id>.yaml`）：关键词、arXiv 分类、跟踪公司、RSS 源。
- `settings.yaml`：新闻源、学术源与输出路径。

## 输出位置
- 规范事实库：`DomainIntelData/intdog.sqlite3`
- 兼容视图：`DomainIntelData/<Industry>/periodic/daily/<YYYY-MM-DD>/<类别>.json`
- 周/月/季产物：`DomainIntelData/<Industry>/periodic/{weekly,monthly,quarterly}/`

`daily/weekly/collect/timeline` 是保留的旧扁平归档命令，产物进入 `_archive/`；新工作流优先使用
`crawl-*`。

## 保证
- 每条记录都带 `url` 和 `references[]`（来源链接），可溯源。
- 按 URL 去重（md5），重复抓取不会产生重复条目。
- 断电可续跑（seen 缓存 + 已归档数据不回滚）。

## 给 agent 的建议
- 批量抓多个行业：循环 `--industry` 逐个跑即可（互不干扰，共用索引）。
- 抓取后接深度研究：见 `research-domain.md`。
