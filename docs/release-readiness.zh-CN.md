# IntDog 测试版发行门槛

[English](release-readiness.md)

本文件定义发行规则，不代表当前工作树已经通过。每个待发布 revision 都必须重新产生证据。

## 产物

| 平台 | 架构 | 文件 |
| --- | --- | --- |
| Windows | x64 | `IntDog-<版本>-windows-x64.exe` |
| macOS | Apple Silicon arm64 | `IntDog-<版本>-macos-arm64.dmg` |
| Linux | x64 | `IntDog-<版本>-linux-x64.AppImage` |

每个包只包含本平台的 Electron 桌面壳和同平台 PyInstaller sidecar。WSL 或源码快捷方式不是 Windows 安装包。三个平台共享业务实现；Electron、API、Schema、Python 运行时或 Web UI 改变时，三平台任务必须全部重跑。

## 测试版与稳定版

- 测试版使用预发布版本并标记 GitHub Pre-release，可以未签名，但必须说明 SmartScreen/Gatekeeper 风险并发布 SHA-256。
- Windows 稳定版必须签名。macOS 稳定版必须签名并公证。
- 缺少签名凭据时不得把测试 artifact 标成稳定版。
- 现有 Windows、macOS、Linux Issue 应幂等复用；只有不存在时才新建。

## 必须通过的门槛

1. 同一 revision 通过 Python 测试、Web 测试与构建、Desktop 测试、类型/OpenAPI 合同、仓库卫生与密钥扫描。
2. 三个平台分别完成安装或挂载、首次启动、后端就绪、关闭、进程/端口释放和再次启动。
3. 使用隔离临时数据完成：创建行业、Agent 自动发现与手动命令文件选择、版本/登录诊断、首次任务、八个主页面、任务取消/重试、删除/恢复和安全退出。Windows 必须覆盖 `.cmd` 包装器；macOS/Linux 必须覆盖从桌面启动时缺少终端 profile PATH 的情况。
4. 无模型流程必须产生真实且可判定的最小结果，不能只生成任务包后宣称研究成功。
5. 真实已登录 Agent 必须先通过 UI 的固定标记最小调用，再至少完成一次不含凭据泄漏的深度任务；静态 MCP 配置存在不能代替该证据。不可用平台或外部网络门槛必须明确标为未验证。
6. 任何直接研究任务缺少必要产物时必须是 `partial` 或 `failed`，不能是 `completed`。

## 安全与数据边界

- API 只监听 `127.0.0.1`，并校验会话、Host 和 Origin。
- 桌面 Key 存在操作系统凭据存储中，经一次性匿名管道传入 sidecar，不进入日志、命令行或子进程环境。
- 测试使用临时数据根；行业数据、联网采集结果、日志和个人路径不得进入发布提交。
- 后台计划只有用户主动启用后才能安装；权限可撤销，卸载默认保留用户数据。

## 结论规则

只有三平台 P0 门槛全部通过，才可标记 `READY_FOR_PUBLIC_TESTING`。缺少任一原生平台、真实 Agent 或外部采集证据时，结论必须保持 `NOT_READY` 或明确的部分就绪状态。历史 revision 的通过记录不能证明新 revision。
