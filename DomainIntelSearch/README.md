# DomainIntelSearch —— 抓取引擎

> **只负责抓取**：从网络与 LLM/agent 获取领域信息，按行业分目录写入 DomainIntelData。
> 这是整个系统里**唯一需要联网、用 LLM/agent** 的部分。

## 它做什么
- **信息源发现**：设定行业后，先梳理该关注哪些博客/平台/自媒体/新闻/学术期刊/财报/金融源
- **三层知识结构**：行业 → 完整产业链 → 具体实体（企业 / 高校研究组）
- **一次性深度爬取**：三份行业报告（近五年趋势 / 近两年流行 / 近半年技术）
- **定期监控**：每天（新闻/GitHub/融资/招聘/CEO发言/论文）、每周（行业总结）、
  每月（产业分析）、每季（财报分析）
- **研究助手能力**（升级为行业研究助手）：
  1. **多源交叉验证**（`verify`）——同一故事按独立来源数自动打可信度分，回写 references
  2. **事件影响引擎**（`impact`）——事件 → 受影响公司/供应链/相关论文/相关政策 + 分析任务包
  3. **竞争格局**（`landscape`）——Leader/Challenger/Emerging/Declining 四类 + 每日快照跟踪变化
  4. **深度研究报告**（`deep-reports`）——季度报告/产业链研究/竞争格局/市场分析，任务包引用本地语料编号成文
  5. **MCP Server**（`mcp-serve`）——把全部数据源封装为 10 个 MCP 工具，任意 Agent 按统一协议调用
- 所有结果按行业写入 `DomainIntelData/<行业>/`

## 关键设计：不绑定任何 agent 平台
深度研究 / 行业报告 / 周月季分析以「模型无关任务包」形式产出（含完整 prompt），
你可把它交给 Codex / WorkBuddy / Claude Code / 自写脚本调 API，模型随时可换。
想让 Search 自带联网 LLM 直连，改 `config/settings.yaml` 的 `llm.provider` 即可
（默认 `none`，只产任务包）。

## 关键设计：弹性网络层（http_utils.py）
所有 HTTP/RSS 拉取走 `crawlers/http_utils.py`：**直连优先**（忽略环境代理，
`trust_env=False`），直连失败才回退环境变量代理——本机 127.0.0.1:7890 代理
不在线时抓取不再全灭。每个失败的源登记到失败清单，`crawl-daily` 结束后写入
`periodic/daily/<日期>/_crawl_log.json`（各类条数 + 失败源及原因），不再静默吞错。

学术抓取按英文关键词过滤（arXiv/S2 是英文库，中文关键词会把结果滤空）；
arXiv 分类内命中过少时保留最新 N 条并标注 `keyword_match=false`（分类本身即行业方向）。

## 安装
```bash
pip install -r requirements.txt     # pyyaml / requests / feedparser
```

## 新工作流（推荐，按行业分目录）
```bash
# 1) 初始化行业：建文件夹 + 信息源 + 三层知识骨架 + 三份报告任务包
python -m src.main init-industry --industry 芯片

# 2) 查看/扩充信息源（先确定"该看谁"）
python -m src.main discover-sources --industry 芯片

# 3) 三层知识：查看 / 添加实体（企业或高校研究组）
python -m src.main knowledge --industry 芯片
python -m src.main knowledge --industry 芯片 --name 英伟达 --etype company --chain 设计验证 --country 美国
python -m src.main knowledge --industry 芯片 --name 港科广吕杨迪组 --etype research_group --chain 设计验证 --country 中国

# 4) 定期抓取（每天六类）
python -m src.main crawl-daily --industry 芯片          # 新闻/论文/GitHub/融资/招聘/CEO
python -m src.main crawl-weekly --industry 芯片         # 每周行业总结
python -m src.main crawl-monthly --industry 芯片        # 每月产业分析
python -m src.main crawl-quarterly --industry 芯片      # 每季财报分析

# 5) 生成三份行业报告任务包（5年趋势/2年流行/半年技术）
python -m src.main report-tasks --industry 芯片

# 6) 研究助手：交叉验证 / 竞争格局 / 事件影响 / 深度报告
python -m src.main verify --industry 芯片              # 回写可信度+references
python -m src.main landscape --industry 芯片           # 四类玩家格局
python -m src.main impact --industry 芯片              # 检测行业事件
python -m src.main impact --industry 芯片 --event "美国限制GPU出口"
python -m src.main deep-reports --industry 芯片        # 四份深度报告任务包

# 7) MCP Server：把数据源以统一协议提供给任意 Agent（stdout 只跑协议帧）
python -m src.main mcp-serve

# 列出全部行业数据文件夹
python -m src.main industries
```
> `--industry` 可用行业名或别名（芯片 / 半导体 / ai / 人工智能…）；
> 数据文件夹名由行业档案的 `data_folder` 决定（芯片→Chips，ai→AI），也可用 `--folder` 覆盖。

## 旧命令（扁平归档，写入 DomainIntelData/_archive/）
```bash
python -m src.main daily --industry 芯片    # 每日 HTML 日报 + 邮件
python -m src.main weekly / timeline / query / plan / agent / kg / modules
```

## 目录
```
DomainIntelSearch/
├── src/
│   ├── main.py               # 命令行入口
│   ├── industry_store.py     # 按行业分目录存储（periodic/one_time/control/sources）
│   ├── knowledge_model.py    # 三层知识结构
│   ├── source_discovery.py   # 信息源发现
│   ├── scheduler.py          # 定期调度（日/周/月/季）
│   ├── report_tasks.py       # 三份行业报告任务包
│   ├── verification.py       # ① 多源交叉验证 + 可信度评分
│   ├── landscape.py          # ③ 竞争格局四类玩家 + 历史快照
│   ├── impact_engine.py      # ② 事件影响引擎（公司/供应链/论文/政策）
│   ├── deep_reports.py       # ④ 深度研究报告任务包（季度/产业链/格局/市场）
│   ├── mcp_server.py         # ⑤ MCP Server（stdio，10 个只读工具）
│   ├── crawlers/             # 新闻/学术/金融 + periodic_crawlers(GitHub/融资/招聘/CEO)
│   ├── agents/               # IIOS 研究 Agent + 知识图谱
│   └── ...
├── config/
│   ├── settings.yaml         # 主配置（data_layer.root 指向 DomainIntelData）
│   └── industries/           # 行业档案（含 data_folder 字段）
├── skills/                   # 能力说明（agent 中立）
└── requirements.txt
```

## 给开发者的边界
- 本目录**只写 DomainIntelData**，不写别处；**不读** DomainIntelApp 的任何代码。
- 展示与删除由 DomainIntelApp 负责，本目录不含 UI。
