# IntDog 领域情报系统

> 当前版本：2.1 Beta。真实实现边界见 [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md)。
> “任务包已生成”不等于研究报告已经完成；Agent 产物在复核前一律视为草稿。

一个「抓取 → 存储 → 展示」三段分离的领域情报工具：自动从网络与 AI 抓取某行业的
新闻、论文、GitHub、融资、招聘、CEO 发言、财报，按行业分目录存成干净的数据，
再用图形界面读出来、也能删除。支持三层知识结构（行业→产业链→企业/高校研究组）。

> 适合：想持续跟踪一个或多个行业（芯片、AI、新能源…），但不想手动翻新闻的人。

---

## 它是怎么组成的（5 个部分）

```
IntDog/
├── IntDog.exe            ① 可执行程序（打包后的入口，当前先不打包）
├── README.md             ② 本说明
├── DomainIntelSearch/    ③ 抓取引擎：联网 + 用 LLM/agent 抓信息
├── DomainIntelData/      ④ 数据层：按行业分目录存文本 + 图片 + 格式契约
└── DomainIntelApp/       ⑤ 图形界面：读取/删除 DomainIntelData，定期更新开关
```

| 部分 | 干什么 | 关键约束 |
|------|--------|----------|
| ③ `DomainIntelSearch/` | **只负责抓取**：信息源发现、三层知识、一次性深爬、定期监控 | 唯一需联网/用 LLM 的部分；**不绑定任何 agent 平台** |
| ④ `DomainIntelData/` | **只负责存储**：`Chips/`、`AI/`… 每个行业一个文件夹 | `skill/spec.md` 规定抓什么+怎么存，是唯一契约 |
| ⑤ `DomainIntelApp/` | **展示与调度**：读取/删除数据，触发 Search 子进程 | 自身不解析网页；无内容编辑功能 |

**一句话流程**：`Search` 抓 → 按行业存进 `Data` → `App` 读给你看、可删。

---

## 快速开始

### 1. 装依赖（只装一次）
```bash
cd DomainIntelSearch
python -m pip install -e .
```

### 2. 初始化一个行业（信息源 + 三层知识骨架 + 报告任务包）
```bash
python -m src.main init-industry --industry 芯片     # 数据进 DomainIntelData/Chips/
```

### 3. 抓一次每日情报（六类）
```bash
python -m src.main crawl-daily --industry 芯片       # 新闻/论文/GitHub/融资/招聘/CEO
```

### 4. 打开界面看
```bash
cd ../DomainIntelApp
python -m desktop.main        # 或双击 run_app.bat
```
界面里：选行业 → 看「每日情报」（每条标题+摘要+链接）→ 想持续更新就点开右上角**「定期更新」开关**。

---

## 核心概念

**三层知识结构**（在「知识结构」标签看）
```
行业：芯片
 └─ 产业链：设计验证
 │    ├─ [企业] 英伟达（美国）
 │    └─ [高校/研究组] 港科广吕杨迪组（中国）
 └─ 产业链：制造
      └─ [企业] 台积电（中国台湾）
```

**定期监控**（开「定期更新」后自动跑，存 `periodic/`，与一次性深爬 `one_time/` 分开）

| 周期 | 内容 |
|------|------|
| 每天 | 新闻 / GitHub / 融资 / 招聘 / CEO发言 / 论文 |
| 每周 | 行业总结 |
| 每月 | 产业分析 |
| 每季 | 上市公司财报分析 |

**三份行业报告**（存 `one_time/reports/`）
近五年（着重**趋势**）、近两年（着重**流行**）、近半年（着重**技术**）。

---

## 最常用的几件事

