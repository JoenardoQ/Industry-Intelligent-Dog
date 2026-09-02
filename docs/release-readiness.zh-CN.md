# IntDog 测试版发行门槛

[English](release-readiness.md)

本文件定义发行规则，不代表当前工作树已经通过。每个待发布 revision 都必须重新产生证据。

## 产物

| 平台 | 架构 | 文件 |
| --- | --- | --- |
| Windows | x64 | `IntDog-<版本>-windows-x64.exe` |
| macOS | Apple Silicon arm64 | `IntDog-<版本>-macos-arm64.dmg` |
| Linux | x64 | `IntDog-<版本>-linux-x86_64.AppImage` |

每个包只包含本平台的 Electron 桌面壳和同平台 PyInstaller sidecar。WSL 或源码快捷方式不是 Windows 安装包。三个平台共享业务实现；Electron、API、Schema、Python 运行时或 Web UI 改变时，三平台任务必须全部重跑。

## 测试版与稳定版

- 测试版使用预发布版本并标记 GitHub Pre-release，可以未签名，但必须说明 SmartScreen/Gatekeeper 风险并发布 SHA-256。
- Windows 稳定版必须签名。macOS 稳定版必须签名并公证。
- 缺少签名凭据时不得把测试 artifact 标成稳定版。
- 现有 Windows、macOS、Linux Issue 应幂等复用；只有不存在时才新建。

一次 `Release · Three platforms` 调度会并行构建三个原生安装包。每个安装包只构建一次，
在对应平台 Runner 上完成测试后上传为 Actions artifact。只有整个矩阵全部成功，统一发布
任务才会校验三个安装包、校验文件、证据清单和源码 revision，随后准备三个 Draft Release，
并把这批已测试产物发布为三个 Pre-release。发布任务不会再次构建安装包。

## 必须通过的门槛

1. 同一 revision 通过 Python 测试、Web 测试与构建、Desktop 测试、类型/OpenAPI 合同、仓库卫生与密钥扫描。
2. 三个平台分别完成安装或挂载、首次启动、后端就绪、关闭、进程/端口释放和再次启动。
3. 使用隔离临时数据完成：创建行业、Agent 自动发现与手动命令文件选择、版本/登录诊断、首次任务、八个主页面、任务取消/重试、删除/恢复和安全退出。Windows 必须覆盖 `.cmd` 包装器；macOS/Linux 必须覆盖从桌面启动时缺少终端 profile PATH 的情况。
4. 无模型流程必须产生真实且可判定的最小结果，不能只生成任务包后宣称研究成功。
5. 真实已登录 Agent 必须先通过 UI 的固定标记最小调用，再至少完成一次不含凭据泄漏的深度任务；静态 MCP 配置存在不能代替该证据。不可用平台或外部网络门槛必须明确标为未验证。
6. 任何直接研究任务缺少必要产物时必须是 `partial` 或 `failed`，不能是 `completed`。
7. `VERSION`、Web、Desktop、MCP、安装包名称和发行参数必须一致；Python 元数据使用已说明的 PEP 440 映射。
8. 进度事件被拆分后仍保留任务状态；初始化完成后必须显示覆盖缺口和直接下一步。

### 首次使用可追踪性

| 需求 | 确定性证据 | 原生/真实环境证据 |
| --- | --- | --- |
| BW-01–03 · API 配置与诊断 | Provider/首次引导测试 | 经授权的真实探测 |
| BW-04–07 · 初始化、门槛与重试 | 初始化/API 测试 | 真实 Provider 运行 |
| BW-08 · 排队与取消 | 任务运行时测试 | 前台/后台竞争 |
| BW-09 · 可访问首次引导状态 | Web 测试 | 安装版渲染器流程 |
| BW-10 · 凭据与生命周期 | Desktop 契约测试 | 三个原生平台 |
| BW-11–12 · 结果真实性与兼容 | Web/Python 回归 | 现有数据冷启动 |

## 安全与数据边界

- API 只监听 `127.0.0.1`，并校验会话、Host 和 Origin。
- 桌面 Key 存在操作系统凭据存储中，经一次性匿名管道传入 sidecar，不进入日志、命令行或子进程环境。
- 测试使用临时数据根；行业数据、联网采集结果、日志和个人路径不得进入发布提交。
- 后台计划只有用户主动启用后才能安装；权限可撤销，卸载默认保留用户数据。

## 结论规则

只有三平台 P0 门槛全部通过，才可标记 `READY_FOR_PUBLIC_TESTING`。缺少任一原生平台、真实 Agent 或外部采集证据时，结论必须保持 `NOT_READY` 或明确的部分就绪状态。历史 revision 的通过记录不能证明新 revision。
