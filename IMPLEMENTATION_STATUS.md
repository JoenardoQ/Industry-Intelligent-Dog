# IntDog Implementation Status

[中文](IMPLEMENTATION_STATUS.zh-CN.md) · [Architecture](DESIGN.md) · [Installation](README.md)

- Updated: 2026-09-02
- Source version: 4.0 working tree after SP4 freeze and SP5 A tasks 1–2
- Release conclusion: `NOT_READY_PENDING_NATIVE_GATES`
- Publication state: no commit, push, CI dispatch, or release was authorized in this round

## Implemented product path

- Electron desktop shell, frozen Python sidecar, session-protected localhost FastAPI, and React workbench.
- First-run runtime/data diagnostics, connection selection, first-industry creation, first bootstrap job, task center, and persistent reopen.
- Model-free task-package mode; direct Codex CLI and Claude Code adapters; secure API configuration for OpenAI, DeepSeek, Qwen, and Azure OpenAI.
- One capability manifest for domestic and international agent/provider identity, region, connection, execution, authentication, defaults, Web capability, and scheduling eligibility.
- Copyable Codex, Claude, Work Buddy, and generic MCP configurations. MCP remains read-only.
- Agent Bridge task export and validated, atomic result import. Imported output is `draft_review_required`, audited, idempotent, bounded to a known industry/task, citation-required, and isolated from the fact store.
- Evidence-aware daily intelligence, source governance, canonical entities/relations, Story corroboration, open-world coverage planning, long-history gates, periodic/research products, durable jobs, scheduling, recovery, and audit views.
- Email delivery remains disabled.

## Current verification

SP4 froze the unified user workflows, deterministic artifact quality gate, and
portable offline HTML. SP5 A froze the serve/CLI/Worker sidecar, explicit hashed
resources, and the fail-stop native lifecycle harness. See
[`SP4 freeze`](docs/superpowers/2026-09-02-sp4-freeze-report.md) and
[`SP5 A report`](docs/superpowers/2026-09-02-sp5-a-task1-2-report.md).

Local verification is closed under the risk model in `docs/iterations/2026-08-31-agent-onboarding-round-1-contract.md`: 168 Python tests, seven Web DOM workflows, two Desktop tests, TypeScript/Vite production build, idempotent generated OpenAPI, compileall, a 108-file repository check, and `git diff --check` pass. A newly rebuilt frozen Linux sidecar completed an isolated first-industry/bootstrap/overview/shutdown workflow.

The reusable native workflow now requires the full Python suite, Web DOM/build, generated OpenAPI drift check, repository check, Desktop tests, frozen-sidecar smoke, renderer-operated first run, restart persistence, and secure-storage lifecycle where available.

## Release blockers

- `NOM-01` live public credential-free collection remains an external gap; local
  task packages and seed fixtures do not satisfy it.
- Native background-service install/revoke, uninstall/data retention, and a real
  logged-in Agent deep smoke remain external gaps.

- The current working tree has not passed matching native Windows, macOS, and Linux runners.
- No newly built current installer has completed a packaged GUI lifecycle on all three hosts.
- Stable Windows and macOS publication also requires signing; macOS requires notarization.
- Real paid API accounts, third-party agent accounts, and production-scale live collection are integration evidence, not implied by offline tests.

The previously published `4.0.0-test.1` artifacts were built from commit `7709e88`. They do not contain or prove the current onboarding/Agent Bridge changes and must not be presented as the current build.

## Historical record

The prior detailed status is preserved at `docs/archive/IMPLEMENTATION_STATUS-2026-08-31-legacy.zh-CN.md`. It is evidence history, not the current release conclusion.
