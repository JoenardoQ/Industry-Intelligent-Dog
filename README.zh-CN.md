# IntDog 行业情报系统

[English documentation](README.md)

数据去重和动态来源池的工程边界见[中文契约](docs/source-governance.zh-CN.md)与[English contract](docs/source-governance.md)。

> 版本 4.0 Preview。模型产物默认是待复核草稿，不构成事实确认或投资建议。

IntDog 是一个本地优先的行业情报工作台：先建立信息源和产业链，再持续采集新闻、
论文、GitHub、融资、招聘和管理层动态，最后生成带引用的周期报告与行业研究。

## 系统目标

IntDog 不预设用户必须回答某一组问题。它的默认目标是建立尽可能完整、可追溯、持续扩展的行业知识体系，帮助用户拓宽知识边界，并形成对产业链各节点、主要及长尾企业、研究机构和技术路线的系统认知。

- **全面发现**：覆盖子领域、上下游、产品、技术、企业、研究组、人物、标准、政策和资本活动。
- **开放世界**：不把当前数据库当作行业全集；持续记录已知、未知、待核实和新出现对象。
- **长尾优先可见**：除头部公司外，主动发现细分节点中的中小企业、初创公司和研究团队。
- **证据可追溯**：结论关联原始来源、时间、适用范围和冲突证据。
- **跨行业复用**：同一企业、技术或机构使用规范实体，在多个行业中保留不同角色。

## 系统组成

| 组件 | 职责 | 是否联网 |
|---|---|---|
| `DomainIntelSearch` | 搜索、采集、审计、验证、知识建模和报告生成 | 是 |
| `intdog_core` | 统一 Schema、SQLite、实体/证据、任务锁、迁移和应用服务 | 否 |
| `DomainIntelData` | 保存结构化事实库与可移植 JSON/Markdown 产物 | 否 |
| `DomainIntelWeb` | React 研究工作台与本地 FastAPI 边界 | 浏览可离线 |
| `DomainIntelApp` | 桌面启动、隔离运行环境与通用任务运行时 | 否 |
| `DomainIntelDesktop` | Electron 桌面壳与三平台原生打包 | 否 |

当前主路径：

```text
来源连接器 → 采集与标准化 → intdog_core → 情报/知识引擎 → 查询/报告 → App/Agent/邮件
```

`Intelligence Lab` 在事实库之上提供证据缺口编译、来源健康度观测、可解释产业链情景传播
和知识边界研究议程；其推演与建议不会自动成为事实。详细契约见
[Intelligence Lab](DomainIntelSearch/INTELLIGENCE_LAB.md)。

默认桌面入口采用独立 Chrome app-mode 窗口承载 React 工作台，没有浏览器地址栏；加载窗
负责创建 Python/前端运行环境，本地 API 仅监听 `127.0.0.1`，关闭应用窗口或在系统状态中
退出会停止服务。4.0 起只有这一套产品 UI；旧 Tk 工作台已经移除。

SQLite 保存规范实体、文档、持久 Story、关系、主张、证据、来源健康和任务状态；文件系统保存原始材料、JSON 兼容视图、Markdown 和图表。报告是证据系统的消费者，不负责决定事实；App 的业务写入统一经过 application service。

## 三种执行模式

| 模式 | 适合 | 密钥/费用 | 结果 |
|---|---|---|---|
| 本机 Agent | 已登录 Codex CLI 或 Claude Code；其他 Agent 走 MCP/任务包 | 由 Agent 自己管理 | 直接生成或交接 |
| API | OpenAI、DeepSeek、Qwen 或 Azure OpenAI | 需要 Key，按 API 计费 | 直接生成草稿 |
| 任务包 | 暂不调用模型 | 无模型费用 | JSON prompt，尚非报告 |

系统不会把“任务包已创建”或“模型已生成”标成已审核结论。
真实 API/SMTP 密钥应通过环境变量注入，不写入受版本控制的配置。非本机模型端点必须
使用 HTTPS；本地数据分享默认只监听 localhost，局域网暴露必须显式开启。

## 用户安装与首次使用

> 已知问题：`4.0.0-test.1` 的首次使用与智能体连接没有达到本节合同，暂不建议普通用户安装。
> 修复版通过新的安装—引导—Provider—首次任务门槛后才会替换该版本。

