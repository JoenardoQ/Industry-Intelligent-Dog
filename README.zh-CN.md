# IntDog 行业情报工作台

[English](README.md)

IntDog 是一个本地优先的桌面应用，用于建立和持续更新行业知识体系。它从信息源与产业链开始，采集新闻、论文、GitHub、融资、招聘和管理层动态，再生成带引用、状态与可视化的研究产物。

> 当前为 4.0 测试版。模型生成内容默认是待复核草稿，不是已确认事实、法律意见或投资建议。

## 能做什么

- 管理多个行业，并在行业概览中查看知识结构、产业链、实体、来源和文档。
- 发现并审查九类来源：政府/监管/标准、协会、机构博客、专业平台、自媒体、新闻、论文、公司披露和金融数据。
- 产业链按上下游建立有向关系；企业、研究组、人物、技术、产品和政策保留证据链接。
- 每日情报支持搜索、分类、来源排序、多选、全选和可恢复删除；事件可显示首次出现、热度与七日变化。
- 一键生成周、月、季、半年、两年和五年研究产物，以及产业链、竞争格局、市场和事件影响研究。
- 生成无需 IntDog 后端即可打开的单文件 HTML 简报，支持本地搜索、筛选、收藏、打印和 PDF。
- 使用已登录的本机 Agent、模型 API 或通用任务包；Agent 返回结果必须经过证据门槛才能进入事实库。
- 可选本地后台计划；默认不发送邮件，也不做云端同步或协作。

## 安装

安装包包含桌面界面和本地后端，但不包含模型账号、API 额度或第三方付费数据。

### Windows 10/11 x64

1. 在 GitHub Releases 的对应测试版中下载 `IntDog-<版本>-windows-x64.exe`，不要下载 “Source code”。
2. 双击安装；完成后从桌面或开始菜单打开 IntDog。
3. 测试包可能尚未签名。遇到 SmartScreen 时，先核对发布页中的文件名和 SHA-256，再决定是否继续。
4. 第一次打开会准备本地运行环境和数据目录，所需时间取决于磁盘性能。
5. 若窗口未出现，查看 `%APPDATA%\intdog-desktop\logs\backend.log`。公开反馈前请删除令牌、Key 和个人路径。

只复制仓库里的 `.exe`、后端文件或 WSL 快捷方式不能代替安装包。安装包必须来自同一版本的正式构建产物。

### macOS Apple Silicon

1. 下载 `IntDog-<版本>-macos-arm64.dmg`。
2. 打开 DMG，将 IntDog 拖入 Applications。
3. 未签名测试包可能被 Gatekeeper 拦截；核对校验值后，在系统隐私与安全设置中决定是否允许。

### Linux x64

1. 下载 `IntDog-<版本>-linux-x64.AppImage`。
2. 执行 `chmod +x IntDog-*.AppImage`。
3. 双击或在终端运行该 AppImage。

当前三个安装包是独立产物；共享代码改变后，Windows、macOS 和 Linux 门槛都必须重新通过。详细边界见[发行说明](docs/release-readiness.zh-CN.md)。

## 首次使用

1. 等待启动向导显示本地运行环境和数据目录正常。
2. 选择模型来源：
   - **本机 Agent**：先在系统终端安装并登录 Agent；IntDog 只运行公开的诊断命令，不读取 GUI 私有会话。
   - **API**：选择服务商并填写模型与 Key；桌面版把 Key 放在操作系统凭据存储中。
   - **任务包**：无需 Key，但只产生可交给任意 Agent 的任务，不会冒充完成的研究报告。
3. 创建行业名称和数据文件夹。
4. 点击“初始化行业研究”。任务会直接进入队列，当前页面显示真实阶段和耗时；任务中心提供完整日志、取消和重试。
5. 初始化完成后检查信息源候选、产业链顺序、实体覆盖和证据缺口，再开始每日采集或研究产物生成。

