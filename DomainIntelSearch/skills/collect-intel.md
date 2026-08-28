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
# 每日情报：抓取 + 生成日报（HTML）+ 归档到 DomainIntelData
python -m src.main daily --industry 半导体 --days 1

# 只抓取原始数据（不生成报告、不发邮件）
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
- `settings.yaml`：邮件、学术源、输出路径。

## 输出位置（全部在 DomainIntelData/ 内）
- 结构化条目：`data/<年>/<YYYY-MM-DD>/<类别>.json`
- 报告：`reports/daily|weekly|timeline/<文件>.html`
- 查询库：`db/intelligence.db`
- 总索引：`index/master_index.json`

## 保证
- 每条记录都带 `url` 和 `references[]`（来源链接），可溯源。
- 按 URL 去重（md5），重复抓取不会产生重复条目。
- 断电可续跑（seen 缓存 + 已归档数据不回滚）。

## 给 agent 的建议
- 批量抓多个行业：循环 `--industry` 逐个跑即可（互不干扰，共用索引）。
- 抓取后接深度研究：见 `research-domain.md`。
