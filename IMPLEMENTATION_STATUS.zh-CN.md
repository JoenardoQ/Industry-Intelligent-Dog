# IntDog 当前实现状态

[English](IMPLEMENTATION_STATUS.md) · [当前架构](DESIGN.zh-CN.md) · [安装指南](README.zh-CN.md)

- 更新日期：2026-09-01
- 源码版本：完成 Agent/首次使用第一轮实施后的 4.0 工作树
- 发行结论：`NOT_READY_PENDING_NATIVE_GATES`
- 发布状态：本轮没有获得 commit、push、CI 触发或发布授权

## 已实现产品路径

- Electron 桌面壳、冻结 Python sidecar、受会话保护的 localhost FastAPI 和 React 工作台。
- 首次启动运行/数据诊断、连接选择、创建首个行业、首个 bootstrap 任务、任务中心和重开持久化。
- 无模型任务包模式；Codex CLI 与 Claude Code 直接适配；OpenAI、DeepSeek、Qwen、Azure OpenAI 安全 API 配置。
- 唯一能力 Manifest 统一国内外 Agent/Provider 的身份、地区、连接、执行、认证、默认配置、Web 能力和可调度性。
- 可复制的 Codex、Claude、Work Buddy 和通用 MCP 配置；MCP 继续默认只读。
- Agent Bridge 支持任务导出与受校验的原子结果导入。导入内容固定为 `draft_review_required`，保留审计、重复导入幂等、限制已知行业/任务、强制引用，并与事实库隔离。
- 可信度感知每日情报、来源治理、规范实体/关系、Story 交叉印证、开放世界覆盖计划、长周期门槛、定期/研究产物、持久任务、调度、恢复和审计界面。
- 邮件发送保持禁用。

## 当前验证

本地验证已按 `docs/iterations/2026-08-31-agent-onboarding-round-1-contract.zh-CN.md` 的风险模型关闭：168 项 Python、7 项 Web DOM、2 项 Desktop、TypeScript/Vite 生产构建、幂等生成 OpenAPI、compileall、108 文件仓库检查和 `git diff --check` 全部通过。当前源码新构建的 Linux 冻结 sidecar 在隔离数据根完成首行业/bootstrap/概览/关闭工作流。

可复用原生工作流现在强制执行完整 Python 套件、Web DOM/构建、OpenAPI 漂移、仓库检查、Desktop 测试、冻结 sidecar 烟雾、renderer 实际操作首次流程、重开持久化，以及安全存储可用时的凭据生命周期。

## 发行阻断项

- 当前工作树尚未通过相同 revision 的 Windows、macOS、Linux 原生 runner。
- 当前源码尚无三个宿主全部通过的新安装包 GUI 生命周期证据。
- Windows 与 macOS 稳定发布还需要签名；macOS 还需要公证。
- 真实付费 API、第三方 Agent 账户和生产规模联网采集属于集成证据，离线测试不能代替。

之前发布的 `4.0.0-test.1` 来自提交 `7709e88`，不包含也不能证明当前首次引导与 Agent Bridge 改动，不能作为当前版本分发。

## 历史记录

旧详细状态保存在 `docs/archive/IMPLEMENTATION_STATUS-2026-08-31-legacy.zh-CN.md`，仅作为历史证据，不代表当前发行结论。