| 我想… | 怎么做 |
|--------|--------|
| 新增一个行业 | `init-industry --industry <名>`；档案在 `DomainIntelSearch/config/industries/` 加 yaml |
| 加一家企业/高校到知识库 | `knowledge --industry X --name 英伟达 --etype company --chain 设计验证` |
| 看某行业该关注哪些信息源 | `discover-sources --industry X`，或界面「信息源」标签 |
| 生成 5年/2年/半年 行业报告 | `report-tasks --industry X`，把任务包交给任意 AI 执行 |
| 验证新闻可信度（多源交叉） | `verify --industry X`；界面每日情报卡片显示「可信度+源数」徽标，点开看互相印证的来源 |
| 检查数据质量与新鲜度 | `doctor --industry X`；只读检查缺字段、旧分类、来源多样性和知识库引用 |
| 看竞争格局（四类玩家） | `landscape --industry X`；界面「研究助手」标签查看 |
| 深挖某事件的影响 | `impact --industry X --event "美国限制GPU出口"` |
| 生成深度研究报告 | `deep-reports --industry X`（季度/产业链/格局/市场），任务包交给任意 AI 回写 |
| 让其它 Agent 读数据 | `mcp-serve` 启动 MCP Server，客户端按统一协议调用 10 个工具 |
| 删错抓的条目 | 界面「每日情报」→ 该条卡片点「删除」 |
| 查看真实实现边界 | 阅读 `IMPLEMENTATION_STATUS.md`，区分代码能力、任务包与路线图 |

---

## 各部分的详细说明
- 抓取引擎怎么用 → [`DomainIntelSearch/README.md`](DomainIntelSearch/README.md)
- 数据存成什么样 → [`DomainIntelData/README.md`](DomainIntelData/README.md)
- 界面怎么用 → [`DomainIntelApp/README.md`](DomainIntelApp/README.md)

---

## API 参考（CLI 命令全集）

> 所有命令在 `DomainIntelSearch/` 目录下运行。完整规格见 [`DESIGN.md` §6](DESIGN.md)。

### 行业初始化与信息源

```bash
python -m src.main init-industry --industry 芯片      # 建文件夹+信息源+知识骨架+报告任务
python -m src.main discover-sources --industry 芯片   # 查看/扩充信息源（7 类）
python -m src.main industries                          # 列出全部行业文件夹
```

### 定期监控

```bash
python -m src.main crawl-daily --industry 芯片       # 每天：新闻/GitHub/融资/招聘/CEO/论文
python -m src.main crawl-weekly --industry 芯片      # 每周：行业总结
python -m src.main crawl-monthly --industry 芯片     # 每月：产业分析
python -m src.main crawl-quarterly --industry 芯片   # 每季：财报分析
```

### 知识结构与报告

```bash
python -m src.main knowledge --industry 芯片          # 查看三层知识树
python -m src.main knowledge --industry 芯片 \        # 添加实体
    --name 英伟达 --etype company --chain 设计验证 --country 美国
python -m src.main report-tasks --industry 芯片       # 生成三份报告任务包
```

### 研究助手（验证 / 格局 / 影响 / 深报 / MCP）

```bash
python -m src.main verify --industry 芯片             # ① 多源交叉验证：跨 3 天归并同一故事，
                                                     #    回写 credibility/源数/references
                                                     #    （--days 7 可扩大窗口）
python -m src.main landscape --industry 芯片          # ③ 竞争格局四类玩家 + 历史快照
python -m src.main impact --industry 芯片             # ② 检测行业级事件清单
python -m src.main impact --industry 芯片 \
    --event "美国限制GPU出口"                          # ② 事件→公司/供应链/论文/政策+分析任务包
python -m src.main deep-reports --industry 芯片       # ④ 四份深度研究报告任务包
                                                     #    （季度/产业链/竞争格局/市场）
python -m src.main deep-reports --industry 芯片 --rtype chain   # 只生成某一种
python -m src.main mcp-serve                          # ⑤ MCP Server（stdio，10 个只读工具）
```

**⑤ MCP 接入**（让任意 Agent 按统一协议读数据）：在 MCP 客户端配置中加入——

