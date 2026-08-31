# Agent 与首次使用周期 · 第一轮收尾

[English](2026-09-01-agent-onboarding-round-1-closeout.md)

## 决策

用户选择并已实施提案 1–4：三平台产品门禁、完整 Agent Bridge、唯一能力 Manifest、双语当前架构/状态与版本化发行证据。本轮未提交、push、触发 CI 或发布，也未改写生产行业数据。

## 已交付

- `capability_manifest.py` 统一 9 类 Agent 与 4 类 API Provider；Provider 工厂显式 fail closed，API、调度和 UI 从 Manifest 派生。
- 首次设置可复制 Codex、Claude、Work Buddy、通用 MCP JSON/TOML 配置，并可保存/删除只含公开 argv 的自定义 CLI Profile。
- 研究助手可导出已知任务 JSON，并把任意 Agent 结果导入 `draft_review_required` 待复核区。
- 导入限制行业与任务、Schema、500 KiB、HTTP(S) 引用和稳定 ID；使用原子写、内容哈希幂等和审计，不写事实库。
- Electron 使用操作系统安全存储；Provider 凭据严格限定所属 Provider，Key 不进入 DOM/API/日志/产物。
- 原生 workflow 现在每个平台执行完整 Python、DOM、生产构建、OpenAPI 漂移、仓库检查、Desktop、sidecar 和 renderer 首次/重开工作流。
- 旧 v2 设计和旧状态保留在 `docs/archive/`；根目录改为完整对齐的中英文当前架构与状态。

## C1–C10 对账

| ID | 结果 | 证据 |
| --- | --- | --- |
| C1 | 通过 | Manifest/工厂集合测试；UI 无手写 Provider option/allow-list |
| C2 | 通过 | 手动与自动未就绪 Provider 均拒绝且不入队 |
| C3 | 通过 | 四类 MCP 配置结构测试与 Setup 复制界面 |
| C4 | 通过 | 未知任务、无引用、坏 Profile/路径、超限全部拒绝 |
| C5 | 通过 | 原子写、内容哈希重复导入、单次审计、事实统计不变 |
| C6 | 通过 | 命令只允许 PATH basename；argv 拒绝路径与 shell 元字符 |
| C7 | 已建立原生门禁 | Electron renderer 实际填写首次向导、观察任务中心并重开；须由三平台 runner 执行 |
| C8 | 本地通过/原生待跑 | Desktop 加密文件/清除测试通过；原生 E2E 在安全存储可用时检查明文泄露 |
| C9 | 通过 | 双语当前架构/状态；旧 release 证据绑定 `7709e88`，当前明确 NOT_READY |
| C10 | 通过 | 既有 Provider、任务包、只读 MCP 与全套回归通过 |

## 验证

- Python：168 passed。
- Web DOM：7 passed；TypeScript 与 Vite production build 通过。
- Desktop：2 passed；Electron 入口语法检查通过。
- OpenAPI 导出/TypeScript 生成幂等；108 个 Python 文件通过语法与重复定义检查；compileall、`git diff --check` 通过。
- 当前源码重新构建 Linux x64 冻结 sidecar；在隔离临时数据根完成 CLI、受保护健康检查、Setup、创建行业、无模型 bootstrap、任务完成、概览读取和正常关闭。

## 剩余发行门槛

当前工作树没有 Windows、macOS、Linux 三平台同 revision runner 结果，也没有三平台当前安装包 renderer 生命周期结果。本地 WSL 不等于三个原生宿主。因此结论是 `NOT_READY_PENDING_NATIVE_GATES`；旧 `4.0.0-test.1` 不能作为当前包。真实账户/API/生产联网采集也没有被离线证据替代。

第一轮在本地范围内关闭。按用户顺序，下一步才启用 Superpowers 并开始最终轮的新鲜审查。
