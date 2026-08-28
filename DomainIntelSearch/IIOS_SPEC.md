# Industry Intelligence Operating System (IIOS) — 产品规格文档

**Version**: 1.1 | **Status**: Beta（确定性采集已实现；深度研究主要为待执行任务包）

> 本文档描述产品目标与 Agent 契约。真实完成度见仓库根目录 `IMPLEMENTATION_STATUS.md`；
> 代码与该状态文件优先于本文中的历史路线图描述。

---

## 1. Objective（目标）

开发一个 AI 驱动的行业情报操作系统（IIOS）：针对任意行业（半导体 / AI / 机器人 / 量子计算 /
生物医药 / 新能源 / 金融等）**自动构建知识体系、持续追踪行业动态、形成长期更新的行业数据库**，
为 Beginner / Intermediate / Expert 三级用户提供学习路径、研究素材与投资参考。

系统属性：**长期运行、模块化、可扩展、自动化**。不是一次性 Prompt，是一个软件产品。

## 2. Input（输入）

所有入口统一接受四个参数（CLI / 配置文件 / API 三处一致）：

| 参数 | 取值 | 默认 |
|---|---|---|
| `--industry` | 任意行业名（如 semiconductor / 人工智能） | settings.yaml `domain.name` |
| `--level` | beginner / intermediate / expert | `domain.depth` |
| `--region` | global / china / us / europe | `iios.region` |
| `--lang` | zh / en / both | `output.language` |

```bash
python -m src.main plan --industry 半导体 --level beginner --region global
```

## 3. Output（输出）

### 3.1 统一输出 Schema（所有 Agent 强制遵守）

定义于 `src/schema.py::IIOSRecord`，所有 Agent 产出必须序列化为：

```json
{
  "id": "sha1", "type": "news|paper|company|policy|...",
  "title": "", "summary": "", "source": "",
  "confidence": 0.95, "tags": [], "region": "", "industry": "",
  "published": "YYYY-MM-DD", "last_updated": "ISO8601",
  "references": [{"title":"","url":""}],
  "impact": {"companies": [], "technologies": [], "importance": 1-5},
  "extra": {}
}
```

### 3.2 归档目录（`D:\IntDog\DomainIntelligence`）

```
DomainIntelligence/
├── data/<year>/<date>/{news,academic,finance,policy,startup}.json   # 原始数据（时间×类别）
├── industry/<industry>/            # IIOS 行业知识库（本次新增）
│   ├── overview.md  value_chain.md  value_chain.mmd
│   ├── companies/   learning/      technologies/
│   ├── timeline/    knowledge_graph/
│   └── reports/
├── reports/{daily,weekly,briefs}/  # 日报/周报 HTML
├── db/intelligence.db              # SQLite（articles + 5 张 IIOS 新表）
├── index/master_index.json         # 可移植双向索引
└── app/                            # 移动端 PWA
```

## 4. 总体架构

```
                 User (CLI / Desktop / API / 自动化)
                          │
                    Planner Agent            ← src/agents/planner.py
                          │  生成 Task DAG
 ┌────────────────────────┴─────────────────────────┐
 │ 研究组（LLM 分析型，产出结构化提示 → WorkBuddy 执行）│
 │   Industry / ValueChain / Company / Technology     │
 │   Learning / Timeline                              │
 │ 情报组（爬虫型，确定性代码直接产出数据）             │
 │   News / Paper / Policy / Finance / Startup / Social│
 │ 综合组                                             │
 │   KnowledgeGraph / Reporter                        │
 └────────────────────────┬─────────────────────────┘
                          │ IIOSRecord (统一 Schema)
                  Knowledge Database
        (SQLite: articles/entities/edges/events/companies/scores)
                          │
          Desktop GUI + Email + PWA + query CLI
```

**设计原则**：
1. **爬虫与分析分离**：情报组是确定性代码（可测试、可重跑）；研究组产出"分析任务包"
   （结构化 Prompt + 数据上下文），由 WorkBuddy/Codex/任意 LLM 执行后回写归档。