```json
{
  "mcpServers": {
    "domain-intel": {
      "command": "<venv>/Scripts/python.exe",
      "args": ["-m", "src.main", "mcp-serve"],
      "cwd": "D:/IntDog/DomainIntelSearch"
    }
  }
}
```

工具清单：`list_industries / get_daily / get_knowledge / get_sources / get_landscape /
get_impact_events / get_impact / list_report_tasks / read_report / search_items`。

### IIOS 深度研究

```bash
python -m src.main plan --industry 半导体              # 全量研究计划+7个Agent任务包
python -m src.main agent --name company --industry 半导体
python -m src.main execute-tasks --industry 半导体 \
  --task-file ../DomainIntelData/Chips/one_time/research/tasks/company.json \
  --provider openai                                      # 明确调用付费 API，结果状态为 draft
python -m src.main kg --build --industry 半导体        # 知识图谱构建
python -m src.main kg --entity 台积电 --depth 2        # 实体邻居查询
python -m src.main modules                             # 17个可组合模块
```

研究 Agent 统一写入 `DomainIntelData/<行业>/one_time/research/`。需要直接调用 API 时，
在配置中显式填写 `llm.model`，通过环境变量提供密钥，再运行：

```bash
python -m src.main brief --provider openai
```

OpenAI 模式使用 Responses API；默认仍为不产生费用的任务包模式。

### 旧版命令（写入 `_archive/`，仍可用）

```bash
python -m src.main daily --industry 芯片 --days 1     # HTML 日报
python -m src.main weekly / timeline / collect / query
python -m src.main test-email / archive / serve
```

### DomainIntelApp 启动

```bash
cd DomainIntelApp && python -m desktop.main            # 命令行
# 或双击 DomainIntelApp/run_app.bat                    # Windows
# INTDOG_DATA_ROOT 环境变量覆盖数据根
```

---

## 部署方案

### 开发环境（3 步）

```bash
cd DomainIntelSearch && python -m pip install -e .
python -m src.main init-industry --industry 芯片         # 初始化行业
cd ../DomainIntelApp && python -m desktop.main            # 启动界面
```

### 无人值守定期监控

**Windows 计划任务**（推荐）：
```powershell
# 每天 08:00 抓取
$action = New-ScheduledTaskAction -Execute "python" `
    -Argument "-m src.main crawl-daily --folder Chips" `
    -WorkingDirectory "D:\IntDog\DomainIntelSearch"
Register-ScheduledTask -TaskName "IntDog-Chips-Daily" -Action $action `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 08:00)
```

**Linux/macOS cron**：
```cron
0 8 * * * cd /path/to/DomainIntelSearch && python -m src.main crawl-daily --folder Chips
0 9 * * 1 cd /path/to/DomainIntelSearch && python -m src.main crawl-weekly --folder Chips
0 10 1 * * cd /path/to/DomainIntelSearch && python -m src.main crawl-monthly --folder Chips
```

### 数据备份

整个 `DomainIntelData/` 文件夹直接拷贝即可备份（所有数据自包含）。

### 完整设计文档

见 [`DESIGN.md`](DESIGN.md) —— 它包含长期设计背景；当前完成度以
[`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) 为准。

---

## 常见问题（小白向）

**Q：不会写代码能用吗？**
A：能。日常就是「init-industry 建行业 → 双击 run_app.bat → 开定期更新」。

**Q：必须联网吗？**
A：只有 DomainIntelSearch 抓取时需要。DomainIntelApp 看数据完全离线。

**Q：一定要用某个特定 AI 平台吗？**
A：不用。深度研究/报告以「模型无关任务包」产出，交给任何 AI 都行。

**Q：定期更新关了窗口还跑吗？**
A：界面内的调度线程随窗口关闭而停。要无人值守，用系统计划任务定时跑
   `python -m src.main crawl-daily --folder <行业>`。

**Q：数据安全吗？**
A：都在 `DomainIntelData/` 一个文件夹；删除的定期产物进 `_trash/` 回收站可恢复。
