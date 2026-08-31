# Subproject 3: Background Tasks and Recovery Implementation Plan

> **Execution requirement:** Use `superpowers:subagent-driven-development`; platform adapters may be implemented in parallel, but the shared task state machine must be completed first.

**Objective:** Continue recurring tasks after the window closes and recover safely across duplicate wakeups, crashes, restarts, and time-zone changes.
**Architecture:** Electron’s windowless mode decrypts credentials and starts a one-shot Worker from the frozen sidecar; SQLite runs/schedules are authoritative for state, while JSON JobStore stores only bounded log-compatible artifacts.
**Tech stack:** Python, SQLite, Electron/Node, Windows Task Scheduler, LaunchAgent, systemd user timer.
**Specification:** `docs/superpowers/specs/2026-09-01-subproject-3-background-worker.md`

## Global Constraints

- Do not concatenate platform commands through a shell; pass all paths and argv explicitly, and send credentials only through a one-time anonymous pipe, never through argv/env/files.
- `partial`, `interrupted`, or `paused` cannot advance the last-successful boundary.
- When the Worker and Desktop run simultaneously, only one may hold the lease.
- Email is disabled; background permission for paid Providers must be persistent and revocable.

---

### Task 1: Unify the Run Ledger, State, and Checkpoints

**Files:**
- Create: `DomainIntelSearch/intdog_core/task_repository.py`
- Modify: `DomainIntelSearch/intdog_core/repository.py`
- Modify: `DomainIntelApp/runtime/jobs.py`
- Test: `DomainIntelApp/tests/test_runtime_jobs.py`
- Test: `DomainIntelSearch/tests/test_task_runtime.py`

**Interfaces:**

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

- [ ] **Step 1: Write Schema 16 and state-machine RED tests**

Cover all nine authoritative states, illegal transitions, heartbeats, parent tasks, Provider/model/time-window, background-authorization scope and revocation, takeover of expired leases, repeated completion, and rollback of partial writes.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_task_runtime.py DomainIntelApp/tests/test_runtime_jobs.py -q`

- [ ] **Step 3: Implement the TaskRepositoryMixin and JobManager ledger adapter**

`JobManager` accepts an optional `ledger: TaskLedger`; logs remain subject to the 1 MiB limit and streaming credential-redaction constraint.

- [ ] **Step 4: Run GREEN and legacy-task regression**

Run: `python -m pytest DomainIntelSearch/tests/test_task_runtime.py DomainIntelApp/tests/test_runtime_jobs.py DomainIntelWeb/tests/test_api.py -q`

### Task 2: Implement the One-Shot Background Worker and Correct Period Boundaries

**Files:**
- Create: `DomainIntelSearch/src/background_worker.py`
- Modify: `DomainIntelWeb/api/automation.py`
- Modify: `DomainIntelSearch/src/scheduler.py`
- Modify: `DomainIntelSearch/src/history_backfill.py`
- Modify: `DomainIntelApp/packaging/entry.py`
- Test: `DomainIntelSearch/tests/test_background_worker.py`
- Test: `DomainIntelSearch/tests/test_time_windows.py`

**Interfaces:**

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

- [ ] **Step 1: Write RED time and concurrency tests**

Cover the 04:00 daily boundary, no last success, insufficient period history, repeated/skipped DST times, local time-zone changes, App/Worker dual ticks, partial runs not advancing the boundary, exhausted backoff, density targets of about 3,000 over two years/about 8,000 over five years, 90% month-bucket coverage, event-peak overflow, over-concentrated buckets, source exhaustion, and low-quality/duplicate entries not being counted.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_background_worker.py DomainIntelSearch/tests/test_time_windows.py -q`

- [ ] **Step 3: Implement `worker --once` and shared claim logic**

The API scheduler and Worker call the same pure function; the Worker exits only after the tasks it claimed have reached terminal states. The long-period planner creates recoverable bucket budgets at 3–5 items/day, ensures time coverage and publisher diversity first, then fills high-value events; when the quality threshold is not met, it outputs partial/gap and does not repeat sampling to reach the count.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest DomainIntelSearch/tests/test_background_worker.py DomainIntelWeb/tests/test_round2_workbench.py -q`

### Task 3: Implement Three-Platform Background-Service Adapters

**Files:**
- Create: `DomainIntelDesktop/src/background-service.cjs`
- Create: `DomainIntelDesktop/test/background-service.test.cjs`
- Modify: `DomainIntelDesktop/src/main.cjs`
- Modify: `DomainIntelDesktop/src/preload.cjs`
- Modify: `DomainIntelDesktop/src/runtime.cjs`

**Interfaces:**

```javascript
function serviceDefinition({ platform, executable, userData, intervalMinutes })
async function installBackgroundService(options)
async function removeBackgroundService(options)
async function backgroundServiceStatus(options)
```

- [ ] **Step 1: Write RED platform contract tests**

Windows outputs schtasks argv; macOS outputs a user-level plist; Linux outputs `.service/.timer`. Test paths with spaces, Unicode, disabled state, repeated installation, and uninstall that preserves data.

- [ ] **Step 2: Run RED**

Run: `npm test --prefix DomainIntelDesktop`

- [ ] **Step 3: Implement shell-free adapters and the `--background-worker` branch**

The background branch does not open a BrowserWindow, reads safeStorage, and starts `intdog-runtime worker --once`; credentials use an OS anonymous pipe/child stdin with length-prefixed messages, then close the pipe and overwrite the Buffer on a best-effort basis. The state file writes only credential-reference status and error categories, never keys.

- [ ] **Step 4: Run GREEN**

Run: `npm test --prefix DomainIntelDesktop`

Tests must use a unique canary key to assert zero matches in child argv/env, process state, logs, task ledger, state file, and temporary directory, and that the pipe cannot be replayed after closing; cover secure-storage locking, child-process launch failure, interrupted writes, cancellation, authorization revocation, and crashes.

### Task 4: Background-State API, Task Center, and System Page

**Files:**
- Modify: `DomainIntelWeb/api/schemas.py`
- Modify: `DomainIntelWeb/api/routers/system.py`
- Modify: `DomainIntelWeb/api/routers/operations.py`
- Modify: `DomainIntelWeb/src/features/JobsPage.tsx`
- Modify: `DomainIntelWeb/src/features/SystemPage.tsx`
- Modify: `DomainIntelWeb/src/test/workflows.test.tsx`

- [ ] **Step 1: Write RED API/DOM tests**

Assert that service installed/last wake/next run/permission/error are visible; tasks display origin, time window, Provider, model, heartbeat, error category, and recovery action.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelWeb/tests/test_api.py DomainIntelWeb/tests/test_round2_workbench.py -q && npm test --prefix DomainIntelWeb`

- [ ] **Step 3: Implement strongly typed state and IPC bridge**

The frontend must not execute platform commands directly; it only invokes installation/disable/status through the minimal preload IPC.

- [ ] **Step 4: Generate the contract and run the subproject gate**

Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb && npm test --prefix DomainIntelDesktop`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`
