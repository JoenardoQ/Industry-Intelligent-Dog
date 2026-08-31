# 子项目 3：后台任务与恢复实施计划

> **执行要求：** 使用 `superpowers:subagent-driven-development`；平台适配器可并行实现，但共享任务状态机必须先完成。

**目标：** 关闭窗口后继续运行周期任务，并在重复唤醒、崩溃、重启和时区变化下安全恢复。
**架构：** Electron 无窗口模式解密凭据并启动冻结 sidecar 的一次性 Worker；SQLite runs/schedules 为状态权威，JSON JobStore 只保存有界日志兼容产物。
**技术栈：** Python、SQLite、Electron/Node、Windows Task Scheduler、LaunchAgent、systemd user timer。
**规格：** `docs/superpowers/specs/2026-09-01-subproject-3-background-worker.zh-CN.md`

## 全局约束

- 不通过 shell 拼接平台命令；所有路径和 argv 显式传递，凭据只走一次性匿名管道，不进入 argv/env/文件。
- `partial`、`interrupted` 或 `paused` 不能推进最后成功边界。
- Worker 和 Desktop 同时运行只能有一个租约持有者。
- 邮件禁用；付费 Provider 后台权限必须持久、可撤销。

---

### 任务 1：统一运行账本、状态与检查点

**文件：**
- Create: `DomainIntelSearch/intdog_core/task_repository.py`
- Modify: `DomainIntelSearch/intdog_core/repository.py`
- Modify: `DomainIntelApp/runtime/jobs.py`
- Test: `DomainIntelApp/tests/test_runtime_jobs.py`
- Test: `DomainIntelSearch/tests/test_task_runtime.py`

**接口：**

```python
class TaskLedger(Protocol):
    def create_task(self, *, folder: str, operation: str, input: dict,
                    origin: str, provider: str) -> dict: ...
    def heartbeat(self, run_id: str, *, stage: str, progress: int,
                  checkpoint: dict) -> None: ...
    def transition(self, run_id: str, *, expected: set[str],
                   target: str, error: dict | None = None) -> dict: ...
    def claim_expired(self, run_id: str, owner: str, ttl_seconds: int) -> bool: ...
```

- [ ] **Step 1: 写 Schema 16 与状态机 RED 测试**

覆盖全部九种权威状态、非法转换、心跳、父任务、Provider/model/time-window、后台授权作用域与撤销、过期租约接管、重复完成和部分写入回滚。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_task_runtime.py DomainIntelApp/tests/test_runtime_jobs.py -q`

- [ ] **Step 3: 实现 TaskRepositoryMixin 和 JobManager ledger 适配**

`JobManager` 接受可选 `ledger: TaskLedger`；日志继续受 1 MiB 上限和流式清密约束。

- [ ] **Step 4: 运行 GREEN 与旧任务回归**

Run: `python -m pytest DomainIntelSearch/tests/test_task_runtime.py DomainIntelApp/tests/test_runtime_jobs.py DomainIntelWeb/tests/test_api.py -q`

### 任务 2：实现一次性后台 Worker 与正确周期边界

**文件：**
- Create: `DomainIntelSearch/src/background_worker.py`
- Modify: `DomainIntelWeb/api/automation.py`
- Modify: `DomainIntelSearch/src/scheduler.py`
- Modify: `DomainIntelSearch/src/history_backfill.py`
- Modify: `DomainIntelApp/packaging/entry.py`
- Test: `DomainIntelSearch/tests/test_background_worker.py`
- Test: `DomainIntelSearch/tests/test_time_windows.py`

**接口：**

```python
class BackgroundWorker:
    def run_once(self, now: datetime) -> WorkerSummary: ...

@dataclass(frozen=True)
class WorkerSummary:
    claimed: int
    completed: int
    paused: int
    failed: int
    next_run_at: str | None