IntDog 安装包包含应用与本地后端，但**不包含模型账号或额度**。如果只查看已有数据、管理行业
或创建任务包，不需要模型；如果要生成研究内容，必须另外完成一种 Provider 配置。

### Windows 10/11 x64

1. 从 GitHub Release 下载 `IntDog-<版本>-windows-x64.exe`，不要下载 Source code 压缩包。
2. 双击安装器并选择安装目录；安装完成后使用桌面或开始菜单中的 IntDog 快捷方式。
3. 测试版未签名。如 SmartScreen 警告，先核对发布页文件名与 SHA-256，再决定是否运行。
4. 第一次打开后等待“本地运行组件”和“数据目录”显示正常。
5. 在首次启动向导选择：
   - **本机 Agent**：Codex CLI 和 Claude Code 可直接执行；DeepSeek Harness、Work Buddy、
     Qwen Code、CodeBuddy、Kimi、Gemini CLI、OpenCode 等通过 MCP/任务包交接；
   - **API**：选择 OpenAI、DeepSeek、Qwen 或 Azure OpenAI，输入 API Key 与模型；Key 由操作系统加密存储；
   - **任务包**：无需 Key，但只生成 prompt，不直接生成研究报告。
6. 创建行业，点击“初始化行业研究”，随后在“任务中心”查看阶段、日志与结果。
7. 其他 Agent 可在“连接设置”复制 MCP 配置，或在“研究助手”导出任务；导回结果固定进入待复核区。

如果双击后没有窗口，在 `%APPDATA%/intdog-desktop/logs/backend.log` 查看后端日志。不要公开
上传含 API Key、令牌或个人路径的完整日志。

### macOS 与 Linux

- macOS 测试包只支持 Apple Silicon arm64。打开 DMG 后把 IntDog 拖入 Applications；
  未签名测试包可能触发 Gatekeeper。
- Linux x64 下载 AppImage 后赋予执行权限：`chmod +x IntDog-*.AppImage`。
- 两个平台的本机 Agent 模式也必须先安装相应 CLI 并完成其公开登录流程；也可选择 API 或任务包。

完整状态含义和故障恢复见[安装与智能体连接指南](docs/onboarding-and-installation.zh-CN.md)。

### 从源码启动（开发者）

```bash
cd "/home/joenardo/My Projects/IntDog"
./run_intdog.sh
```

仓库本身可移动，不依赖 `/mnt/d` 或固定盘符。源码模式会创建隔离的 Python/Web 运行环境。

### 命令行

```bash
cd DomainIntelSearch
python -m pip install -e .

# 仅创建目录、种子来源和任务骨架
python -m src.main init-industry --industry 芯片

# 搜索并审计来源，再构建产业链和实体
python -m src.main bootstrap-industry --industry 芯片 --provider codex

# 抓取每日六类数据
python -m src.main crawl-daily --industry 芯片

# 编译证据与来源覆盖，形成研究议程
python -m src.main run-lab --industry 芯片

# 对明确事件做可解释的产业链情景传播
python -m src.main simulate-chain --industry 芯片 --event "先进 GPU 出口限制"

# 打开桌面应用
cd ..
./run_intdog.sh
```

`--industry` 可使用“芯片/半导体/ai/人工智能”等档案别名；`--folder` 可直接指定
`Chips`、`AI` 等数据目录。

## 原生发行边界

原生包采用 Electron 桌面壳与单一 PyInstaller API/CLI sidecar。Windows x64 生成 NSIS
`.exe`，macOS Apple Silicon arm64 生成 `.dmg`，Linux x64 生成 `.AppImage`；每个安装包只携带
本平台运行时。共享架构、API、Schema、运行时或 UI 发生变化时，三平台门槛必须同时重跑。

`4.0.0-test.*` 标记为 GitHub Pre-release 且不签名，因此 Windows SmartScreen 或 macOS
Gatekeeper 可能要求用户手动允许。稳定版 Windows/macOS 需要签名，macOS 还需要公证。详见
[发行合同](docs/release-readiness.zh-CN.md)与[English release contract](docs/release-readiness.md)。

## 主要产物

