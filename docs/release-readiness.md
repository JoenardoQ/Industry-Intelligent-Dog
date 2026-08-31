# IntDog 4.0 Production Release Readiness Contract

## Release Objective

The final release target now spans Windows, macOS, and Linux. The current Windows 11 + WSL `Ubuntu-D` path remains useful for regression evidence, but distributable artifacts must be built natively for all three platforms; WSL or source-based startup is not a cross-platform application package.

This work creates three release-tracking Issues and permits unsigned `4.0.0-test.1` GitHub Pre-releases after native gates pass. Stable Releases remain subject to signing gates. Separate authorization for Git commit and push has not yet been given. This work does not call paid models, send email, perform live network collection, permanently delete production data, or promise commercial-database coverage.

## Supported Boundary

- Target path: platform-native desktop shell → same-platform backend sidecar → random localhost port plus session credential → embedded Chromium workbench. The Windows WSL shortcut becomes a development compatibility path, not the release package.
- Data: production data receives read-only checks; writes, deletion, recovery, jobs, and fault injection use an isolated temporary data root.
- Network: the application listens only on `127.0.0.1`; session token, Host, and Origin checks must hold at the boundary.
- Compatibility: Windows x64, macOS arm64/x64, and Linux x64 each receive an installer built and smoke-tested on a native runner. The local Windows/WSL compatibility path and a Linux x64 AppImage now have runtime evidence; native Windows and macOS packages still require CI evidence.

## Approved Packaging Architecture

The approved route is an Electron desktop shell plus one PyInstaller Python/FastAPI/CLI sidecar and `electron-builder`. Electron supplies consistent Chromium rendering, windows, and lifecycle behavior; one sidecar handles both the API and research commands so Python is not bundled twice. Native CI runners produce a Windows x64 `.exe`, a macOS Apple Silicon arm64 `.dmg`, and a Linux x64 `.AppImage`. Each installer carries only its own platform runtime and never embeds binaries for the other platforms.

Each platform has one GitHub Issue, one independent build job, and one platform Release. Any change to the shared Electron main process, Python sidecar interface, Schema, or overall architecture invalidates all three platform jobs and requires all three to rebuild and pass. The project must not maintain three divergent business implementations. Electron has a fixed Chromium size cost even with platform separation; separate distribution avoids cross-platform binary bundling but does not remove Chromium.

Stable Windows and macOS Releases require signing, and macOS also requires notarization. Without credentials, CI may create explicitly test-only artifacts or Pre-releases but must not create a stable Release.

Unsigned test releases do not require those credentials. They must use a prerelease version such as `4.0.0-test.1`, be marked as GitHub Pre-releases, and warn that Windows SmartScreen or macOS Gatekeeper may require manual approval. The three test-release entry points do not inherit repository signing Secrets, preventing a test build from being mistaken for a formally signed artifact.