若 IntDog 没识别已经登录的 Agent：在“连接设置”重新诊断，并确认该 Agent 的 CLI 在启动 IntDog 的系统环境中可执行。Windows、WSL 和 macOS/Linux 的 PATH 彼此不一定相同。IntDog 对所有已登记 Agent 使用相同的可执行文件、版本、认证与能力诊断流程；无法直接调用的工具可通过 MCP 或任务包交接。

## 日常工作流

1. **行业概览**：检查知识结构、产业链图和各类数量，点击数字进入对应页面。
2. **每日情报**：抓取从前一日 04:00 到当前系统时间的内容；按标题、类别或来源排序并审核证据。
3. **信息源**：保留完整来源目录。稳定可抓取的来源进入自动监控；登录墙、付费墙或反爬来源保留为人工阅读推荐。
4. **研究产物**：周期任务从上次成功窗口继续；历史不足一个周期时，从当前时间向前补足一个完整周期。长周期采集按时间桶均匀取样，避免只堆积最近新闻。
5. **研究助手**：使用默认模板一键生成，也可修改任务类型、周期、事件或仅本次使用的 Agent。
6. **系统状态**：设置全局 Agent 和任务默认值。行业自定义会覆盖全局值，后续修改全局默认不会改写已有行业自定义。

默认检索预算相对旧基线提高：来源候选和常规采集为 1.5 倍，论文为 2 倍。论文同时覆盖成熟主题与前沿候选，用于发现可能形成新产业方向、但尚未得到行业验证的技术；这些内容保持 `candidate`，不会自动变成事实。

## 数据、隐私与状态

- SQLite 是实体、证据、来源、任务、审核和调度的事务数据源；原始材料、Markdown、HTML 和图表保存在本地数据目录。
- 行业数据、生成产物、日志、凭据和构建缓存均被 Git 忽略，不应提交到仓库。
- 删除的行业和每日情报先进入回收站。永久删除前先停止任务并备份整个数据目录。
- `candidate` 表示候选；`collected` 表示已采集；`verified/corroborated` 表示已通过相应证据规则；`draft_review_required` 表示模型成文但仍需人工复核。
- 有效网址不等于有效证据。正式断言还需通过语义支持、引用定位、数字/单位、声明类型、独立佐证和冲突检查。
- “未发现”不等于“不存在”。系统应同时显示覆盖缺口、失败来源和不确定性。首次采集没有稳定基线时显示“数据不足”，不显示虚假的漂移告警。

## 从源码启动（开发者）

需要 Git、Python 3.11+、Node.js 20+ 和 npm：

```bash
git clone https://github.com/JoenardoQ/Industry-Intelligent-Dog.git
cd Industry-Intelligent-Dog
./run_intdog.sh
```

首次启动会在忽略目录中准备隔离运行环境。不要把源码目录放在只读位置。Windows 用户开发源码时可在 WSL 中运行脚本；面向普通用户请使用 Windows 安装包。

常用开发验证：

```bash
.venv/bin/python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests
npm test --prefix DomainIntelWeb
npm run build --prefix DomainIntelWeb
npm test --prefix DomainIntelDesktop
```

## 项目结构

| 目录 | 作用 |
| --- | --- |
| `DomainIntelSearch` | 搜索、采集、去重、证据与知识算法、报告生成 |
| `DomainIntelWeb` | React 工作台和本地 FastAPI |
| `DomainIntelApp` | 启动、任务运行时和运行环境管理 |
| `DomainIntelDesktop` | Electron 桌面壳与三平台打包 |
| `DomainIntelData` | 本地数据模板；实际行业数据不进入 Git |

进一步阅读：[架构](DESIGN.zh-CN.md) · [安装与 Agent 连接](docs/onboarding-and-installation.zh-CN.md) · [信息源规则](docs/source-governance.zh-CN.md) · [发行门槛](docs/release-readiness.zh-CN.md)。
