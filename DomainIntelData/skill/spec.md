# DomainIntelData 保存格式规范 (spec)

> 本文件是 DomainIntelSearch 与 DomainIntelApp 之间的**数据格式契约**。
> Search 会读取并展示本规范摘要；可执行的行业与来源配置位于
> `DomainIntelSearch/config/industries/`。改变本文字段后，仍需同步修改 Schema、写入器、UI 与测试。
>
> 本文不是可执行 DSL，单独修改它不会自动改变程序行为。
> 修改规则：标题（`## xxx`）不要改，标题下的内容可以自由增删。

---

## 抓取领域

> DomainIntelSearch 按此列表决定爬取范围。每行一个领域，写成 `显示名 (id)`。
> 留空则沿用 DomainIntelSearch/config/industries/ 里内置的行业档案。
> 现在默认监控以下领域（可增删）：

- 半导体 (semiconductor)
- 人工智能 (ai)

---

## 保存格式

> 数据一律写入 `DomainIntelData/` 内部，**按行业分目录**。约定如下（Search 默认实现）：

根目录: DomainIntelData
行业分目录: <行业文件夹>/            # 例：Chips、AI（由行业档案 data_folder 决定）

# ---- 每个行业文件夹内部 ----
行业-控制: <行业>/control.json        # 定期更新开关 periodic_enabled + 调度记录
行业-信息源: <行业>/sources.json      # 博客/平台/自媒体/新闻/期刊/财报/金融
一次性-知识: <行业>/one_time/knowledge/{industry,chains,entities}.json   # 三层知识
一次性-报告: <行业>/one_time/reports/  # 5年趋势 trend_5y / 2年流行 popular_2y / 半年技术 tech_6m
一次性-深度报告: <行业>/one_time/reports/deep_tasks.json + deep/<rid>.md
             # 四种：quarterly 季度报告 / chain 产业链研究 / landscape 竞争格局 / market 市场分析
             # deep_tasks.json 是 LLM 任务包清单；agent 执行后把 Markdown 回写到 deep/<rid>.md
一次性-竞争格局: <行业>/one_time/landscape/landscape.json + history/<YYYY-MM-DD>.json
             # 四类玩家 tiers{leader,challenger,emerging,declining}（含 mentions/signal/reason）
             # history/ 每日快照，用于跟踪份额/地位变化
一次性-影响分析: <行业>/one_time/impact/events.json            # 检测到的行业事件清单
             <行业>/one_time/impact/<事件slug>/impact.json     # 结构化关联结果
             <行业>/one_time/impact/<事件slug>/analysis_task.json  # 影响分析 LLM 任务包
定期-每日: <行业>/periodic/daily/<YYYY-MM-DD>/<类别>.json   # news/github/funding/hiring/ceo/papers
定期-每周: <行业>/periodic/weekly/<YYYY>-W<ww>.json        # 行业总结
定期-每月: <行业>/periodic/monthly/<YYYY>-<MM>.json        # 产业分析
定期-每季: <行业>/periodic/quarterly/<YYYY>-Q<q>.json      # 财报分析
旧版扁平归档: _archive/                # daily/weekly 等旧命令写入处
删除回收站: _trash/                    # 删除的定期产物（可恢复）

# ---- 单条定期情报的字段（JSON 对象） ----
字段-title: 标题
字段-abstract: 摘要（界面在标题下显示）
字段-url: 原文链接（必须有，用于溯源与「打开」）
字段-source: 来源（如 36氪 / GitHub / arXiv）
字段-date: 日期 YYYY-MM-DD
字段-category: 类别（news / github / funding / hiring / ceo / papers）
字段-references: 引用来源数组 [{title,url,source,date}]

# ---- 多源交叉验证字段（verify 命令自动回写，不人工填） ----
字段-credibility: 可信度评分 0-1（来源质量先验 + 独立来源印证奖励，诚实封顶 0.95）
字段-source_quality: 来源质量先验（官方一手 0.90 / 原始记录 0.85 / 主流媒体 0.72 /
             普通二手来源 0.50 / 社区信号 0.35）
字段-evidence_type: official_primary | primary_record | established_media |
             secondary_source | community_signal
字段-credibility_label: 高(>=0.75) | 中(>=0.5) | 低(<0.5)
字段-source_count: 独立发布者数（同一域名只算一个发布者）
字段-verified: true 表示被 >=2 个独立来源印证
说明-references: verify 后自动填入"报道同一事件的其它来源"（不含自身）

# ---- 竞争格局单条玩家（landscape.json tiers 内） ----
玩家-name: 公司名
玩家-mentions: 最近一天情报中的提及次数
玩家-signal: tracked_company | rising_mentions | recent_funding | decline_news | known_entity
玩家-reason: 归类理由（人读）

# ---- 事件影响分析（impact.json 顶层字段） ----
影响-event: 事件描述（如 "美国限制GPU出口"）
影响-affected_companies: 受影响公司名数组（affected_detail 含逐家命中原因）
影响-affected_chains: 关联产业链层级名数组
影响-related_papers: [{title,url,source,date,overlap}]   # overlap=主题重合度
影响-related_policies: [{title,url,source,date,policy_signals,credibility_label}]
影响-analysis_task: 叙事性影响分析的 LLM 任务包（prompt + output_file）

# ---- 三层知识结构（entities.json 单条实体） ----
实体-name: 名称（如 英伟达 / 港科广吕杨迪组）
实体-type: company(企业) | research_group(高校/研究组)
实体-chain: 所属产业链层级（如 设计验证 / 制造 / 封装）
实体-country: 国家/地区
实体-url: 链接（可选）

# ---- 图片命名约定 ----
图片命名: images/<行业>/<YYYY-MM-DD>_<标题slug>.<png|jpg|webp>
图片说明: 同目录 .md 备注或在 JSON 里以 images 字段引用相对路径

# ---- 跨平台约束 ----
文件名安全字符: 文件名只用 ASCII 安全字符，避免跨系统编码问题
行业自成一体: 每个 <行业>/ 文件夹独立，可单独拷贝某个行业

---

## 用户待规定

> ↓↓↓ 由你（DomainIntelData 所有者）在这里补充/修改，覆盖上面的默认约定。
> Search 与 App 都会尊重你写的内容。常见可改项：

1. **要监控的领域清单**：在上方「抓取领域」里增删即可。
2. **字段增减**：是否要加 `images`、`tags`、`confidence`、`author` 等字段。
3. **目录/文件名约定**：是否改用 `领域/日期/类别` 或 `日期/领域` 的层级。
4. **是否需要 SQLite**：只要 JSON+Markdown 文本、不要 db/ 也可（告诉 Search 关闭）。
5. **图片策略**：是否抓取原文配图、是否压缩、命名规则。
6. **Markdown 优先**：若你更想要 `domains/<领域>/<日期>.md` 的可读报告而不是 JSON，
   在这里写明「每条情报一个 md 文件」，Search 会按此输出。

（本区块当前为模板，等你填写具体要求后，Search 的写入行为会随之调整。）
