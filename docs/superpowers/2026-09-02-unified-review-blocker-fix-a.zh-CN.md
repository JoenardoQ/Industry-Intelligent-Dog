# 统一审查阻断修复 A——冻结报告

日期：2026-09-02
范围：仅安全、数据完整性与后台一致性

## 已闭合阻断项

- 任务心跳、checkpoint、输出发布、请求派发和终态迁移均要求未过期的
  owner/lease CAS。启动恢复会中断租约过期的 `running`/`cancelling` 任务；
  旧 Worker 在租约接管后不能继续发布。
- Schema 迁移在首次读取版本前获取 `BEGIN IMMEDIATE`，DDL 与迁移记录处于
  同一事务，不再受 `executescript` 隐式提交影响。
- 情报与来源活动子进程只接收白名单环境。公开/无模型任务收到空凭据帧；
  付费凭据帧按任务声明的 provider 与 operation 限定。
- Electron 高权限 IPC 必须来自当前主窗口、顶层 frame 和随机后端 origin。
  安装后台服务还要求有界参数和用户确认后签发的短期一次性 nonce。
- 可移植行业包增加 SHA-256 完整性、64 MiB 总上限、数组与单记录上限、
  写入前全量校验、隔离 staging，以及主库单事务合并。合并失败不会留下目标
  目录、行业记录或共享表污染；导入的信任状态统一降级为 candidate/人工审核，
  不信任导入的 evidence_count。
- 实体规范关系必须有当前行业 Document，或当前行业已接受的 Claim/Assertion。
  无支持证据的关系进入审核队列；审核通过后在同一事务中物化规范关系。
- Linux 后台服务在可用时使用稳定 `APPIMAGE` 路径，并要求绝对常规文件，
  避免持久服务引用临时挂载点。

## 聚焦验证

- `DomainIntelSearch/tests/test_task_runtime.py`：11 passed。
- `DomainIntelApp/tests/test_runtime_jobs.py`：10 passed。
- 后台子进程环境白名单：1 passed。
- `DomainIntelDesktop/test/ipc-security.test.cjs`：3 passed。
- `DomainIntelWeb/tests/test_industry_workflow.py`：4 passed。
- Web 工作流 DOM 短批：3 个聚焦文件共 33 passed。
- Python 静态编译、Electron 语法检查、`git diff --check` 和 Web 生产构建通过。
- OpenAPI 与生成的 TypeScript 契约已同步。

按已批准执行策略，本块未运行全仓测试；未联网、未操作用户数据、未提交、
未发布。
