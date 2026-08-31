# IntDog 领域情报系统 · 完整设计文档

> **注意**：本文包含目标架构和历史设计，并不表示所有条目都已落地。
> 当前实现状态以 [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) 为准。
> 其中 `industry/<行业>`、行业独立 `db/`、`ArchiveStore` 唯一入口、固定 Top 10 和
> 单一三层知识树属于 v1/v2 历史方案；v3 以 [`IIOS_SPEC.md`](DomainIntelSearch/IIOS_SPEC.md)
> 的共享 `intdog_core`、开放世界覆盖、规范实体与 Claim–Evidence 模型为准。
> 当前 Schema v10 还包含发布者/转载簇、产业链节点、可取证有向边、时态实体角色、外部标识、
> Intelligence Lab 分析快照、议程历史和有预算边界的研究任务；
> App 可通过 application service 写入，并使用持久化 Job Manager/任务中心。后文与此冲突时
> 一律视为历史记录。

> **版本**: 2.0 | **日期**: 2026-07-31 | **目标行数**: 5000–10000 行
>
> 本文档是 IntDog / IIOS（Industry Intelligence Operating System）的完整设计说明，
> 涵盖架构、数据库 Schema、全部 Agent Prompt、目录结构、工作流、API 定义、部署方案与开发计划。

---

## 目录