2. **Agent 只通过 Schema 交换数据**，禁止互相 import 内部实现。
3. **本地优先**：数据与索引保存在本地 SQLite + JSON；联网采集、邮件和可选 LLM 执行仍依赖外部服务。

## 5. Agent 职责（15 个）

| Agent | 文件 | 类型 | 职责与输出 |
|---|---|---|---|
| Planner | agents/planner.py | 调度 | 按 industry/level/region 生成任务 DAG（JSON），编排全部 Agent |
| Industry | agents/research.py | LLM | 行业概述/规模/历史/玩家/趋势/挑战/机会/政策影响 → overview.md |
| ValueChain | agents/research.py | LLM+模板 | 标准化产业链（内置半导体/AI/新能源/机器人/生物医药模板）→ Mermaid + JSON |
| Company | agents/research.py | LLM | 每层级 Top10 中国 + Top10 全球；24 项指标（见 §6）+ 雷达评分 |
| Technology | agents/research.py | LLM | 技术方向→子方向→知识模块→关键论文/教材→未来发展 |
| Learning | agents/research.py | LLM | 按 level 生成带依赖关系的学习 DAG（Mermaid）+ Roadmap/Checklist/预估时长 |
| Timeline | agents/research.py | LLM | 产业/公司/技术/政策四类时间轴 → events 表 + Mermaid timeline |
| News | crawlers/news_crawler.py | 爬虫 | RSS/NewsAPI/GNews；输出含影响公司/技术/重要度/可信度 |
| Paper | crawlers/academic_crawler.py | 爬虫 | arXiv + Semantic Scholar；分类 Survey/SOTA/Application |
| Policy | crawlers/finance_crawler.py | 爬虫 | 政府 RSS；分类出口管制/投资/关税/补贴/科研经费 |
| Finance | crawlers/finance_crawler.py | 爬虫 | 财经 RSS + AKShare 市值；财报期由 LLM 分析任务补充 |
| Startup | crawlers/news_crawler.py | 爬虫 | HN/ProductHunt/36Kr 融资信号（Crunchbase 等需 Key，见路线图） |
| Social | agents/research.py | LLM+爬虫 | CEO/CTO/创始人发言追踪（受平台 API 限制，RSS 近似） |
| KnowledgeGraph | agents/kg.py | 代码 | 从 articles/companies 抽取实体关系 → entities/edges 表 + Mermaid |
| Reporter | generators/digest_generator.py | 代码 | 日报/周报/深度报告 HTML + 邮件推送 |

## 6. 公司分析指标（24 项）

Overview / 成立时间 / CEO / 员工数 / 市值 / 营收 / 净利润 / 毛利率 / 现金流 / PE / PS / PB /
客户 / 供应商 / 竞争对手 / 产品 / 专利 / 市场份额 / 优势 / 劣势 / 护城河 / 进出口 /
供应链位置 / 最新战略 / 风险 / 未来展望 / Confidence Score

评分雷达（scores 表，0-10）：Innovation / Financial / SupplyChain / Talent / Research / Market / Policy / Overall

## 7. 数据库 Schema（SQLite `db/intelligence.db`）

```sql
-- 既有
articles(uid PK, title, url, source, category, published, summary, lang, authors, date_added);
-- IIOS 新增
entities(id PK, name, etype /*company|technology|person|product|org|policy*/,
         industry, region, summary, extra_json, updated_at);
edges(id PK, src_id, dst_id, relation /*supplies|competes|develops|invests|uses|regulates|member_of*/,
      weight, source, updated_at);
events(id PK, etype /*industry|company|technology|policy*/, subject, date, title,
       description, importance, source_url);
companies(id PK, name, name_en, industry, tier /*产业链层级*/, region, is_china,
          metrics_json /*24项指标*/, updated_at);
scores(company_id, dimension, score, rationale, updated_at,
       PRIMARY KEY(company_id, dimension));
```

