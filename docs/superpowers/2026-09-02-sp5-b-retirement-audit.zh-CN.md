# SP5 B 旧发行面退役审计

日期：2026-09-02

删除必须同时满足四项证据：无运行时 import、无有效引用、无当前用户/安装文档依赖、已有通过测试的替代路径。

| 候选 | import/引用证据 | 文档/安装器证据 | 替代路径 | 决定 |
| --- | --- | --- | --- | --- |
| `DomainIntelSearch/src/services/worker.py` | 无运行时 import 或有效测试引用 | 不进入安装包，仅有历史/计划文字 | `src/background_worker.py` 与 Electron 当前用户后台服务 | 删除 |
| `DomainIntelApp/configure_openai_api.ps1` | 无运行时或测试引用 | 不进入安装包，当前文档不再推荐 | 首次向导 + OS `safeStorage` + 匿名凭据管道 | 删除 |
| `DomainIntelApp/configure_openai_api.bat` | 只调用已退役 PowerShell 脚本 | 不进入安装包，当前文档不再推荐 | 同一安全首次向导 | 删除 |
| `DomainIntelApp/launch_intdog.py` | 源码启动器和 launcher 测试仍引用 | 开发者源码文档间接依赖 | 原生安装器替代用户路径，但开发路径尚未完全迁移 | 保留为 developer-only |
| `DomainIntelApp/windows_launcher.ps1` | 快捷方式创建与测试仍引用 | 当前 WSL 开发兼容路径 | 原生 Windows 安装器替代普通用户路径，不替代 WSL 开发 | 保留为 developer-only |

保留的启动器明确不进入发行资源。release manifest 拒绝 `DomainIntelData`、虚拟环境、keys/私钥格式、
旧原生 `dist`、测试输出、依赖目录和缓存；唯一允许的 `dist` 子树是 Web 生产构建 `DomainIntelWeb/dist`。

本次审计未读取、迁移或删除任何用户数据目录。
