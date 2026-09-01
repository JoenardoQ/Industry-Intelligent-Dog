# Unified Review Blocker Fix A — Freeze Report

Date: 2026-09-02
Scope: security, data integrity, and background consistency only

## Closed blockers

- Task mutations now require an unexpired owner/lease CAS for heartbeats,
  checkpoints, output publication, dispatch, and terminal transitions. Startup
  recovery interrupts expired `running`/`cancelling` tasks, and stale workers
  cannot publish after lease takeover.
- Migrations acquire `BEGIN IMMEDIATE` before the first schema-version read and
  execute DDL inside that transaction without `executescript` implicit commits.
- Intelligence and source-campaign children receive an allowlisted environment.
  Credential frames are empty for public/no-model tasks and scoped to the
  task's explicit provider and operation.
- Privileged Electron IPC requires the current main window, its top frame, and
  the random backend origin. Background installation additionally requires a
  bounded payload and a short-lived, one-use user-confirmation nonce.
- Portable industry bundles have SHA-256 integrity, 64 MiB total, bounded
  arrays and record sizes, full pre-write validation, isolated staging, and a
  single main-database merge transaction. Failed merges leave neither a target
  folder nor industry/shared rows. Imported trust decisions are downgraded to
  candidate/manual review; imported evidence counts are not trusted.
- Canonical entity relations require a current-industry Document or accepted
  current-industry Claim/Assertion. Unsupported relations enter the review
  queue; approval materializes the canonical relation transactionally.
- Linux background services use `APPIMAGE` when present and require an
  absolute path to a regular file, avoiding temporary mount executables.

## Focused verification

- `DomainIntelSearch/tests/test_task_runtime.py`: 11 passed.
- `DomainIntelApp/tests/test_runtime_jobs.py`: 10 passed.
- Background child-environment test: 1 passed.
- `DomainIntelDesktop/test/ipc-security.test.cjs`: 3 passed.
- `DomainIntelWeb/tests/test_industry_workflow.py`: 4 passed.
- Web workflow DOM batch: 33 passed across 3 focused files.
- Python static compilation, Electron syntax checks, `git diff --check`, and
  the production Web build passed.
- OpenAPI and generated TypeScript contracts were regenerated.

Per the approved execution policy, the full repository suite was not run in
this block. No network, user data, commit, or release mutation was performed.