Platform delivery is tracked by [Windows Issue #1](https://github.com/JoenardoQ/Industry-Intelligent-Dog/issues/1), [macOS Issue #2](https://github.com/JoenardoQ/Industry-Intelligent-Dog/issues/2), and [Linux Issue #3](https://github.com/JoenardoQ/Industry-Intelligent-Dog/issues/3). `.github/workflows/platform-gates.yml` triggers all platform gates together, while the three Pre-release entry points remain separate. Initial test tags are `v4.0.0-test.1-windows`, `v4.0.0-test.1-macos`, and `v4.0.0-test.1-linux`.

## Current Native Evidence

- Linux x64 sidecar: 17 MB; the same frozen executable passed `cli industries`, FastAPI health, session enforcement, and graceful shutdown.
- Linux x64 AppImage: 142,063,476 bytes (about 135.5 MiB), SHA-256 `863844d3f8c1a26c598199c4113796587b87f9fc7bca8c1361a39d7ed0e777d2`; under WSLg and isolated data/config roots, it completed two consecutive UI/backend start, ready, graceful close, and reopen cycles.
- Each installer carries only its native sidecar. Electron/Chromium is the dominant size component; the Python sidecar is not the main contributor.
- The current conclusion remains `NOT_READY`: the repaired shared gate still needs native macOS arm64 build and install-lifecycle evidence. Test packages are intentionally unsigned; signing and notarization remain formal-release requirements.

## Risk Coverage Matrix

| ID | Risk or requirement | States and interactions | Failure modes | Test level and oracle | Priority |
| --- | --- | --- | --- | --- | --- |
| R1 | First and repeat launch | absent runtime, ready runtime, reopen after close | spaces in paths, UNC, empty ExitCode, stale port | Real Windows shortcut; window, health endpoint, and logs succeed | P0 |
| R2 | Single instance and shutdown | starting, running, normal close, abnormal exit | duplicate service, orphan process, port retained after close | Process/port/shutdown state machine | P0 |
| R3 | Session boundary | valid, missing, wrong token; valid/invalid Host and Origin | unauthorized read or shutdown | API decision table with expected 2xx/4xx | P0 |
| R4 | Seven primary pages | empty, representative, large lists, lazy loading | blank page, route failure, asset 404, dense/overflow layout | Browser AX/DOM, network logs, screenshots | P0 |
| R5 | Industry lifecycle | create, conflict, rename, archive, restore | overwrite, invalid folder, partial write | Isolated API+browser with state and audit readback | P0 |
| R6 | Daily intelligence | search, sort, pagination, selection, delete, restore | cross-page deletion, duplication, empty state, bad attribution | Synthetic end-to-end data with SQLite/JSON oracle | P0 |
| R7 | Source governance | active/manual/reserve, manual source, duplicate URL | reserve collection, catalog truncation, publisher crowding | Contract tests and UI status filtering | P0 |
| R8 | Job lifecycle | queued/running/completed/partial/failed/cancelled/interrupted | stall, bad retry, log leakage, cancellation never converges | Fault injection, durable state, and process-tree oracle | P0 |
| R9 | Reports and Markdown | absent/valid report, invalid path, chart sidecar | path escape, blank reader, render crash | API and browser content oracle | P1 |
| R10 | Time and scheduling | daily/weekly/monthly/quarterly, restart catch-up, timezone edges | duplicate enqueue, bad checkpoint, email delivery | Deterministic clock/state tests | P0 |
| R11 | Migration and recovery | empty/old database, dirty views, repeated run | non-idempotent migration, data loss, stale locks | Temporary copy, integrity, and idempotency checks | P0 |
| R12 | Performance and capacity | 6,800+ documents, 50-row pages, 87 sources | slow first view, unbounded response, memory pressure | Benchmarks and response bounds | P1 |
| R13 | Accessibility and display | keyboard/focus, scaling, Chinese, narrow/wide viewport | inoperable controls, clipping, low contrast | axe/AX, viewport, and visual inspection | P1 |
| R14 | Release hygiene | build artifacts, dependencies, logs, caches, secrets | missing files, stale absolute paths, secret/test debris | Inventory, search, builds, and diff checks | P0 |

## Acceptance Criteria

1. P0 automation, type checking, production build, Python compilation, SQLite integrity, and OpenAPI contract pass.
2. Native Windows, macOS, and Linux artifacts each complete install → launch → home and synthetic industry data load → close → port/sidecar release → reopen; the Windows WSL shortcut remains a separate compatibility regression.
3. An isolated-data browser journey covers all seven pages and the critical recoverable industry and daily-intelligence mutations, with no unhandled frontend exception, primary-resource 4xx/5xx, or serious accessibility violation.
4. Relevant gates rerun after every P0 fix; unavailable hosts and external dependencies remain explicit limitations.
5. `READY` requires all three platforms to pass P0 gates. Missing native artifact evidence for any platform requires `NOT_READY`.

## Evidence and Artifacts

Automated commands, user-journey results, screenshots, performance measurements, defects, and fixes go under `docs/release-evidence/`. Tests must not copy the production database, session tokens, personal files outside the user path, or live network content into the repository.
