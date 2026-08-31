# Subproject 3: Background Tasks and Recovery Specification

Status: Approved, awaiting implementation verification
Dependency: Strongly typed tasks and data boundaries from Subprojects 1–2

## Objective

Keep daily and recurring tasks running after the IntDog window is closed, while maintaining single-instance execution, recoverability, and auditability across system restarts, duplicate wakeups, task crashes, and time-zone changes.

## Runtime Model

Installed IntDog can enter windowless mode with `--background-worker`. Electron is responsible for accessing operating-system secure storage, then sends a short-lived credential bundle through a one-time anonymous pipe readable only by the parent and child processes to the same frozen sidecar’s `worker --once` mode; keys must not appear in argv, environment variables, temporary files, the task ledger, state files, or logs. The Worker reads the bundle once, closes the pipe, handles only due tasks, waits for the tasks it claimed in this run to reach terminal states, and then exits.

System wake-up methods:

- Windows: Task Scheduler;
- macOS: user-level LaunchAgent;
- Linux: systemd user service/timer.

Registration, updates, disabling, and status checks are performed by platform adapters without concatenating shell strings.

## Scheduling and Leases

- Continue using `automation_schedules`, adding Worker installation status and the last wake-up record.
- Claiming a schedule must compare the period key, lease, and retry time in a SQLite transaction.
- The Desktop API scheduler and background Worker may wake simultaneously, but only one may obtain the lease.
- The daily window is from 04:00 on the previous day to the current time; periods start at the last successful boundary, looking back over a complete period when history is insufficient.
- Time zones use IANA names; skipped/repeated daylight-saving times must generate unique period keys.

Long-period collection uses adaptive time buckets and qualified-document density rather than concentrating the total near the present. The default target is 3–5 qualified documents per calendar day: 2,400–3,600 over two years (nominally about 3,000) and 7,000–9,000 over five years (nominally about 8,000); week, month, quarter, and half-year periods scale by the same density and available sources. At least 90% of applicable month buckets must have coverage, and no bucket may exceed three times the median bucket without explanation; genuine major-event peaks are retained as justified overflow. When sources are insufficient, duplicated, or below quality, report a gap and do not copy or fabricate entries.

## Failure and Recovery

- The authoritative state set is `queued / running / cancelling / paused / completed / partial / failed / cancelled / interrupted`; normal completion, cancellation, pausing, and crash recovery follow the parent specification.
- Heartbeats, checkpoints, parent task, Provider, model, time window, and output location are persisted.
- After system shutdown or process termination, the next Worker may safely take over an expired lease.
- Retries follow exponential backoff and an upper limit; configuration/credential errors enter pause and do not consume unlimited retries.
- Paid Providers or first-time credential use require prior user permission for background use; otherwise the task remains paused.
- Background authorization is minimized by Provider, industry, and task type, disabled by default, and revocable. After revocation, new claims are forbidden, active tasks whose requests have not been sent are cancelled, and unused credential handles are cleared; requests already sent to an external Provider cannot be withdrawn, and the UI must clearly display this limitation.

The threat model covers ordinary same-user processes reading command lines/environment, logs, task listings, state files, and temporary directories, as well as residue after crashes/cancellation. It does not claim to resist attackers with administrator/root, debugger, kernel, or physical-memory access. Garbage-collected strings in Electron/Python cannot be reliably zeroed, so implementations should prefer short-lived Buffer/bytearray values and overwrite them on a best-effort basis after use; this limitation must be recorded, and absolute memory clearing must not be claimed.

## UI

The system page displays whether the background service is installed, the latest wake-up, next run, permissions, and failure reasons. The task center distinguishes tasks initiated by the App, manually, by system scheduling, or by the background Worker, and provides cancel, retry, and recovery actions.

## Acceptance

- Due tasks still complete after the window is closed; reopening the App shows the same tasks and artifacts.
- Duplicate system wakeups and simultaneous App execution do not generate duplicate tasks.
- System restart, expired heartbeat, checkpoint recovery, cancellation, and timeout all have state-machine tests.
- Two-year and five-year tasks meet time-bucket coverage, deduplication, publisher-diversity, and evidence-quality gates; when insufficient, they remain partial/gap and must not falsely report target counts.
- Windows/macOS/Linux platform adapters have command/file contract tests, and native runners verify actual registration and uninstall.
- Logs and the environment do not expose credentials; email remains disabled at all times.
- Platform contract tests and native smoke tests must prove that keys are absent from child-process argv/env, logs, the ledger, state, or temporary files, and cannot be reread after the anonymous pipe closes; when secure storage is unavailable, the background session is locked, or authorization is revoked, the task enters an explainable paused state rather than falling back to plaintext transfer.