```

- [ ] **Step 1: 写 RED 时间与并发测试**

覆盖 04:00 日界、无上次成功、周期不足、DST 重复/跳过、本地时区改变、App/Worker 双 tick、partial 不推进边界、退避耗尽、两年约 3,000/五年约 8,000 的密度目标、90% 月桶覆盖、事件峰值 overflow、桶过度集中、来源枯竭和低质/重复条目不计数。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelSearch/tests/test_background_worker.py DomainIntelSearch/tests/test_time_windows.py -q`

- [ ] **Step 3: 实现 `worker --once` 和共享 claim 逻辑**

API scheduler 与 Worker 调用同一个纯函数；Worker 等待自己领取的任务进入终态再退出。长周期 planner 按 3–5 条/日建立可恢复桶预算，先保证时间覆盖和发布者多样性，再填充高价值事件；达不到质量门槛时输出 partial/gap，不重复采样凑数。

- [ ] **Step 4: 运行 GREEN**

Run: `python -m pytest DomainIntelSearch/tests/test_background_worker.py DomainIntelWeb/tests/test_round2_workbench.py -q`

### 任务 3：实现三平台后台服务适配器

**文件：**
- Create: `DomainIntelDesktop/src/background-service.cjs`
- Create: `DomainIntelDesktop/test/background-service.test.cjs`
- Modify: `DomainIntelDesktop/src/main.cjs`
- Modify: `DomainIntelDesktop/src/preload.cjs`
- Modify: `DomainIntelDesktop/src/runtime.cjs`

**接口：**

```javascript
function serviceDefinition({ platform, executable, userData, intervalMinutes })
async function installBackgroundService(options)
async function removeBackgroundService(options)
async function backgroundServiceStatus(options)
```

- [ ] **Step 1: 写 RED 平台合同测试**

Windows 输出 schtasks argv；macOS 输出用户级 plist；Linux 输出 `.service/.timer`。测试空格路径、Unicode、禁用、重复安装和卸载保留数据。

- [ ] **Step 2: 运行 RED**

Run: `npm test --prefix DomainIntelDesktop`

- [ ] **Step 3: 实现无 shell 适配器与 `--background-worker` 分支**

后台分支不开 BrowserWindow，读取 safeStorage 后启动 `intdog-runtime worker --once`；凭据使用 OS 匿名管道/child stdin 的长度前缀消息传递，发送后关闭并尽力覆盖 Buffer。状态文件只写凭据引用状态和错误分类，不写密钥。

- [ ] **Step 4: 运行 GREEN**

Run: `npm test --prefix DomainIntelDesktop`

测试必须用唯一 canary 密钥断言 child argv/env、进程状态、日志、任务账本、状态文件和临时目录均无匹配，管道关闭后不可重放；覆盖安全存储锁定、子进程启动失败、写入中断、取消、撤销授权和崩溃。

### 任务 4：后台状态 API、任务中心与系统页

**文件：**
- Modify: `DomainIntelWeb/api/schemas.py`
- Modify: `DomainIntelWeb/api/routers/system.py`
- Modify: `DomainIntelWeb/api/routers/operations.py`
- Modify: `DomainIntelWeb/src/features/JobsPage.tsx`
- Modify: `DomainIntelWeb/src/features/SystemPage.tsx`
- Modify: `DomainIntelWeb/src/test/workflows.test.tsx`

- [ ] **Step 1: 写 RED API/DOM 测试**

断言 service installed/last wake/next run/permission/error 可见；任务显示 origin、时间窗、Provider、模型、心跳、错误分类和恢复动作。

- [ ] **Step 2: 运行 RED**

Run: `python -m pytest DomainIntelWeb/tests/test_api.py DomainIntelWeb/tests/test_round2_workbench.py -q && npm test --prefix DomainIntelWeb`

- [ ] **Step 3: 实现强类型状态与 IPC 桥接**

前端不得直接执行平台命令；只通过 preload 的最小 IPC 调用安装/禁用/状态。

- [ ] **Step 4: 生成契约并运行子项目门禁**

Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb && npm test --prefix DomainIntelDesktop`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`