1. [系统架构概述](#1-系统架构概述)
2. [目录结构](#2-目录结构)
3. [数据模型与 Schema](#3-数据模型与-schema)
   - 3.1 SQLite 数据库表
   - 3.2 JSON 文件结构
   - 3.3 三层知识结构
   - 3.4 定期监控数据结构
4. [Agent 系统与 Prompt 全集](#4-agent-系统与-prompt-全集)
   - 4.1 Agent 架构设计
   - 4.2 研究组 Agent（7 个）
   - 4.3 Planner Agent
   - 4.4 KnowledgeGraph Agent
   - 4.5 深度分析 Prompt 模板集
5. [核心工作流](#5-核心工作流)
   - 5.1 一次性深度研究（IIOS 多 Agent）
   - 5.2 定期监控（日/周/月/季）
   - 5.3 信息源发现
   - 5.4 行业报告生成
6. [CLI API 参考](#6-cli-api-参考)
7. [部署方案](#7-部署方案)
8. [开发路线图](#8-开发路线图)

---

## 1. 系统架构概述

### 1.1 五部分分离原则

```
IntDog/
├── IntDog.exe              ① 可执行入口（PyInstaller 打��，当前版本暂不打包）
├── README.md               ② 使用说明（面向 GitHub + 初学者）
├── DomainIntelSearch/      ③ 抓取引擎（唯一需要联网、使用 LLM/agent 的模块）
├── DomainIntelData/        ④ 数据层（只存领域文本 + 图片 + skill 格式契约）
└── DomainIntelApp/         ⑤ 图形界面（纯 UI：读取/删除 DomainIntelData，不做抓取）
```

**核心设计原则**：
- **③ → ④**：Search 抓取后按行业分目录写入 Data。
- **⑤ → ④**：App 只读 Data，可删除条目，不做任何抓取或编辑。
- **④**：唯一事实来源，`skill/spec.md` 是 Search 与 App 之间的唯一契约。
- **③**：不绑定任何特定 agent 平台（Codex / WorkBuddy / Claude Code 皆可），
  深度研究以"模型无关任务包"形式产出，LLM 可随时替换。

### 1.2 数据流全景

```
                 ┌─────────────────────┐
                 │  config/industries/  │  行业档案
                 │  settings.yaml       │  主配置
                 └─────────┬───────────┘
                           ▼
  ┌──────────────── DomainIntelSearch ──────────────────┐
  │  CLI 入口 (main.py)                                  │
  │  ├─ orchestrator.py   主编排（旧版扁平归档）          │
  │  ├─ industry_store.py  按行业分目录存储               │
  │  ├─ knowledge_model.py  三层知识结构                  │
  │  ├─ scheduler.py  定期调度（日/周/月/季）             │
  │  ├─ report_tasks.py  行业报告任务包                   │
  │  ├─ source_discovery.py  信息源发现                   │
  │  ├─ crawlers/                                         │
  │  │   ├─ news_crawler.py     RSS/NewsAPI/GNews         │
  │  │   ├─ academic_crawler.py  arXiv/Semantic Scholar   │
  │  │   ├─ finance_crawler.py   金融/政策/行情            │
  │  │   └─ periodic_crawlers.py  GitHub/融资/招聘/CEO    │
  │  ├─ agents/                                           │
  │  │   ├─ planner.py      任务 DAG 编排                │
  │  │   ├─ research.py     7 个研究 Agent               │
  │  │   └─ kg.py           知识图谱构建                  │
  │  ├─ services/                                         │
  │  │   ├─ archive_store.py  旧版扁平归档(SQLite+JSON)   │
  │  │   └─ email_service.py  SMTP 邮件推送               │
  │  └─ modules/            17 个可组合功能模块            │
  └──────────────────────┬──────────────────────────────┘
                         │  写入
                         ▼
  ┌──────────────── DomainIntelData ──────────────────────┐
  │  skill/spec.md          ★ 唯一契约（抓取领域+保存格式）│
  │                                                        │
  │  <行业文件夹>/             例：Chips / AI               │
  │  ├─ control.json           定期更新开关                │
  │  ├─ sources.json           信息源                      │
  │  ├─ one_time/              一次性深度爬取              │
  │  │   ├─ knowledge/         三层知识结构                │
  │  │   │   ├─ industry.json                              │
  │  │   │   ├─ chains.json                                │
  │  │   │   └─ entities.json                              │
  │  │   └─ reports/           行业报告（5年/2年/半年）     │
  │  └─ periodic/              定期监控（与一次性分开）     │
  │      ├─ daily/<日期>/<类别>.json                        │
  │      ├─ weekly/ / monthly/ / quarterly/                │
  │                                                        │
  │  _archive/                 旧版扁平归档（legacy）       │
  │  _trash/                   删除回收站                   │
  └──────────────────────┬───────────────────────────────┘
                         │  读取/删除
                         ▼
  ┌──────────────── DomainIntelApp ───────────────────────┐
  │  desktop/                       纯 UI（零 src 依赖）   │
  │  ├─ dataio.py        直连 DomainIntelData JSON         │
  │  ├─ app.py           五标签交互界面                    │
  │  │   ├─ 每日情报       卡片：标题+摘要+链接+删除       │
  │  │   ├─ 知识结构       三层树（行业→产业链→实体）       │
  │  │   ├─ 定期产物       周/月/季报告+删除               │
  │  │   ├─ 信息源         博客/平台/自媒体/新闻/期刊/财报  │
  │  │   └─ 行业报告       5年趋势/2年流行/半年技术         │
  │  └─ main.py          启动入口                          │
  │                                                        │
  │  功能：                                                 │
  │  · 行业下拉选择（从 DomainIntelData 文件夹自动发现）    │
  │  · 定期更新开关（写 control.json → 调度线程自动抓取）   │
  │  · 删除（每日条目从 JSON 移除；定期产物移入 _trash/）   │
  │  · 无编辑功能（按设计需求）                             │
  └───────────────────────────────────────────────────────┘
```

### 1.3 核心模块职责矩阵

| 模块 | 文件 | 联网 | LLM | 写 Data | 读 Data | UI |
|------|------|:---:|:---:|:------:|:------:|:--:|
| orchestrator | `src/orchestrator.py` | ✅ | ❌ | ✅(旧) | ❌ | ❌ |
| industry_store | `src/industry_store.py` | ❌ | ❌ | ✅ | ✅ | ❌ |
| knowledge_model | `src/knowledge_model.py` | ❌ | ❌ | ✅ | ✅ | ❌ |
| scheduler | `src/scheduler.py` | ✅ | ❌ | ✅(定期) | ✅ | ❌ |
| report_tasks | `src/report_tasks.py` | ❌ | ❌(任务包) | ✅(任务包) | ❌ | ❌ |
| source_discovery | `src/source_discovery.py` | ❌ | ❌(任务包) | ✅(种子+任务包) | ❌ | ❌ |
| crawlers/* | `src/crawlers/` | ✅ | ❌ | ❌ | ❌ | ❌ |
| agents/* | `src/agents/` | ❌ | ❌(任务包) | ✅(任务包) | ✅(归档) | ❌ |
| archive_store | `src/services/archive_store.py` | ❌ | ❌ | ✅(旧) | ✅ | ❌ |
| DomainIntelApp | `desktop/app.py` | ❌ | ❌ | ✅(删除) | ✅ | ✅ |

---

## 2. 目录结构

### 2.1 项目根目录（位置无关，生产环境位于 WSL home）

```
IntDog/
├── DESIGN.md                    # ★ 本设计文档
├── README.md                    # 使用说明（面向 GitHub + 初学者）
│
├── DomainIntelSearch/           # ③ 抓取引擎
│   ├── src/
│   │   ├── main.py              #   命令行入口（全部 CLI 命令）
│   │   ├── orchestrator.py      #   主编排（旧版 daily/weekly/timeline）
│   │   ├── industry_store.py    #   按行业分目录存储（新版核心）
│   │   ├── knowledge_model.py   #   三层知识结构模型
│   │   ├── source_discovery.py  #   信息源发现（种子源 + LLM 任务包）
│   │   ├── scheduler.py         #   定期监控调度器
│   │   ├── report_tasks.py      #   三种行业报告任务包
│   │   ├── spec_loader.py       #   读取 DomainIntelData/skill/spec.md
│   │   ├── schema.py            #   IIOSRecord 数据结构
│   │   ├── profiles.py          #   行业档案加载
│   │   ├── utils.py             #   通用工具（SeenStore/article_id/ensure_dir…）
│   │   ├── crawlers/
│   │   │   ├── base.py          #     Article + BaseCrawler
│   │   │   ├── news_crawler.py  #     RSSCrawler / NewsAPI / GNews / NewsAggregator
│   │   │   ├── academic_crawler.py  # ArxivCrawler / SemanticScholar / AcademicAggregator
│   │   │   ├── finance_crawler.py   # PolicyNews / FinanceNews / StockData / FinanceAggregator
│   │   │   └── periodic_crawlers.py # GitHub / 融资 / 招聘 / CEO（关键词过滤型）
│   │   ├── agents/
│   │   │   ├── __init__.py      #     AGENT_REGISTRY (9 个)
│   │   │   ├── base.py          #     AgentContext / BaseAgent
│   │   │   ├── planner.py       #     PlannerAgent + STANDARD_DAG
│   │   │   ├── research.py      #     7 个研究 Agent + VALUE_CHAIN_TEMPLATES
│   │   │   └── kg.py            #     KnowledgeGraphAgent
│   │   ├── services/
│   │   │   ├── archive_store.py #     旧版扁平归档（SQLite + JSON + index）
│   │   │   ├── email_service.py #     SMTP 邮件推送
│   │   │   └── worker.py        #     后台常驻爬虫线程（桌面程序用）
│   │   ├── generators/
│   │   │   └── digest_generator.py   # 日报/周报/轨迹 HTML 生成
│   │   ├── analyzers/
│   │   │   └── prompts.py       #     分析 Prompt 模板集合（8 个方法）
│   │   └── modules/             #     17 个可组合功能模块
│   ├── config/
│   │   ├── settings.yaml        #   主配置文件
│   │   └── industries/          #   行业档案（semiconductor/ai/new_energy/robotics/biomed）
│   ├── skills/                  #   Agent 中立能力说明
│   │   ├── README.md
│   │   ├── collect-intel.md
│   │   ├── research-domain.md
│   │   ├── knowledge-graph.md
│   │   ├── save-format.md
│   │   └── setup-email.md
│   ├── IIOS_SPEC.md             #   IIOS 多 Agent 规格（原始设计）
│   ├── requirements.txt         #   依赖（pyyaml/requests/feedparser）
│   └── README.md
│
├── DomainIntelData/             # ④ 数据层
│   ├── skill/
│   │   └── spec.md              #   ★ 唯一契约（抓取领域 + 保存格式）
│   ├── <行业文件夹>/             #   每个行业独立文件夹（例：Chips / AI）
│   │   ├── control.json         #   定期更新开关 + 调度记录
│   │   ├── sources.json         #   信息源（7 类）
│   │   ├── one_time/            #   一次性深度爬取
│   │   │   ├── knowledge/       #     三层知识结构
│   │   │   │   ├── industry.json
│   │   │   │   ├── chains.json
│   │   │   │   └── entities.json
│   │   │   └── reports/         #     行业报告
│   │   │       └── tasks.json   #       三份报告任务包
│   │   └── periodic/            #   定期监控（与 one_time 分开）
│   │       ├── daily/
│   │       │   └── <YYYY-MM-DD>/
│   │       │       ├── news.json
│   │       │       ├── github.json
│   │       │       ├── funding.json
│   │       │       ├── hiring.json
│   │       │       ├── ceo.json
│   │       │       └── papers.json
│   │       ├── weekly/   #  <YYYY>-W<ww>.json
│   │       ├── monthly/  #  <YYYY>-<MM>.json
│   │       └── quarterly/#  <YYYY>-Q<q>.json
│   ├── _archive/               #   旧版扁平归档（legacy daily/weekly 命令写入）
│   ├── _trash/                 #   删除回收站（可恢复）
│   ├── domains/                #   占位（领域分目录）
│   └── images/                 #   占位（图片分目录）
│
├── DomainIntelWeb/             # ⑤ React/FastAPI 本地工作台
│   ├── api/                    #   localhost API、调度与安全边界
│   └── src/                    #   七个懒加载研究页面
└── DomainIntelApp/             # ⑥ 桌面启动与通用运行时
    ├── runtime/                #   数据访问、任务、DPI、单实例
    ├── launch_intdog.py        #   环境构建与 app-mode 启动
    ├── scripts/
    │   └── make_icons.py        #   图标生成脚本
    ├── run_app.bat              #   Windows 双击启动
    └── README.md
```

### 2.2 行业档案 `config/industries/<id>.yaml` 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|:---:|------|
| `id` | string | ✅ | 唯一标识（例：`semiconductor`） |
| `name` | string | ✅ | 中文名（例：`半导体`） |
| `name_en` | string | | 英文名 |
| `data_folder` | string | ✅ | DomainIntelData 下的文件夹名（例：`Chips`） |
| `aliases` | string[] | | 别名列表（CLI `--industry` 匹配用） |
| `depth` | string | | 默认水平（`beginner`/`intermediate`/`expert`） |
| `description` | string | | 一句话简介 |
| `keywords` | string[] | ✅ | 新闻/论文过滤关键词 |
| `value_chain_template` | string | | 对应 `VALUE_CHAIN_TEMPLATES` 的键 |
| `arxiv_categories` | string[] | | arXiv 分类 |
| `tracked_companies` | dict[] | | 重点跟踪公司（`[{name, symbol}]`） |
| `extra_rss_feeds` | dict | | 追加的 RSS 源（按 category 分组） |

---

## 3. 数据模型与 Schema

### 3.1 SQLite 数据库表（旧版扁平归档）

> 存储于 `DomainIntelData/_archive/db/intelligence.db`（旧版 daily/weekly 命令写入）。

#### articles 表 — 情报条目

```sql
CREATE TABLE IF NOT EXISTS articles (
    uid         TEXT PRIMARY KEY,          -- md5(url) 前 16 hex
    date        TEXT NOT NULL,             -- 归档日期 YYYY-MM-DD
    published   TEXT,                      -- 原文发布日期
    category    TEXT NOT NULL,             -- news|academic|finance|policy|startup
    title       TEXT,
    url         TEXT,                      -- 原文链接
    source      TEXT,                      -- 来源（如 36氪 / arXiv）
    summary     TEXT,
    lang        TEXT,                      -- zh/en
    authors     TEXT,                      -- JSON array
    extra       TEXT,                      -- JSON object（含 references/content_hash…）
    archived_at TEXT                       -- 归档时间戳
);
CREATE INDEX idx_date ON articles(date);
CREATE INDEX idx_cat  ON articles(category);
CREATE INDEX idx_pub  ON articles(published);
```

#### entities 表 — 知识图谱实体

```sql
CREATE TABLE IF NOT EXISTS entities (
    id          TEXT PRIMARY KEY,          -- md5("ent|<etype>|<name>")
    name        TEXT NOT NULL,
    etype       TEXT NOT NULL,             -- org|company|technology|person…
    industry    TEXT,                      -- 所属行业
    region      TEXT,                      -- 国家/地区
    summary     TEXT,                      -- 简介
    extra_json  TEXT,                      -- JSON object
    updated_at  TEXT
);
CREATE INDEX idx_ent_name ON entities(name);
```

#### edges 表 — 知识图谱关系

```sql
CREATE TABLE IF NOT EXISTS edges (
    id          TEXT PRIMARY KEY,          -- md5("edge|<src>|<relation>|<dst>")
    src_id      TEXT NOT NULL,
    dst_id      TEXT NOT NULL,
    relation    TEXT NOT NULL,             -- member_of|supplies|competes|co_mentioned|invests…
    weight      REAL DEFAULT 1.0,
    source      TEXT,                      -- 来源标识（value_chain/companies.json/article:uid…）
    updated_at  TEXT
);
CREATE INDEX idx_edge_src ON edges(src_id);
```

#### events 表 — 时间轴事件

```sql
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    etype       TEXT NOT NULL,             -- industry|company|technology|policy
    subject     TEXT,
    date        TEXT,
    title       TEXT,
    description TEXT,
    importance  INTEGER DEFAULT 3,         -- 1-5
    source_url  TEXT
);
CREATE INDEX idx_evt_date ON events(date);
```

#### companies 表 — 公司画像

```sql
CREATE TABLE IF NOT EXISTS companies (
    id          TEXT PRIMARY KEY,          -- md5("cpy|<name>")
    name        TEXT NOT NULL,
    name_en     TEXT,
    industry    TEXT,
    tier        TEXT,                      -- 所属产业链层级
    region      TEXT,                      -- 国家/地区
    is_china    INTEGER DEFAULT 0,
    metrics_json TEXT,                     -- 24 项指标 JSON
    updated_at  TEXT
);
```

#### scores 表 — 公司评分维度

```sql
CREATE TABLE IF NOT EXISTS scores (
    company_id  TEXT NOT NULL,
    dimension   TEXT NOT NULL,             -- market_position|technology|financial|…
    score       REAL,                      -- 0-10
    rationale   TEXT,
    updated_at  TEXT,
    PRIMARY KEY (company_id, dimension)
);
```

### 3.2 JSON 文件结构

#### 3.2.1 IIOSRecord（统一记录格式）

```json
{
  "type":        "news|academic|finance|policy|task|report|value_chain|…",
  "title":       "记录标题",
  "summary":     "摘要",
  "source":      "来源（如 agent:industry / 36氪 / arXiv）",
  "url":         "原文链接",
  "published":   "YYYY-MM-DD",
  "industry":    "所属行业名",
  "region":      "global|china|us|europe",
  "tags":        ["标签1", "标签2"],
  "confidence":  0.7,
  "authors":     ["作者1"],
  "references":  [{"title":"...","url":"...","source":"...","date":"..."}],
  "extra":       {"agent":"...","output_file":"...","instruction":"..."}
}
```

#### 3.2.2 COMPANY_METRICS_TEMPLATE（24 项公司指标）

```json
{
  "基本画像": {
    "name": "", "name_en": "", "founded": "", "headquarters": "",
    "employees": "", "ticker": "", "website": ""
  },
  "业务与市场": {
    "primary_business": "", "revenue_breakdown": "", "key_products": "",
    "market_share_estimate": "", "main_markets": ""
  },
  "财务指标": {
    "revenue_latest": {"amount":null,"unit":"","year":"","source":""},
    "revenue_growth_yoy": null,
    "gross_margin": null, "operating_margin": null, "net_margin": null,
    "market_cap": {"amount":null,"unit":"","date":"","source":""},
    "pe_ratio": null, "debt_to_equity": null
  },
  "竞争地位": {
    "swot_summary": "",
    "competitive_advantages": [], "weaknesses": [],
    "suppliers": [], "customers": [], "competitors": []
  },
  "供应链与风险": {
    "import_dependency": "", "export_capability": "",
    "key_risks": [], "regulatory_exposure": ""
  },
  "source_urls": []
}
```

#### 3.2.3 SCORE_DIMENSIONS（8 维评分维度）

```python
SCORE_DIMENSIONS = [
    "market_position",   # 市场地位（份额/品牌/渠道）
    "technology",        # 技术实力（专利/研发/产品）
    "financial",         # 财务健康（营收/利润/负债）
    "growth",            # 增长潜力（市场空间/增速）
    "management",        # 管理团队（履历/稳定性）
    "supply_chain",      # 供应链韧性（依存度/多元化）
    "innovation",        # 创新能力（研发投入/新产品）
    "globalization",     # 国际化程度（海外收入/布局）
]
```

#### 3.2.4 每日定期条目（Daily Item）

```json
{
  "title":    "标题",
  "abstract": "摘要（≤500 字）",
  "url":      "原文链接（可溯源）",
  "source":   "来源（GitHub/36氪/arXiv/…）",
  "date":     "2026-07-31",
  "category": "news|github|funding|hiring|ceo|papers"
}
```

#### 3.2.5 周/月/季产物

```json
{
  "kind":         "weekly|monthly|quarterly",
  "key":          "2026-W31",
  "generated_at": "2026-07-31 08:00:00",
  "counts":       {"news":20,"github":25,"funding":15,…},
  "task": {
    "type": "weekly_summary|monthly_analysis|quarterly_financials",
    "prompt": "…（完整 LLM 提示词）",
    "output_file": "periodic/weekly/2026-W31.md"
  },
  "summary": "本周行业总结（数据已汇总，LLM 任务包见 task.prompt）"
}
```

### 3.3 三层知识结构（按行业分目录，存 one_time/knowledge/）

#### industry.json — 行业（第一层）

```json
{
  "id": "abc123def456",
  "name": "半导体",
  "name_en": "Semiconductor",
  "description": "芯片设计、制造、封测、设备材料与国产替代",
  "references": [{"title":"...","url":"...","source":"..."}]
}
```

#### chains.json — 产业链层级列表（第二层）

```json
[
  {
    "id": "def456abc789",
    "name": "设计验证",
    "description": "芯片架构设计、RTL 实现、验证",
    "order": 1,
    "references": [{"title":"...","url":"..."}],
    "entities": [ … ]
  }
]
```

#### entities.json — 实体列表（第三层）

```json
[
  {
    "id": "xyz789ghi012",
    "name": "英伟达",
    "name_en": "NVIDIA",
    "type": "company",
    "chain": "设计验证",
    "country": "美国",
    "description": "全球 GPU 与 AI 计算领导者",
    "url": "https://www.nvidia.com",
    "references": [{"title":"...","url":"..."}]
  },
  {
    "id": "uvw345rst678",
    "name": "港科广吕杨迪组",
    "type": "research_group",
    "chain": "设计验证",
    "country": "中国",
    "description": "香港科技大学（广州）微电子方向研究组"
  }
]
```

**实体类型** (`entity.type`)：
- `company` — 企业
- `research_group` — 高校 / 科研院所研究组

### 3.4 control.json — 定期更新开关

```json
{
  "periodic_enabled": true,
  "daily_time": "08:00",
  "weekly_day": "monday",
  "monthly_day": 1,
  "last_run": {
    "daily": "2026-07-31",
    "weekly": "2026-W31",
    "monthly": "2026-07",
    "quarterly": "2026-Q3"
  },
  "updated_at": "2026-07-31 08:05:00",
  "note": "periodic_enabled=true 时定期更新；各周期产物存于 periodic/"
}
```

### 3.5 sources.json — 信息源

```json
{
  "industry": "Chips",
  "blogs":       [{"name":"Semiconductor Engineering","url":"https://semiengineering.com/feed/","note":"半导体工程深度技术"}],
  "platforms":   [{"name":"GitHub Trending","url":"https://github.com/trending","note":"开源项目热度"}],
  "self_media":  [{"name":"机器之心","url":"https://www.jiqizhixin.com/rss","note":"AI 领域自媒体"}],
  "news":        [{"name":"TechCrunch","url":"https://techcrunch.com/feed/","note":"科技新闻"}],
  "journals":    [{"name":"arXiv","url":"https://arxiv.org/","note":"预印本论文"}],
  "financials":  [{"name":"SEC EDGAR","url":"https://www.sec.gov/cgi-bin/browse-edgar","note":"美股财报"}],
  "finance":     [{"name":"华尔街见闻","url":"https://wallstreetcn.com/rss.xml","note":"金融资讯"}],
  "updated_at": "2026-07-31 13:50:00"
}
```

---

## 4. Agent 系统与 Prompt 全集

### 4.1 Agent 架构设计

**设计原则（IIOS_SPEC.md §4）**：
1. 研究组 Agent **不直接调用 LLM API**，而是产出「任务包」——
   结构化 Prompt + 数据上下文 + 期望输出路径，交给任意 LLM/agent 执行。
   系统离线也能跑，LLM 可随时替换。
2. Agent 之间只通过 `IIOSRecord` / 归档目录交换数据，禁止互相依赖内部实现。

**Agent 类型**：
- `llm_task` — 产出 LLM 任务包（7 个研究 Agent）
- `code` — 纯代码执行（Planner、KnowledgeGraph、Reporter、爬虫）

#### AgentContext（统一输入）

```python
@dataclass
class AgentContext:
    industry: str      = "人工智能"    # 行业名
    industry_en: str   = ""           # 英文名
    level: str         = "beginner"   # beginner|intermediate|expert
    region: str        = "global"     # global|china|us|europe
    lang: str          = "zh"         # zh|en|both
    config: dict       = {}
    archive_root: Path = None
```

`level_label` 映射：
- `beginner` → "新手（零基础，需要基础概念铺垫）"
- `intermediate` → "熟手（有基础，需要进阶和实操）"
- `expert` → "专家（需要前沿深度和细节）"

#### BaseAgent.make_task（任务包产出）

每个任务的 `extra` 包含：
- `agent` — 产出该任务的 Agent 名
- `output_file` — 期望 LLM 回写 Markdown 的路径（相对 industry_dir）
- `instruction` — 给 LLM/agent 的执行指令，含**引用规范**：
  - 每个关键结论用 `[n]` 标注来源
  - 文末附编号 references 列表（title + url）
  - 引用来源不少于 3 个
  - JSON 输出中的每个对象必须带 `source_url` 或 `references` 字段

**引用规范（全系统统一要求）**：
每个 LLM 任务包的 `extra.instruction` 都包含以下引用规范：
- 每个关键结论后用 `[n]` 标注来源
- 文末附编号 `references` 列表（每项含 title + url）
- 引用来源不少于 3 个
- JSON 输出中的每个对象必须带 `source_url` 或 `references` 字段
- 整体结论标注 `confidence(0-1)`

### 4.2 研究组 Agent（7 个，全部以 llm_task 型产出任务包）

> 源码：`src/agents/research.py`（221 行）。

#### 4.2.1 IndustryAgent — 行业总览

| 属性 | 值 |
|------|-----|
| **名称** | `industry` |
| **类型** | `llm_task` |
| **描述** | 行业整体介绍：概述/规模/历史/玩家/趋势/挑战/机会/政策 |
| **输出文件** | `industry/<行业>/overview.md` |

**Prompt（完整）**：

   你是"{行业}"行业的首席研究分析师，面向【{水平标签}】、区域视角【{区域}】。
   生成行业总览报告，必须包含以下 12 节（Markdown 二级标题）：
   1. 行业概述
   2. 行业规模（含数据来源与年份）
   3. 发展历史（关键节点）
   4. 主要玩家（按区域分组）
   5. 产业链概览
   6. 上下游关系
   7. 关键技术
   8. 未来趋势（3-5年）
   9. 主要挑战
   10. 主要机会
   11. 投资热点
   12. 政策影响（{区域} 视角）
   要求：每节引用至少 1 个可核实来源；数字必须给出年份；
   结尾给出整体 confidence(0-1)。

---

#### 4.2.2 ValueChainAgent — 产业链标准化

| 属性 | 值 |
|------|-----|
| **名称** | `value_chain` |
| **类型** | `llm_task` |
| **描述** | 内置模板 + Mermaid 图 + LLM 细化任务 |
| **输出文件** | `industry/<行业>/value_chain.md` + `.mmd` + `.json` |

**内置产业链模板（6 个行业）**：

| 行业 | 层级（按上下游顺序） |
|------|---------------------|
| 半导体 | EDA → IP → Fabless 设计 → Foundry 制造 → 封装测试 → 设��� → 材料 → OEM/整机 → 云厂商 → AI 公司 |
| 人工智能 | 算力芯片 → 云基础设施 → 数据/标注 → 基础大模型 → 开发框架/工具链 → 行业模型/Agent → 应用层 → 终端硬件 |
| 新能源 | 上游资源(锂/钴/硅料) → 材料(正负极/电解液/隔膜) → 电芯制造 → 电池包/系统 → 整车/储能集成 → 充换电/电网 → 回收利用 |
| 机器�� | 核心零部件(减速器/伺服/传感器) → 控制器/芯片 → 本体制造 → 系统集成 → 行业应用 → 运营服务 |
| 生物医药 | 基础研究/靶点发现 → 药物设计(CADD/AIDD) → 临床前 CRO → 临床试验 → 生产 CDMO → 审批注册 → 流通商业化 |

有模板命中时，Agent 离线直接产出：
- `value_chain.mmd` — Mermaid graph TD 产业链流程图（T0→T1→T2→…）
- `value_chain.json` — `{"industry":"","tiers":["层级1","层级2",…]}`

**LLM 细化 Prompt（完整）**：

   你是"{行业}"产业链研究专家。{可选：参考已生成的层级模板：T1 → T2 → T3…}
   任务：产出 value_chain.md，包含：
   1. 每个层级：定义 / 关键投入产出 / 技术壁垒 / 集中度(CR5) / 毛利水平
   2. 层级间的供需关系与卡脖子环节（{区域} 视角）
   3. 更新 value_chain.mmd（Mermaid graph TD，可加分支）
   4. 输出 value_chain.json：
      {{"tiers": [{{"name","barrier","cr5","margin","key_players",
      "references":[{{"title","url"}}]}}]}}
      每个层级的判断都必须给出来源链接。

---

#### 4.2.3 CompanyAgent — Top10 公司 + 24 项指标 + 8 维评分

| 属性 | 值 |
|------|-----|
| **名称** | `company` |
| **类型** | `llm_task` |
| **描述** | 各层级 Top10 中国/全球公司 + 24 项指标 + 8 维评分 |
| **输出文件** | `companies/top_companies.md` + `companies/deep_dive.md` + JSON |

**任务 1 — Top 公司清单 Prompt**：

   你是"{行业}"产业投资分析师。
   任务：对产业链每个层级（读取 value_chain.json），分别列出
   Top 10 中国公司 与 Top 10 全球公司。
   每家公司一行：名称 | 国别 | 层级 | 主营 | 市值量级 | 定位。
   输出 companies/top_companies.md，并生成 companies/companies.json：
   [{{"name","name_en","tier","region","is_china","sources":[{{"title","url"}}],...}}]
   （供入库 companies 表）。
   数量不足 10 家的层级列出实际全部。市值/定位信息必须附来源链接。

**任务 2 — 公司深度画像 Prompt**：

   你是跨境产业与金融分析师。对以下"{行业}"公司逐一深度画像：
   - 公司A
   - 公司B
   …

   每家公司必须填满以下 24 项指标（JSON，未知项标 "N/A" 并降低 confidence_score）：
   （见 §3.2.2 COMPANY_METRICS_TEMPLATE）

   同时给出 8 维评分（0-10 分 + 一句话依据）：
   market_position / technology / financial / growth / management /
   supply_chain / innovation / globalization

   输出：companies/<公司名>.md（人读）+ companies/<公司名>.json（入库 companies/scores 表）。
   市值/财务数据必须标注数据日期与来源链接；
   市场信心参考近期股价趋势、机构评级、舆情。
   JSON 末尾必须带 "sources": [{{"title","url"}}]，汇总画像用到的全部来源。

---

#### 4.2.4 TechnologyAgent — 技术地图

| 属性 | 值 |
|------|-----|
| **名称** | `technology` |
| **类型** | `llm_task` |
| **描述** | 技术方向→子方向→知识模块→关键论文/教材→未来发展 |
| **输出文件** | `technologies/tech_map.md` + `tech_tree.mmd` |

**Prompt（完整）**：

   你是"{行业}"技术地图专家，面向【{水平标签}】。
   任务：产出 technologies/tech_map.md，按层级拆解：
   全部技术方向 → 子方向 → 知识模块 → 关键算法/工艺 → 关键论文(附链接) →
   经典教材 → 未来发展。
   每个技术方向标注成熟度（实验室/原型/商用）与主要玩家。
   最后 5-8 个最前沿方向做"面向略懂一二学者"的导览：
   核心思想类比 + 突破点 + 主要团队。
   同时输出 technologies/tech_tree.mmd（Mermaid mindmap 或 graph TD 技术树）。

---

#### 4.2.5 LearningAgent — 学习路径 DAG

| 属性 | 值 |
|------|-----|
| **名称** | `learning` |
| **类型** | `llm_task` |
| **描述** | 按 level 生成带依赖关系的学习 DAG + Roadmap |
| **输出文��** | `learning/roadmap.md` + `learning_dag.mmd` + `learning_dag.json` |

**Prompt（完整）**：

   你是"{行业}"领域的课程设计专家。为【{水平标签}】设计学习路线。
   核心要求——学习路径必须是 DAG（有向无环图），明确前置依赖，不是平铺清单：
   1. learning/roadmap.md：
      - 阶段划分（每阶段：目标 / 知识模块 / 前置依赖 /
        推荐资源[书/课/论文/项目] / 预估时长）
      - Checklist（可勾选）
   2. learning/learning_dag.mmd：Mermaid graph TD，
      节点=知识模块，边=依赖关系，
      例：数学基础 → 电路 → 数字逻辑 → 计算机组成 → …
   3. learning/learning_dag.json：
      {{"nodes":[{{"id","name","stage","hours"}}],"edges":[["a","b"]]}}
      （供入库与前端渲染）
   expert 级重点放最新论文、工具链与工业趋势；
   beginner 级从基础学科开始。

---

#### 4.2.6 TimelineAgent — 四类时间轴

| 属性 | 值 |
|------|-----|
| **名称** | `timeline` |
| **类型** | `llm_task` |
| **描述** | 产业/公司/技术/政策四类时间轴 → events 表 + Mermaid |
| **输出文件** | `timeline/timeline.md` + `timeline.mmd` + `events.json` |

**Prompt（完整）**：

   你是"{行业}"历史脉络分析师。{可选：近一年新闻标题参考}
   任务：构建四类时间轴，输出 timeline/timeline.md +
   timeline/timeline.mmd（Mermaid timeline）+
   timeline/events.json（[{{"etype","subject","date","title","description",
   "importance","source_url"}}]，etype ∈ industry|company|technology|policy，
   importance 1-5，供入库 events 表）：
   1. 产业时间轴：从行业起源到今天的关键节点
   2. 公司时间轴：头部公司的成立/IPO/重大并购/重大产品/CEO更替/融资
   3. 技术时间轴：范式转移节点
   4. 政策时间轴：{区域} 视角的关键政策/管制事件
   每个事件标注驱动因素（技术突破/资本/政策/竞争）。

---

#### 4.2.7 SocialAgent — 高管发言追踪

| 属性 | 值 |
|------|-----|
| **名称** | `social` |
| **类型** | `llm_task` |
| **描述** | 追踪 CEO/CTO/创始人/研究负责人的公开发言 |
| **输出文件** | `social/leaders_digest.md` |

**Prompt（完整）**：

   你是"{行业}"高管言论情报分析师。{可选：今日抓取相关条目}
   任务：总结该行业头部公司与明星初创的
   CEO/CTO/创始人/研究负责人近期公开发言
   （来源：X、LinkedIn、GitHub、企业 Blog、微信公众号、访谈）。
   输出 social/leaders_digest.md：
   - Top Posts（原文链接 + 一句话摘要 + 为什么重要）
   - Trending Topics / 新产品信号 / 招聘信号 / 研究信号
   注意：无法直接抓取的平台，用搜索工具检索近 7 天公开报道替代，
   并标注来源可信度。

### 4.3 Planner Agent（任务 DAG 编排）

| 属性 | 值 |
|------|-----|
| **名称** | `planner` |
| **类型** | `code` |
| **描述** | 生成任务 DAG 并调用各 Agent 产出任务包 |
| **源码** | `src/agents/planner.py`（114 行） |

**STANDARD_DAG（10 节点 + 8 边）**：

```
┌─────────────┐
│ value_chain │──→ industry ──→ company ──→ kg_build ──→ report
└─────────────┘           ──→ company ──┘             ←── timeline
                           technology ──→ learning
                           crawl_all ──→ kg_build
```

**编排流程**：
1. 按 DAG 顺序执行 7 个研究 Agent（串行调用，每个产出任务包）
2. 输出 `plan.mmd`（Mermaid 可视化）
3. 输出 `plan.json`（含 dag_nodes、task_bundles 路径、next_steps）
4. 每个 Agent 产出的任务包写入 `industry/<行业>/tasks/<agent>.json`

**next_steps（给 agent/用户的执行指引）**：
```
1. python -m src.main collect --days 7    # 爬虫组：新闻/学术/金融并行抓取
2. 将 tasks/*.json 中的任务包交给任意 LLM/agent 执行分析
3. python -m src.main kg --build            # 知识图谱构建
4. python -m src.main daily                 # 日报生成与推送
```

### 4.4 KnowledgeGraph Agent

| 属性 | 值 |
|------|-----|
| **名称** | `kg` |
| **类型** | `code` |
| **描述** | 构建知识图谱：实体抽取 + 关系边 + Mermaid 导出 |
| **源码** | `src/agents/kg.py`（171 行） |

**四阶段构建流程**：

| 阶段 | 数据来源 | 产出表/操作 | 说明 |
|------|---------|------------|------|
| 1 | `value_chain.json` | `entities` (org/technology) + `edges` (member_of, supplies) | 按层级顺序，相邻层级加 supplies 边 |
| 2 | `companies/companies.json` | `entities` (company) + `edges` (member_of, supplies, competes) + `companies` 表 + `scores` 表 | 从 LLM 回写的 JSON 中直接读取 suppliers/competitors 字段 |
| 3 | `timeline/events.json` | `events` 表 | 直接 INSERT OR REPLACE |
| 4 | `articles` 表（最近 500 条） | `edges` (co_mentioned) | 字符串匹配：同一标题中出现的公司名→创建共现边（weight=0.5）

**共现算法（第 4 阶段伪代码）**：
```python
known = [name for name in entities WHERE etype='company']
for article in articles ORDER BY date DESC LIMIT 500:
    hits = [name for name in known if name.lower() in title.lower()]
    for i, a in enumerate(hits):
        for b in hits[i + 1:]:
            upsert_edge(a, b, "co_mentioned", weight=0.5, source=f"article:{uid}")
```

**Mermaid 导出**：
- 取权重最高 60 条边
- 关系标签中文化（supplies→供应, competes→竞争, member_of→属于, co_mentioned→共现）
- 输出：`industry/<行业>/knowledge_graph/graph.mmd`

### 4.5 深度分析 Prompt 模板集

> 源码：`src/analyzers/prompts.py`（146 行），共 8 个方法。

#### list_subdomains — 子领域拆分

   你是"<行业>"领域的资深研究分析师。面向【<水平>】，完成：
   列出该领域的不同子领域。以结构化方式列出 8-15 个主要子领域。
   对每个子领域给出：名称 / 一句话定义 / 核心研究方向与典型应用 / 与上下游的关联。
   输出 Markdown 列表，每个子领域一个小节。

#### industry_chain — 产业上下游

   你是"<行业>"产业链研究专家。详细解释该行业的产业上下游：
   上游（原材料、基础设施、核心技术/算法、硬件）
   中游（制造、集成、平台、服务）
   下游（应用场景、终端用户、渠道）
   对每个环节说明：关键投入、产出、主要参与者类型、技术壁垒。
   绘制文字版产业链全景图。输出 Markdown 分上/中/下游三节 + 全景概述。

#### top_companies — Top10 中外公司

   你是"<行业>"产业投资分析师。对产业链每个层级（可结合前序产业下游输出）
   分别列出 Top 10 中国公司与 Top 10 外国公司（欧美日韩等）。
   每家公司给出：名称、国别、主营业务、在该层级的定位。
   按层级分节，每节内含中国和外国两个子表。
   数量不足10家列出实际全部。

#### company_deep_dive — 公司深度画像

   你是跨境产业与金融分析师。针对指定公司逐一详细分析：
   - 核心优势（技术/渠道/牌照/生态）
   - 核心劣势（短板/风险）
   - 进口依赖 or 出口能力（关键技术/材料是否受制于人）
   - 市值规模（给出量级，如千亿级）
   - 市场信心指标（近期股价趋势、机构评级、舆情基调）
   每家公司一个独立 Markdown 小节。

#### knowledge_modules — 知识模块与学习路径

   你是"<行业>"领域的教育专家。为【<水平>】设计知识地图：
   对每个主要子领域：所属大类（基础层/技术层/应用层/商业层）、
   核心知识模块（概念、工具、方法）、
   推荐学习路径（从入门到进阶，含资源类型：书籍/课程/论文/项目）、
   关键前置知识。按子领域分节。

#### cutting_edge — 前沿技术导览（面向略懂一二的学者）

   你是善于科普的"<行业>"研究科学家。总结该领域最先进的技术方向，
   面向"略懂一二的学者"（有专业基础但想快速理解前沿）。
   列出 5-8 个最前沿技术方向，每个包含：名称 / 一句话核心思想（用类比）/
   为什么重要（突破点）/ 主要玩家（学术团队/公司）/ 当前成熟度（实验室/原型/商用）。
   也可结合近期论文/新闻的新进展。

#### yearly_timeline — 年度轨迹分析

   你是"<行业>"历史脉络分析师。根据近一年该领域的重要新闻标题，
   按季度（或关键节点）梳理重大事件脉络，标注每条轨迹的"驱动因素"
   （技术突破/资本/政策/竞争），总结年度主线和转折点。
   输出 Markdown 时间线 + 主线总结。

#### summarize_for_digest — 通用摘要指令

   你是"<行业>"领域的情报编辑。以下是今日抓取的<类别>（已按相关性筛选）：
   <条目列表>
   请生成一则面向【<水平>】的<类别>简报：
   1. 用 3-5 条要点概括最重要的进展
   2. 标注每条的意义（为什么值得关注）
   3. 语言简洁，中文输出，不超过 300 字。

### 4.6 定期监控 Prompt

> 源码：`src/scheduler.py`（第 102-158 行）+ `src/report_tasks.py`（第 24-83 行）。

#### 每周行业总结（scheduler.run_weekly）

   你是"<行业>"行业分析师。请基于本周抓取到的新闻、GitHub、融资、招聘、
   CEO发言、论文数据，输出一份**每周行业总结**（Markdown）：
   1. 本周最重要 3-5 个动态（每条附来源链接 [n]）
   2. 融资与招聘反映的行业冷热
   3. 技术进展亮点
   文末附 references[]（含 url）。数据见 periodic/daily/ 本周文件。

#### 每月产业分析（scheduler.run_monthly）

   你是"<行业>"产业研究员。请输出一份**每月产业分析**（Markdown）：
   1. 本月产业链各层级动态（设计/制造/封装等）
   2. 重点公司动向与投融资
   3. 政策与区域格局变化
   4. 下月值得关注的信号
   每条结论附来源 [n]，文末 references[]（含 url）。

#### 每季财报分析（scheduler.run_quarterly）

   你是"<行业>"行业财务分析师。请输出**季度上市公司财报分析**（Markdown）：
   跟踪公司：<公司列表>
   对每家公司：营收/利润同比、毛利率、业务分部表现、管理层指引、市场反应。
   数据来源：sources.json 的 financials 源（SEC/巨潮/港交所）。
   每个数据点附来源 [n]，文末 references[]（含 url）。

#### 近五年趋势报告（report_tasks.REPORTS["trend_5y"]）

   请输出一份【近五年行业趋势报告】（Markdown），着重**长期趋势**：
   1. 五年产业规模/结构/区域格局的演变曲线（分年列出关键转折点）
   2. 技术路线的长期演进方向与范式转移
   3. 产业链权力结构的变迁（哪些层级崛起/衰落）
   4. 驱动趋势的底层因素（政策/资本/需求/技术突破）
   5. 未来 3-5 年趋势研判
   每个论断附来源 [n]，文末 references[]（含 url 与年份）。

#### 近两年流行报告（report_tasks.REPORTS["popular_2y"]）

   请输出一份【近两年行业流行报告】（Markdown），着重**当下流行/热点**：
   1. 近两年最热门的技术概念/产品/赛道（按热度排序）
   2. 资本追逐的热点（融资热点、明星公司、估值案例）
   3. 舆论与社区关注的焦点（GitHub/社交媒体/媒体高频词）
   4. 流行背后的供需逻辑与可持续性判断
   每条热点附来源 [n]，文末 references[]（含 url 与时间）。

#### 近半年技术报告（report_tasks.REPORTS["tech_6m"]）

   请输出一份【近半年行业技术报告】（Markdown），着重**最新技术进展**：
   1. 近半年最重要的技术突破/论文/产品发布（按月梳理）
   2. 关键技术指标的最新水平（性能/成本/良率等，给数据）
   3. 学术界与工业界的最新方向对比
   4. 尚待解决的技术瓶颈
   5. 面向略懂一二的读者的通俗解释（每个技术点配一段白话）
   每条进展附来源 [n]，文末 references[]（含 url 与日期）��

### 4.7 信息源发现 Prompt

> 源码：`src/source_discovery.py`（第 85-111 行）。

   你是"<行业>"(<英文>)行业的资深情报分析师。
   请为这个行业梳理一份**权威信息源清单**，供持续监控使用。

   要求按以下类别分别列出（每类 3-8 个，给出 name / url / 一句话 note）：
   博客、平台/社区、自媒体、新闻媒体、学术会议/期刊、公司财报、金融资讯

   筛选标准：
   - 优先有 RSS / 稳定更新 / 可免费访问的源
   - 新闻要行业垂直的权威媒体
   - 学术要该领域的顶会/顶刊/预印本
   - 财报要官方披露渠道（SEC/巨潮/港交所/公司 IR 页）
   - 自媒体要该领域有公信力的大V/公众号/专栏

   输出为 JSON（必须带 source_url）：
   {{"blogs":[{{"name","url","note"}}], "platforms":[...],
     "self_media":[...], "news":[...], "journals":[...],
     "financials":[...], "finance":[...]}}

---

## 5. 核心工作流

### 5.1 一次性深度研究（IIOS 多 Agent）

**触发命令**：`python -m src.main plan --industry 半导体 --level beginner --region global`

**Step 1 — 行业档案加载**：`config/industries/semiconductor.yaml → apply_profile() → 覆盖 domain/academic 配置；data_folder = "Chips" → 行业数据根 = <repo>/DomainIntelData/Chips/`

**Step 2 — PlannerAgent 生成 DAG**：AgentContext(industry/level/region/lang) → plan.json + plan.mmd + 调用7个研究Agent

**Step 3 — 各研究 Agent 产出任务包**：ValueChain→value_chain.mmd+.json+tasks；Industry→12节报告prompt；Company→Top清单+深度画像；Technology→技术地图；Learning→学习DAG；Timeline→四类时间轴；Social→高管发言追踪

**Step 4 — 爬虫数据采集（独立命令）**：`python -m src.main collect --days 7` → 新闻/论文/金融/政策 → _archive/

**Step 5 — LLM/agent 执行任务包**：用户把 tasks/*.json 交给任意 LLM/agent 执行 → Markdown/JSON 回写到 industry/<行业>/

**Step 6 — 知识图谱构建**：`python -m src.main kg --build` → entities/edges/events 入库 → graph.mmd

**Step 7 — 报告生成与推送**：`python -m src.main daily/weekly` → HTML + SMTP

### 5.2 定期监控（日/周/月/季）

**触发**：UI 开关写 control.json period_enabled=true / CLI 手动 crawl-daily/weekly/monthly/quarterly

**每日六类**：NewsAggregator(新闻) + AcademicAggregator(论文) + fetch_github(GitHub Search API) + fetch_funding(RSS+融资关键词20个) + fetch_hiring(RSS+招聘关键词) + fetch_ceo(RSS+高管关键词)

**每周**：汇总本周 daily 条目数 + LLM 任务包（prompt+output_file）→ save_period("weekly")

**每月**：LLM 任务包（每月产业分析）→ save_period("monthly")

**每季**：LLM 任务包（季度财报分析）→ save_period("quarterly")

**UI 内置调度**：每60秒检查 control.json，到期且未执行则触发对应 crawl-* 子进程；长期无人值守用系统计划任务

### 5.3 信息源发现

触发：`python -m src.main init-industry --industry 芯片`（含种子源+LLM发现任务包）

流程：seed_sources()→7类内置源→写入 sources.json；生成 LLM 发现任务包→agent 执行后 merge_sources()合并

### 5.4 行业报告生成

触发：`python -m src.main report-tasks --industry 芯片`

流程：build_report_tasks()→读取 REPORTS 字典(3个模板)→生成 header→写入 one_time/reports/tasks.json→agent 执行→回写 {trend_5y,popular_2y,tech_6m}.md

---

## 6. CLI API 参考

### 新版命令（按行业分目录）

| 命令 | 参数 | 说明 |
|------|------|------|
| `init-industry` | `--industry <名> [--folder <夹>]` | 建文件夹+信息源+知识骨架+报告任务 |
| `crawl-daily` | `--industry <名> [--days N]` | 每日六类抓取→periodic/daily/<日期>/ |
| `crawl-weekly` | `--industry <名>` | 每周行业总结任务包 |
| `crawl-monthly` | `--industry <名>` | 每月产���分析任务包 |
| `crawl-quarterly` | `--industry <名>` | 每季财报分析任务包 |
| `report-tasks` | `--industry <名>` | 三份报告任务包→one_time/reports/ |
| `knowledge` | `--industry <名> [--name/--etype/--chain/--country/--url]` | 查看三层树 / 添加实体 |
| `industries` | 无 | 列出 DomainIntelData 下全部行业文件夹 |
| `discover-sources` | `--industry <名>` | 查看/扩充信息源 |

### 旧版命令（写入 _archive/）

`daily` / `weekly` / `timeline` / `collect` / `brief` / `test-email` / `query` / `archive` / `serve`

### IIOS 多 Agent

`plan` / `agent` / `kg` / `modules`

### DomainIntelApp

仓库根目录运行 `./run_intdog.sh`，或在原生 Windows checkout 双击 `run_app.bat`；
`DOMAIN_INTEL_DATA_ROOT` 环境变量可覆盖数据根。

### 关键配置项

| 路径 | 默认值 | 说明 |
|------|--------|------|
| `data_layer.root` | `../DomainIntelData` | 相对当前仓库解析，按行业分目录 |
| `archive.root` | `_archive` 子目录 | 旧版扁平归档（已解耦） |
| `llm.provider` | `none` | LLM 提供商（none/ openai/deepseek/qwen） |

---

## 7. 部署方案

### 7.1 开发环境

```bash
cd DomainIntelSearch
pip install -r requirements.txt          # pyyaml requests feedparser
python -m src.main init-industry --industry 芯片
python -m src.main crawl-daily --industry 芯片 --days 1
cd .. && ./run_intdog.sh
```

### 7.2 无人值守定期监控

**方案 A — Windows 计划任务**：每天 08:00 `python -m src.main crawl-daily --folder Chips`；每周一 09:00 crawl-weekly；每月1日 10:00 crawl-monthly；每季首日 10:00 crawl-quarterly

**方案 B — UI内置调度 + 计划任务兜底**：UI 开时内置线程自动跑；UI 关时靠方案 A 兜底。推荐两者都配。

**方案 C — Linux/macOS cron**：
```cron
0 8 * * * cd /path/to/DomainIntelSearch && python -m src.main crawl-daily --folder Chips
0 9 * * 1 cd /path/to/DomainIntelSearch && python -m src.main crawl-weekly --folder Chips
0 10 1 * * cd /path/to/DomainIntelSearch && python -m src.main crawl-monthly --folder Chips
0 10 1 1,4,7,10 * cd /path/to/DomainIntelSearch && python -m src.main crawl-quarterly --folder Chips
```

### 7.3 数据备份

整个 `DomainIntelData/` 文件夹直接拷贝即可。建议每日增量+每周全量。

### 7.4 多行业部署

每个行业独立文件夹，互不干扰。并行抓取：`python -m src.main crawl-daily --industry 芯片 & python -m src.main crawl-daily --industry ai &`。注意 GitHub Search API 限流 10次/分钟，多行业并发时需错开。

### 7.5 PyInstaller 打包（暂缓）

```bash
cd DomainIntelApp && pyinstaller build/DomainIntel.spec --noconfirm
```
产出 `dist/DomainIntel/DomainIntel.exe`（~38MB）。分发改将整个 `dist/DomainIntel/` 文件夹（含 _internal/）打包 ZIP，用户解压双击即用。

---

## 8. 开发路线图

### Phase 1: 基础架构 ✅

| 任务 | 状态 |
|------|:---:|
| 六维源码审计（29个问题诊断） | ✅ |
| 五部分分层（Search/Data/App职责分离） | ✅ |
| 行业档案系统（5个内置行业） | ✅ |
| 模块化功能框架（17个可组合模块） | ✅ |
| agent中性skills（5个能力文档） | ✅ |
| 引用溯源全链路 | ✅ |
| 按行业分目录存储（IndustryStore） | ✅ |
| 三层知识结构（行业→产业链→实体） | ✅ |
| 定期监控（日/周/月/季 6类+3种分析） | ✅ |
| 纯UI重写（读取+删除+定期开关+卡片展示） | ✅ |

### Phase 2: 可信度增强（4个Critical）

🔴 **P2.1** SQLite 启用 WAL模式 + busy_timeout
🔴 **P2.2** 爬虫加超时控制
🔴 **P2.3** JSON写入改为 tempfile+rename 原子操作
🔴 **P2.4** PolicyNewsCrawler/FinanceNewsCrawler 修复 since_days硬编码bug
🟡 P2.5 SeenStore 按时间过期策略
🟡 P2.6 article_id 16→32 hex
🟡 P2.7 结构化 ErrorLog
🟡 P2.8 except:pass 改日志记录

### Phase 3: 泛用性增强

🔴 **P3.1** 基础RSS源全量迁入行业档案
🔴 **P3.2** SeenStore 按行业隔离
🟡 P3.3 articles 表增加 industry 列
🟡 P3.4 spec.md format段实际驱动输出
🟡 P3.5 region参数控制数据源选择
🟢 P3.6 日报多语言

### Phase 4: 专业性增强

🟡 P4.1 日报 [n] 双向锚点
🟡 P4.2 schema_version 字段
🟢 P4.3 新闻自动分类
🟢 P4.4 语义去重
🟢 P4.5 产业链模板结构化

### Phase 5: 深度增强

🟢 P5.1 NLP 关系抽取
🟢 P5.2 event_entity 中间表
🟢 P5.3 SWOT+雷达图
🟢 P5.4 学习评估+实践项目
🟢 P5.5 新增数据源（SEC/巨潮/专利/研报）

### Phase 6: 广度增强

🟢 P6.1 新增行业档案（量子计算/金融科技/新材料/氢能）
🟢 P6.2 IntDog.exe 打包（含图标）
🟢 P6.3 手机端PWA重做
🟢 P6.4 多语言全面支持

---

## 附录 A: 架构决策记录 (ADR)

**ADR-001 — 为什么 Agent 不直连 LLM？** 产出模型无关任务包，模型可替换，系统离线也能生成，降低平台耦合。

**ADR-002 — 为什么 one_time/ 和 periodic/ 分开？** 一次性深爬是参考级输出需审核，定期监控是流水级自动生成，删除/备份/展示策略不同。

**ADR-003 — 为什么 UI 不做编辑？** 编辑应由 agent 任务包回写控制质量，手动编辑破坏引用溯源，降低误操作风险。

**ADR-004 — 为什么有 data_folder 字段？** 不同称谓的同一行业用统一文件夹名（半导体→Chips），文件夹名稳定不受多语言影响，��持自定义。

**ADR-005 — 为什么旧扁平归档归入 _archive/？** 保留旧命令兼容性，与新版并存互不干扰，等新版稳定后逐步废弃。

---

## 附录 B: 文件对照表

| 文档章节 | 源码文件 | 行数 |
|---------|---------|:---:|
| §3.1 SQLite | archive_store.py:72-123 | 52 |
| §3.2 IIOSRecord | schema.py:34-51 | 18 |
| §3.3 三层知识 | knowledge_model.py | 156 |
| §3.4 定期存储 | industry_store.py | 210 |
| §4.2 研究Agent | research.py | 221 |
| §4.3 Planner | planner.py | 114 |
| §4.4 KG | kg.py | 171 |
| §4.5 Prompt模板 | prompts.py | 146 |
| §4.6 定期Prompt | scheduler.py + report_tasks.py | 159+83 |
| §4.7 信息源 | source_discovery.py | 125 |
| §5 工作流 | agents/ + orchestrator.py | — |
| §6 CLI | main.py | 380 |

---

> **文档版本 2.0 | 基于 2026-07-31 代码状态生成 | 随代码演进持续更新**

---

## 9. 测试策略

### 9.1 单元测试覆盖矩阵

| 模块 | 测试重点 | 离线可测 | 当前状态 |
|------|---------|:---:|:---:|
| `industry_store.py` | save_daily/list_daily/delete_daily_item/save_period JSON 读写正确性 | ✅ | 未覆盖 |
| `knowledge_model.py` | add_chain/add_entity/delete_entity/tree 三层数据一致性 | ✅ | 未覆盖 |
| `spec_loader.py` | 解析 spec.md 各段（抓取领域/保存格式/用户待规定）、空文件、损坏文件 | ✅ | 已手动验证 |
| `profiles.py` | find_profile 匹配（精确/别名/模糊）、apply_profile 合并去重 | ✅ | 未覆盖 |
| `source_discovery.py` | seed_sources 返回正确结构、merge_sources 按 URL 去重 | ✅ | 未覆盖 |
| `scheduler.py` | run_daily 六类计数正确性、run_weekly 汇总逻辑 | ⚠ 需 mock | 未覆盖 |
| `periodic_crawlers.py` | fetch_github API 格式解析、_fetch_rss 关键词过滤 | ⚠ 需 mock | 未覆盖 |
| `archive_store.py` | save_articles 合并去重、query 筛选、graph_neighbors BFS | ✅ | 未覆盖 |
| `news_crawler.py` | Article 构造、关键词过滤、RSSCrawler 解析 | ⚠ 需 mock | 未覆盖 |
| `digest_generator.py` | HTML 模板渲染、_references_html 去重 | ✅ | 未覆盖 |

**建议测试框架**：`pytest` + `pytest-mock`

**快速冒烟命令**（开发提交前必执行）：
```bash
# Search 端
cd DomainIntelSearch
python -m src.main modules           # Orcherstrator + Module 初始化
python -m src.main industries        # 行业列表
python -m src.main knowledge --industry 芯片  # 三层树

# App 端
python -c "import sys; sys.path.insert(0, 'DomainIntelApp'); from runtime import dataio; assert dataio.find_data_root().exists()"
```

### 9.2 集成测试场景

| 场景 | 步骤 | 验证点 |
|------|------|--------|
| 完整初始化流程 | init-industry → knowledge add → report-tasks | control/sources/knowledge/reports 全部生成 |
| 每日抓取端到端 | crawl-daily --days 1 | periodic/daily/ 下 6 个 JSON 非空且格式正确 |
| 删除→恢复 | UI 删除每日条目 | JSON 条目数减少 1；重跑 crawl-daily 恢复 |
| 定期产物删除 | UI 删除 weekly 产物 | 文件从 periodic/weekly/ 移至 _trash/ |
| 多行业隔离 | 先跑 Chips 再跑 AI 的 crawl-daily | 各自的 periodic/ 无交叉 |
| CLI help | `python -m src.main -h` / `python -m src.main daily -h` | 所有命令有帮助文本 |

### 9.3 关键测试用例

**industry_store.py 原子写入测试**：
```python
def test_write_atomic(tmp_path):
    store = IndustryStore(tmp_path, "Test", "测试")
    # 写入后立即 kill 进程 → 目标文件不应存在（.tmp 残留）
    # 正常写入后文件内容完整且可解析
    store.save_daily("news", [{"title": "test", "url": "http://a"}], "2026-01-01")
    items = store.list_daily(date="2026-01-01", category="news")
    assert len(items) == 1
    assert items[0]["title"] == "test"
```

**profiles.py 匹配测试**：
```python
def test_find_profile_aliases():
    assert find_profile("芯片")["id"] == "semiconductor"
    assert find_profile("ai")["id"] == "ai"
    assert find_profile("半导体")["id"] == "semiconductor"
    assert find_profile("机器学习") is not None  # 模糊匹配
    assert find_profile("不存在的行业") is None
```

**knowledge_model.py 三层一致性测试**：
```python
def test_three_layer_tree(tmp_path):
    km = KnowledgeModel(tmp_path)
    km.set_industry("芯片", "Chip")
    km.add_chain("设计验证")
    km.add_entity("英伟达", "company", "设计验证", country="美国")
    km.add_entity("港科广吕杨迪组", "research_group", "设计验证", country="中国")
    tree = km.tree()
    assert len(tree["chains"]) == 1
    assert len(tree["chains"][0]["entities"]) == 2
    ents = km.get_entities(etype="company")
    assert len(ents) == 1
    assert ents[0]["name"] == "英伟达"
```

---

## 10. 安全模型

### 10.1 数据安全

| 层级 | 措施 | 说明 |
|------|------|------|
| 存储 | 原子写入（tempfile + rename） | 防止崩溃导致 JSON 损坏 |
| 删除 | 定期产物移入 `_trash/` 回收站 | 可恢复（手动移回或保留 30 天） |
| 备份 | 整个 `DomainIntelData/` 文件夹拷贝 | 所有数据自包含，可直接备份 |
| 授权码 | `settings.yaml` 的 `email.password` | 敏感信息，不提交到版本控制 |
| API Key | `news.newsapi_key / gnews_key` | 同上 |

### 10.2 网络安全

| 爬虫 | 认证 | 限流 | 超时 |
|------|:---:|------|:---:|
| RSS (feedparser) | 无需 | 无限制 | ⚠ 当前无超时，建议 15s |
| GitHub Search API | 无需（公开仓库） | 10 req/min（未认证）/ 30 req/min（认证） | 15s |
| arXiv API | 无需 | 1 req/3s（礼貌爬取） | 15s |
| NewsAPI | API Key | 100 req/day（免费） | 15s |
| GNews | API Key | 100 req/day（免费） | 15s |
| AKShare | 无需 | 无明确限制 | 15s |

**建议**：
- 所有 HTTP 请求统一 `timeout=15`（当前 feedparser 无超时是已知 bug）
- 对 arXiv 加入 `time.sleep(3)` 礼貌延迟
- GitHub Search API 加入 `time.sleep(6)` 避免 403
- 对同一 host 的并发请求数限制为 1（避免被封 IP）

### 10.3 UI 数据安全

- 删除确认：每次删除弹出 `messagebox.askyesno` 确认对话框
- 编辑禁用：UI 无文本编辑入口（`app.py` 无编辑按钮或编辑区）
- 外部打开：`open_path()` 使用 `os.startfile`/`xdg-open`/`open` 系统命令，不执行用户输入
- 输入校验：CLI `--industry` 参数通过 `find_profile()` 校验，不支持任意路径注入

---

## 11. 数据质量检查清单

### 11.1 抓取质量

| 检查项 | 频率 | 方法 |
|--------|:---:|------|
| 各 RSS 源最近 7 天抓取量 | 每日 | `crawl-daily` 日志中各类别计数 |
| RSS 源可用性（HTTP 200） | 每周 | 手动检查或 ErrorLog |
| 中文/英文覆盖比例 | 每月 | 统计 `lang` 字段分布 |
| 重复条目率（URL 碰撞） | 每月 | `SeenStore` 命中率统计 |
| 关键词过滤精度（假阳性） | 每月 | 随机抽样 100 条人工验证 |

### 11.2 存储质量

| 检查项 | 方法 |
|--------|------|
| JSON 文件可解析性 | `json.loads()` 扫描 `periodic/daily/` 下所有文件 |
| `control.json` 字段完整性 | `periodic_enabled` + `last_run` + `updated_at` 均存在 |
| `sources.json` 7 类齐全 | blogs/platforms/self_media/news/journals/financials/finance 均非空 |
| 三层知识一致性 | `chains.json` 中每个 chain 对应 `entities.json` 中至少 0 个实体 |

### 11.3 UI 数据一致性

| 检查项 | 预期 |
|--------|------|
| 行业列表与 `DomainIntelData/` 文件夹一致 | `industries` CLI 输出 = `ls DomainIntelData/ | grep -v _` |
| 每日条目数与 JSON 文件一致 | UI「每日情报」计数 = 各 daily JSON 条目总和 |
| 删除后 JSON 即时反映 | 删除后立即刷新，条目数减 1 且文件内容更新 |

---

## 12. 扩展开发指南

### 12.1 新增行业

1. 在 `config/industries/` 新增 `<id>.yaml`：
   ```yaml
   id: quantum
   name: "量子计算"
   name_en: "Quantum Computing"
   data_folder: "Quantum"
   keywords: ["量子","quantum","qubit","量子比特"]
   arxiv_categories: ["quant-ph","cs.ET"]
   ```
2. （可选）在 `research.py` 的 `VALUE_CHAIN_TEMPLATES` 添加产业链模板
3. 运行 `python -m src.main init-industry --industry 量子计算`
4. 运行 `python -m src.main crawl-daily --industry 量子计算`

### 12.2 新增爬虫类别（以 news 分类为例）

1. 在 `src/crawlers/` 创建 `my_crawler.py`：
   ```python
   class MyCrawler:
       def fetch(self) -> list[Article]:
           # 返回 Article 对象列表
   ```
2. 在 `periodic_crawlers.py` 或 `scheduler.py` 的 `run_daily()` 中接入
3. 在 `industry_store.py` 的 `DAILY_CATEGORIES` 添加新类名
4. 在 UI 的 `app.py` 的 `CAT_META` 添加新类别显示配置
5. 更新本设计文档 §3.4 和 §5.2

### 12.3 新增 LLM 任务包 Agent

1. 在 `src/agents/` 新建 `<agent>.py`，继承 `BaseAgent`：
   ```python
   class MyAgent(BaseAgent):
       name = "my_agent"
       description = "描述"
       def run(self, **kw) -> list[IIOSRecord]:
           prompt = "完整的分析 prompt"
           return [self.make_task("任务名", prompt, "output.md")]
   ```
2. 在 `src/agents/__init__.py` 注册到 `AGENT_REGISTRY`
3. 在 `planner.py` 的 `STANDARD_DAG` 添加节点和依赖边
4. 更新本设计文档 §4

---

## 13. 已知限制与风险

### 13.1 技术债务

| 问题 | 严重度 | 缓解 | 计划 |
|------|:---:|------|:---:|
| `feedparser.parse()` 无超时 | 🔴 Critical | 手动 kill 进程 | Phase 2 |
| `SeenStore` 10000条后去重失效 | 🔴 Critical | 定期清理旧数据 | Phase 2 |
| `since_days` 硬编码 bug | 🔴 Critical | 手动使用 `collect` + `--days` 覆盖 | Phase 2 |
| `article_id` 16 hex 碰撞风险 | 🟡 High | 目前条目数远低于碰撞阈值 | Phase 2 |
| funding/hiring/ceo 仅 RSS 过滤 | 🟡 High | 用 LLM 任务包补充 | Phase 5 |
| 知识图谱边无 NLP 类型识别 | 🟢 Medium | 用 LLM 回写的 companies.json 补充 | Phase 5 |

### 13.2 外部依赖风险

| 依赖 | 风险 | 缓解 |
|------|------|------|
| RSS 源（TechCrunch/36氪…） | 源停止维护或改版 | 行业档案加 `extra_rss_feeds` 可追加替代源 |
| GitHub Search API | 限流从严 | 认证 Token 提限 + 本地缓存 |
| arXiv API | 偶尔维护/慢响应 | `timeout=15` + 结果缓存 |
| PyYAML/requests/feedparser | 未来不兼容 | 固定版本号在 requirements.txt |

### 13.3 平台限制

- **Windows**: 桌面程序 (Tkinter) 正常；PyInstaller 打包需注意中文路径和 Tcl/Tk 捆绑。
- **macOS**: Tkinter 风格较旧（用 `clam` 主题缓解）；`os.startfile` 需替换为 `open`。
- **Linux**: 需安装 `python3-tk` 包；`xdg-open` 替代 `os.startfile`。

---

## 14. 贡献指南

### 14.1 分支策略

```
main          — 稳定版本
feat/xxx      — 新功能分支（从 main 切出）
fix/xxx       — Bug 修复分支
docs/xxx      — 文档更新
```

### 14.2 提交规范

```
<type>(<scope>): <subject>

feat(scheduler): 增加每日六类抓取的 ErrorLog 记录
fix(crawler): 修复 PolicyNewsCrawler since_days 硬编码
docs(design): 更新 §5.2 定期监控数据流图
```

### 14.3 代码风格

- Python 3.10+ type hints
- 4 空格缩进，120 字符行长
- 公开方法/类/模块级 docstring
- JSON 键用 snake_case，YAML 键用 snake_case
- 文件名用 snake_case

### 14.4 提交前检查清单

```
☐ py_compile 全量通过
☐ src.main modules 正常
☐ src.main industries 列表正确
☐ 新增/变更的 CLI 命令有 --help 说明
☐ 新增/变更的 JSON schema 已更新 DESIGN.md §3
☐ 新增/变更的 Agent prompt 已更新 DESIGN.md §4
☐ 无新增 from src 依赖在 DomainIntelApp/
☐ 涉及爬虫的变更已做本地网络测试（crawl-daily --days 1）
```


---

---

## 15. 研究助手五能力（2026-07-31 新增）

系统从「信息聚合器」升级为「行业研究助手」的五项能力设计。

### 15.1 ① 多源交叉验证（verification.py）

**核心问题**：RSS 聚合的条目 references 恒为空、单一来源无法辨真伪。

**方案**：
1. `group_stories(items)` 用并查集把同一事件的报道归并为一个"故事"：
   - 完全相同 URL 直接归并；
   - 标题 token overlap 系数 `|交|/min(|A|,|B|) >= 0.42` 且交集 >= 3 归并；
   - 字符级近似重复（difflib ratio >= 0.75）归并。
   - 中文按 2-gram 切 token（不分词）；阈值经四组对照样例标定
     （同事件改写≈0.47 / 相关不同事件≈0.19 / 无关≈0.06 / 近似重复≈0.77）。
   - **教训**：不要用"辨识词门"（key-token gate）——中文整句会被当成一个辨识词，
     改写标题永远共享不了，反而挡住正确归并。
2. `score_group()` 按**独立来源数**（来源名+域名去重）打分：
   1源=0.30 / 2源=0.60 / 3源=0.78 / >=4源=0.88；高权威源（通讯社/官方/顶会，见
   `AUTHORITY` 表）在场 +0.07；**诚实封顶 0.95，永不满分**。
3. 标签：高(>=0.75) / 中(>=0.5) / 低(<0.5)；verified = 独立来源 >=2。
4. 回填每条 `credibility / credibility_label / source_count / verified / references[]`
   （references = 组内其它来源，排除自身与同 URL）。

**接入点**：`scheduler.run_daily()` 末尾自动执行；也可手动 `verify --industry X`。
跨类别归并（同一故事可能同时出现在 news 与 funding），再按原文件回写。

**诚实性说明**：单日、单语种利基源里同一事件很少被 2+ 独立媒体同时报道，
故真实数据多为"低·源1"——这是事实而非缺陷；多源印证随源增多/多日累积出现。

### 15.2 ② 事件影响引擎（impact_engine.py）

**事件检测** `detect_events(store)`：从最近一天情报筛出值得深挖的事件——
标题/摘要含政策/事件信号词（`POLICY_KW`/`EVENT_KW`：限制/禁令/出口/制裁/关税/
ban/export/sanction…）或 verified=True；按 credibility 降序，落盘
`one_time/impact/events.json`。

**影响分析** `analyze_event(store, pcfg, event)` 四层关联：
1. **受影响公司**：事件直接点名（含 name_en 别名）｜出现在事件相关情报（token
   重叠>=2）｜所属产业链被命中（回填 chain_of_company）；
2. **关联供应链**：三层知识的 chain 名 token 与事件重叠，或由命中公司回填；
3. **相关论文**：papers 类主题重叠 >=2，按重合度排序；
4. **相关政策**：news 类带政策信号且（主题重叠 >=2 或事件本身是政策）。

产出：`one_time/impact/<事件slug>/impact.json`（结构化骨架）+
`analysis_task.json`（叙事性影响分析 LLM 任务包：影响等级 短/中/长期、
供应链传导路径、投资启示，要求逐论断引用 [n]）。

**边界**：代码层只做客观关联；叙事分析交 agent。本地语料无相关报道时如实返回
"未命中"，任务包引导 agent 联网补充。

### 15.3 ③ 竞争格局（landscape.py）

四类玩家的**客观骨架**（纯代码可判定）：
- **Leader**：行业档案 `tracked_companies`（重点上市公司）；
- **Challenger**：知识库企业实体中近期被频繁提及者（mentions>=2 或有融资信号）；
- **Emerging**：出现在融资新闻里的已知名单公司；
- **Declining**：命中裁员/亏损/下滑信号词（`DECLINE_KW`）的公司。

每档按提及量降序；产出 `one_time/landscape/landscape.json` +
`history/<日期>.json` 每日快照。`share_trend(company)` 读历史快照的提及量序列，
作为份额/地位变化的代理指标。定性份额估算以 `market_share_task` LLM 任务包产出。

### 15.4 ④ 深度研究报告（deep_reports.py）

四种类型（`DEEP_REPORTS` 注册表，对应用户示例）：
`quarterly`《行业季度报告》/ `chain`《产业链研究》/ `landscape`《竞争格局》/
`market`《市场分析》。

每个任务包的 prompt 包含：行业角色设定 + **本地数据清单**（`_data_manifest()` 列出
应读取的 periodic/daily 六类、knowledge 三层、landscape.json、impact/events.json、
sources.json）+ 分报告类型的 6 段提纲 + 硬性要求（>=3000 字、逐论断引用 [n]、
区分事实与研判、末尾数据附录）。产出 `one_time/reports/deep_tasks.json`；
agent 执行后回写 `deep/<rid>.md` + `<rid>.references.json`。

支持 `--rtype` 只生成某一种；`topic` 参数可定制主题（RISC-V/量子芯片/EDA…）。

### 15.5 ⑤ MCP Server（mcp_server.py）

**目的**：抓取/读取逻辑不耦合在 Agent 内，全部数据源以统一协议（MCP）暴露。

- **传输**：stdio（换行分隔 JSON-RPC 2.0）；**stdout 只跑协议帧**，日志走 stderr。
  （为此 main.py 的 Orchestrator 改为按需懒构造——其初始化 print 曾污染协议流。）
- **协议**：initialize（回显客户端 protocolVersion）/ notifications/initialized /
  ping / tools/list / tools/call；工具内错误以 `isError:true` 返回（MCP 约定）。
- **10 个只读工具**：list_industries / get_daily / get_knowledge / get_sources /
  get_landscape / get_impact_events / get_impact / list_report_tasks / read_report /
  search_items。纯标准库实现，零依赖。
- **启动**：`python -m src.main mcp-serve`；客户端配置见根 README「研究助手」节。

### 15.6 UI 接入（DomainIntelApp）

- 每日情报卡片新增**可信度徽标**（高/中/低+源数+✓），点击弹窗显示互相印证的来源；
- 新增「研究助手」标签：竞争格局四类玩家、已分析事件（点击查看四层关联详情）、
  检测到的最新事件、深度报告任务包状态（✅已生成可打开 / ⏳待执行）；
- dataio.py 新增只读函数：read_landscape / share_trend / read_impact_events /
  list_impact_analyses / read_impact / read_deep_tasks / list_deep_reports。
  App 依然零 src 依赖、无编辑功能。

### 15.7 存储契约变更（spec.md 已同步）

```
<行业>/one_time/landscape/landscape.json + history/<日期>.json
<行业>/one_time/impact/events.json + <事件slug>/{impact,analysis_task}.json
<行业>/one_time/reports/deep_tasks.json + deep/<rid>.md
每日条目新增字段：credibility / credibility_label / source_count / verified
```

---

## 16. 自我迭代（2026-08-07）：弹性抓取 + 前端可用性

### 16.1 弹性网络层（crawlers/http_utils.py，新增）

**问题**：本机环境变量常驻 `HTTP_PROXY=127.0.0.1:7890`（Clash 类代理），代理不在线时
所有走环境代理的请求全灭（feedparser/requests 默认读 env 代理）；且 feedparser 裸
`parse(url)` 无 UA、无统一超时、失败静默。

**方案**：
- `fetch_url()`：**直连优先**（`Session(trust_env=False)` 忽略环境代理），
  连接错误/超时后**回退环境代理**再试一次（代理在线时可救回被墙源）；
- 所有失败登记到模块级清单，`crawl-daily` 结束写入
  `periodic/daily/<日期>/_crawl_log.json`（各类条数 + 失败源及双通道错误原因）；
- `_` 前缀文件在 IndustryStore.list_daily 与 App dataio.list_daily 中均被跳过。
- news_crawler / periodic_crawlers / academic_crawler 全部改经此模块。

### 16.2 学术抓取修复（academic_crawler.py）

**根因**：`filter_by_keywords` 用全量关键词（含"半导体/芯片/晶圆"等中文），
arXiv/S2 是英文库 → 论文几乎被滤空（曾一天仅 1 条）。

**修复**：
- arXiv / SemanticScholar 只用 ASCII 关键词（`k.isascii()`）过滤/组 query；
- arXiv 分类内英文关键词命中 < max(3, N/4) 时，保留分类内最新 N 条
  （cs.AR/cs.ET/eess.SY 分类本身即行业方向），并标注 `extra.keyword_match=false`；
- 实测：AI 论文 1 → 20 条/天。

### 16.3 行业垂直信息源（实测可达后才写入档案）

- 候选源一律先实测（直连 200 + 有条目）才写入 `config/industries/*.yaml`；
- AI 新增：MIT Tech Review AI；半导体新增：Semiconductor Digest（100 条/feed）、
  EE Times。VentureBeat/ImportAI/HuggingFace/IEEE Spectrum 直连不可达，未收录
  （代理在线时可通过回退通道碰运气，但不写死）。

### 16.4 跨天交叉验证（verification.py）

`verify_store_daily(store, days=N)`：N>1 时把最近 N 天条目统一归并打分再按文件回写。
`crawl-daily` 固定 days=3；CLI `verify` 默认跨 3 天（`--days` 可调）。
实测 AI 首日即产出 3 条「高」可信（TechCrunch/The Verge/HN 三源印证同一 ChatGPT 新闻，
credibility 0.78，references 双向回填）。

### 16.5 前端可用性（DomainIntelApp）

- **搜索框**：标题+摘要关键词过滤（Enter 触发）；
- **分页**：首屏 30 张卡片 +「加载更多」（102 条全渲染曾明显卡顿）；
- **类别按钮计数**：`新闻(7)` 式实时条数；
- **可信度排序**：高→低，同级按独立来源数；
- **滚轮冲突修复**：ScrollFrame 滚轮响应前检查 `winfo_ismapped()`，
  隐藏标签页不再抢滚轮。
- 数据读取一次取全天全类别，本地过滤/计数/排序（避免多次读盘）。
