# SP5 A（任务 1–2）冻结报告

日期：2026-09-02

## 已实现

- 冻结入口明确支持 `serve`、`cli`、`worker --once`。
- 发行资源只从 Web 构建、Search 配置、evaluation、skills 与三平台服务模板组装；临时目录生成带 SHA-256 的确定性清单后原子替换目标。
- electron-builder 与资源组装器共同排除 `DomainIntelData`、venv、keys 和常见私钥格式。
- sidecar smoke 校验资源摘要，并真实执行 CLI、一次 Worker 和本地 API 启停。
- 原生生命周期 smoke 使用 13 步原子状态记录、逐步超时诊断和失败即停语义。
- `NOM-01` 明确拒绝 taskpack/seed；只接受公开免凭据模式下具有真实 URL、发布者身份/可达性、采集时间、内容 SHA-256、实体类型、有序节点、证据边和零 Provider 调用的记录。
- 后台服务生命周期必须显式传入原生变更授权；安装、Worker 执行与移除均使用隔离应用数据，移除放在清理路径。
- reference Agent/API 只检查确定性连接合同；真实已登录 Agent 深度 smoke 未获本轮授权，记录为外部缺口，不以 mock 代替。

## 本地证据

- `DomainIntelApp/tests/test_packaged_commands.py`：7 passed。
- Desktop runtime focused：1 passed。
- Python compileall：通过。
- 资源组装：5 个资源组、40 个文件。
- Linux frozen sidecar：构建成功；CLI/Worker/API smoke 退出码 0。
- scoped `git diff --check`：通过。

## 未关闭的外部门槛

- 本轮禁止联网，因此未运行真实 `NOM-01` 公共来源采集。
- 未提供 Windows NSIS、macOS DMG 或 Linux AppImage 原生安装制品，因此未执行真实安装/挂载/卸载与数据保留 smoke。
- 未授权修改本机服务调度器，因此未实际安装后台服务。
- 未明确授权使用已登录 Agent，因此未执行真实 Agent 深度 smoke。

上述项目保持 external gap；不得据此声明原生 Beta 生命周期已通过。