Phase 2 迁移目标：PostgreSQL（结构化）+ Qdrant（向量/RAG）+ Neo4j（图）+ S3（原文）。
迁移时保持字段名不变，`ArchiveStore` 是唯一存储入口，替换实现即可。

## 8. 任务编排（DAG）与调度

Planner 产出的标准 DAG（`plan` 命令生成 JSON）：

```
value_chain → industry_overview → company_research → scoring
technology_map → learning_path
(并行) news / paper / policy / finance / startup 爬取 → kg_build → report
```

调度层级（settings.yaml `iios.schedule` + WorkBuddy 自动化）：

| 频率 | 任务 |
|---|---|
| 每天 08:00 | 新闻/论文/CEO发言/GitHub → 日报邮件 |
| 每周一 09:00 | 行业总结 + 政策总结 + 投融资总结 |
| 每月 1 日 | 财报跟踪 + 技术趋势 + 竞争分析（LLM 任务包） |
| 每季度 | 深度行业报告 + 公司排名 + 市场预测（LLM 任务包） |

## 9. API 设计（Phase 2，FastAPI）

```
GET /industry?name=            GET /companies?industry=&tier=&region=
GET /papers?days=              GET /news?days=&importance=
GET /timeline?etype=&subject=  GET /technology?industry=
GET /policy?category=          GET /learning?level=
GET /finance?company=          GET /graph?entity=&depth=
```

Phase 1 等价能力：`python -m src.main query|kg|serve`（SQLite + 局域网 HTTP）。

## 10. 评估指标（Eval）

- 爬虫：每日抓取量 > 0；去重率；来源可用率（失败源自动降级）
- 数据：新闻多源交叉验证覆盖率（≥2 源 → confidence ≥ 0.8）
- 分析：LLM 任务包引用来源数 ≥ 3；公司指标填充率
- 系统：调度成功率；归档索引一致性（路径 100% 可解析）

## 11. 技术栈（Beta 当前能力 / 后续目标）

| 层 | Beta 当前能力 | 后续服务化目标 |
|---|---|---|
| 编排 | Planner Agent + WorkBuddy 自动化 | LangGraph / OpenAI Agents SDK |
| LLM | WorkBuddy（任务包模式） | GPT/Claude/Gemini 可配置 |
| 采集 | requests + feedparser + RSS | Firecrawl / Playwright / Tavily |
| 存储 | SQLite + JSON + master_index | PostgreSQL + Qdrant + Neo4j + S3 |
| 队列/调度 | 线程 + WorkBuddy 自动化 | Celery / Temporal + APScheduler |
| 前端 | Tkinter 桌面 + PWA | Next.js Dashboard |
| 可视化 | Mermaid（.mmd 文件） | ECharts + Graphviz |
| 邮件 | SMTP（QQ/163/Gmail） | Resend / SendGrid |
| 监控 | 运行日志 + worker_state.json | Langfuse + Prometheus |
| 工具协议 | — | MCP Server 封装全部数据源 |

## 12. 开发路线图

- **Beta（部分完成）**：采集 + 归档 + Agent 任务包 + KG(SQLite) + 桌面程序 + 本地调度；生产级审核与数据覆盖尚未完成
- **Phase 2**：多源交叉验证（Impact Engine 雏形）、FastAPI、向量化 RAG、Crunchbase/SEC 数据源
- **Phase 3**：Neo4j 知识图谱、Next.js Dashboard、竞争格局追踪（Leader/Challenger/Emerging/Declining）
- **Phase 4**：MCP Server 化全部数据源、深度研究报告生成器（季度报告/专题研究）

## 13. 对 Coding Agent 的约束（System Prompt 摘要）

1. 新功能必须归属于某个 Agent，禁止写"什么都干"的大脚本。
2. 所有数据落地必须经过 `ArchiveStore`，输出必须符合 `IIOSRecord` Schema。
3. 爬虫必须容错降级（单源失败不影响整体），必须去重（seen 缓存）。
4. 不硬编码行业：一切从 industry/level/region/lang 参数派生。
5. 改动后必须运行 `python -m src.main plan --industry 测试` 冒烟测试。