| 位置 | 内容 |
|---|---|
| `sources.json` | 9 类信息源、可达性、来源地区和人工关注状态 |
| `one_time/knowledge/` | 行业 → 产业链 → 企业/机构等实体 |
| `periodic/daily/` | 新闻、论文、GitHub、融资、招聘、CEO 发言 |
| `periodic/{weekly,monthly,quarterly}/` | 周/月/季任务、Markdown 和图表元数据 |
| `one_time/reports/` | 五年趋势、两年热点、半年技术报告 |
| `one_time/research/history/` | 长周期逐桶 manifest、供应商降级和可续跑状态 |
| `one_time/landscape/` | 竞争分层、Watchlist 和历史快照 |

### 产物状态

| 状态/概念 | 含义 |
|---|---|
| candidate | 搜索候选，尚未通过结构和来源审计 |
| collected | 已抓取，不代表已被独立来源印证 |
| verified/corroborated | 有一手证据或多个独立发布者印证 |
| draft_review_required | 模型已成文，仍需人工检查引用和数字 |
| reviewed/published | 当前不会自动授予，需人工流程确认 |

来源刷新、质量诊断、周期生成、深度研究和 Agent 接入的完整命令见 [Search 手册](DomainIntelSearch/README.md)。

默认 Web 工作台包含行业概览、每日情报、研究产物、信息源、研究助手、任务中心和系统状态
七个按需加载页面。每日情报默认每页 50 条，由服务端排序、筛选和分页；“全选”只选择已加载
条目。信息源卡片显示采集状态以及最近检查/成功时间。Overview 来源指标统计已采集文档的中国 / 国外 / 未知分布。
规范来源字段保持为名称、类别、来源地区、层级、访问、可达性、监测状态和发布者；Web 卡片
按需折叠展示，不改变底层字段。

## 调度边界

- 默认 Web 工作台持久化每日、周、月、季计划、周期键、下次执行、最近成功和错误；应用重启后
  可补跑错过的周期，租约与周期键防止两个进程重复入队。
- 系统状态页可启停、设置本地时间和立即运行。默认 Web 调度明确禁用邮件，只生成本地产物。
- `crawl-weekly/monthly/quarterly` 负责聚合数据和任务元信息；模型成文由生成任务完成。
- Web 调度是唯一计划所有者；邮件投递始终禁用。

## 可信度与已知边界

- 来源池覆盖良好不等于每日抓取结果均衡；`doctor` 会单独报告实际分布。
- 社交媒体和自媒体只作为线索；官方披露、监管、统计和同行评审材料优先。
- 无 RSS、付费墙或反爬的优质来源保留为“推荐·人工关注”，不会冒充自动采集结果。
- 当前不具备商业数据库级的全球融资、招聘、海关、实时行情或完整社交平台覆盖。
- 竞争格局是证据骨架：证据不足的公司进入 Watchlist，不自动认定为 Leader/Challenger。
- “没有发现”不等于“不存在”；系统应同时报告覆盖率、空白节点、失效来源和待验证候选。

## 演进优先级

1. **可信数据内核**：基础能力已落地；继续加强迁移审计、Schema 校验和恢复工具。
2. **发现与验证算法**：实体消歧、转载识别、事件聚类、主张—证据关系和覆盖矩阵。
3. **行业知识网络**：时态产业链、跨行业实体、研究组与企业长尾、学习依赖图和影响传播。

新增报告和数据源应建立在上述内核之上，避免用更多模型文本掩盖底层证据、覆盖和一致性缺口。

更完整的实现边界见 [当前实现状态](IMPLEMENTATION_STATUS.zh-CN.md)。

## 文档导航

- [Search：安装、命令、执行模式和故障排查](DomainIntelSearch/README.md)
- [Data：目录、字段、状态和备份契约](DomainIntelData/README.md)
- [App：图形界面任务手册](DomainIntelApp/README.md)
- [DESIGN.zh-CN.md：当前架构](DESIGN.zh-CN.md)

## 开发验证

```bash
python -m pytest DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests -q
cd DomainIntelWeb && npm run build
```

数据默认完全保存在 `DomainIntelData/`；删除项进入 `_trash/`，整个目录可备份。
系统状态页可列出和恢复已归档行业、已删除的每日情报批次；同名行业不会被静默覆盖，
重复文档会跳过并留下审计记录。永久删除仍不在默认工作流中。结构化内核已修复连接泄漏和
“读取缺失行业时隐式注册”，并通过
dirty view 记录与 `reconcile-data` 重建 SQLite 之外的核心 JSON 视图。详见
[IMPLEMENTATION_STATUS.zh-CN.md](IMPLEMENTATION_STATUS.zh-CN.md)。
