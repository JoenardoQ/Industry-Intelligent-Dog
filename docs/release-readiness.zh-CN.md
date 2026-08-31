# IntDog 4.0 正式发行就绪合同

## 发行目标

本次基线的最终发行目标扩展为 Windows、macOS 与 Linux 三个平台。当前机器上的 Windows 11 + WSL `Ubuntu-D` 路径用于已有行为回归，但正式产物必须分别在三个原生宿主构建，不能把 WSL 或源码启动视为跨平台安装包。

本次已创建三个发行跟踪 Issue，并允许在原生门槛通过后创建 `4.0.0-test.1` 未签名 GitHub Pre-release；稳定版仍受签名门槛约束。本次尚未获得 Git commit/push 的单独授权；不调用付费模型，不发送邮件，不执行真实联网采集，不永久删除生产数据，也不承诺商业数据库级覆盖。

## 支持边界

- 目标支持路径：平台原生桌面壳 → 同平台后端 sidecar → 随机 localhost 端口与会话凭证 → 内嵌 Chromium 工作台。Windows WSL 快捷方式降为开发兼容入口，不作为发行包。
- 数据：生产数据只读检查；写入、删除、恢复、任务和错误注入使用隔离的临时数据根。
- 网络：应用只监听 `127.0.0.1`；会话令牌、Host 与 Origin 必须通过边界检查。
- 兼容性：Windows x64、macOS arm64/x64、Linux x64 分别产出安装包；每个平台必须由对应 runner 原生构建与烟雾测试。当前已有本机 Windows/WSL 兼容入口与 Linux x64 AppImage 运行证据；Windows/macOS 原生安装包仍须 CI 证明。

## 已批准的打包架构

采用 Electron 桌面壳 + 单一 PyInstaller Python/FastAPI/CLI sidecar + `electron-builder`。Electron 提供三平台一致的 Chromium、窗口与生命周期，单一 sidecar 同时承担 API 与研究命令，避免重复捆绑 Python。CI 在 Windows/macOS/Linux 原生 runner 分别生成 Windows x64 `.exe`、macOS universal `.dmg` 和 Linux x64 `.AppImage`；每个包只携带本平台运行时，不混装其他平台二进制。

三个平台各有一个 GitHub Issue、一个独立构建任务和一个平台 Release。共享 Electron 主进程、Python sidecar 接口、Schema 或整体架构发生变化时，三项平台任务必须全部重新构建并通过；禁止维护三个分叉的业务实现。Electron 自带 Chromium，因此即使分平台仍有固定体积成本；分发拆分的收益是避免跨平台二进制混装，而不是消除 Chromium。

Windows 和 macOS 稳定版 Release 必须签名，macOS 还必须完成公证。凭证缺失时 CI 只可产生明确标注的测试 artifact 或 Pre-release，不能创建稳定版 Release。

未签名测试版不需要上述凭证。测试版必须使用 `4.0.0-test.1` 一类预发布版本、勾选 GitHub Pre-release，并在发行说明中明确 Windows SmartScreen 或 macOS Gatekeeper 可能要求用户手动允许。三个测试版入口不继承仓库签名 Secrets，防止测试构建被意外当作正式签名产物。

平台发行分别由 [Windows Issue #1](https://github.com/JoenardoQ/Industry-Intelligent-Dog/issues/1)、[macOS Issue #2](https://github.com/JoenardoQ/Industry-Intelligent-Dog/issues/2) 与 [Linux Issue #3](https://github.com/JoenardoQ/Industry-Intelligent-Dog/issues/3) 跟踪。平台门槛由 `.github/workflows/platform-gates.yml` 同时触发；三个 Pre-release 入口保持独立。首个测试版标签分别为 `v4.0.0-test.1-windows`、`v4.0.0-test.1-macos` 与 `v4.0.0-test.1-linux`。

## 当前原生证据

- Linux x64 sidecar：17 MB；同一冻结文件同时通过 `cli industries`、FastAPI 健康检查、会话保护和正常关机。
- Linux x64 AppImage：142,063,476 字节（约 135.5 MiB），SHA-256 为 `863844d3f8c1a26c598199c4113796587b87f9fc7bca8c1361a39d7ed0e777d2`；在 WSLg 中以隔离数据与配置目录连续完成两次 UI/后端启动、就绪、正常关闭与重开。
- 安装包只包含当前平台 sidecar。Electron/Chromium 是主要体积来源；Python sidecar 不是体积主因。
- 当前结论仍为 `NOT_READY`：Windows 原生 NSIS 与 macOS universal DMG 尚无对应宿主构建、签名/公证及安装生命周期证据。

## 风险覆盖矩阵

| ID | 风险/要求 | 状态与交互 | 故障模式 | 测试层与判定 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| R1 | 首次与再次启动 | 无环境、已就绪、窗口关闭后重开 | 路径含空格、UNC、空 ExitCode、端口残留 | Windows 快捷方式实测；窗口、健康接口和日志均成功 | P0 |
| R2 | 单实例与关闭 | 启动中、运行中、正常关闭、异常退出 | 双服务、孤儿进程、关闭后端口仍占用 | 进程/端口/关闭 API 状态机 | P0 |
| R3 | 会话边界 | 有效、缺失、错误 token；合法/非法 Host 与 Origin | 未授权读取或关闭 | API 决策表，预期 2xx/4xx | P0 |
| R4 | 七个主页面 | 空数据、典型数据、大列表、延迟加载 | 白屏、路由错误、资源 404、密集/溢出布局 | 浏览器 AX/DOM、网络日志、截图 | P0 |
| R5 | 行业生命周期 | 新建、重名、重命名、归档、恢复 | 覆盖数据、非法目录、部分写入 | 隔离数据 API+浏览器，状态与审计回读 | P0 |
| R6 | 每日情报 | 搜索、排序、分页、多选、删除、恢复 | 跨页误删、重复、空态、错误来源 | 合成数据端到端，SQLite/JSON 双向判定 | P0 |
| R7 | 来源治理 | active/manual/reserve、手动来源、重复 URL | 储备源被抓取、目录被截断、同源占位 | 合同测试与 UI 状态筛选 | P0 |
| R8 | 任务生命周期 | queued/running/completed/partial/failed/cancelled/interrupted | 卡死、重试错误、日志泄密、取消不收敛 | 故障注入、持久状态与进程树判定 | P0 |
| R9 | 报告与 Markdown | 无报告、有效报告、非法路径、图表 sidecar | 路径越界、空白阅读器、渲染崩溃 | API 与浏览器内容判定 | P1 |
| R10 | 时间与调度 | 日/周/月/季、重启补跑、时区边界 | 重复入队、错误 checkpoint、邮件误发 | 确定性时钟/状态测试 | P0 |
| R11 | 迁移与恢复 | 空库、旧库、脏兼容视图、重复执行 | 迁移非幂等、数据丢失、锁残留 | 临时副本、完整性与幂等检查 | P0 |
| R12 | 性能与容量 | 6,800+ 文档、50 条分页、87 来源 | 首屏超时、无界响应、内存爆涨 | 基准脚本与响应上限 | P1 |
| R13 | 可访问性与显示 | 键盘、焦点、缩放、中文、窄/宽屏 | 不可操作、文字截断、低对比 | axe/AX、视口与视觉检查 | P1 |
| R14 | 发布卫生 | 构建产物、依赖、日志、缓存、密钥 | 缺文件、绝对旧路径、秘密或测试垃圾入包 | 清单、搜索、构建与差异检查 | P0 |

## 验收条件

1. P0 自动化测试、类型检查、生产构建、Python 编译、SQLite 完整性与 OpenAPI 合同通过。
2. Windows、macOS、Linux 原生产物分别完成“安装 → 启动 → 首页和测试行业数据加载 → 关闭 → 端口/sidecar 释放 → 再启动”；Windows WSL 快捷方式另作兼容回归。
3. 隔离数据浏览器旅程覆盖七页、行业与每日情报的关键可恢复写操作；无未处理前端异常、主资源 4xx/5xx 或严重可访问性错误。
4. P0 缺陷修复后重复相关门槛；无法验证的宿主或外部依赖明确列为限制。
5. 三个平台都通过 P0 门槛后才允许 `READY`；缺少任一平台原生产物证据时结论必须是 `NOT_READY`。

## 证据与产物

自动化命令、用户旅程结果、截图、性能数字、缺陷与修复记录写入 `docs/release-evidence/`。测试不得复制生产数据库、令牌、用户路径外的个人文件或联网内容到仓库。
