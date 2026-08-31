# Agent and First-run Cycle · Round 1 Closeout

[中文](2026-09-01-agent-onboarding-round-1-closeout.zh-CN.md)

## Decision

The user selected and this round implemented proposals 1–4: native product gates, a complete Agent Bridge, one capability manifest, and aligned current bilingual architecture/status with revision-scoped release evidence. This round did not commit, push, dispatch CI, publish, or mutate production industry data.

## Delivered

- `capability_manifest.py` owns nine agent families and four API providers. The provider factory fails closed; API, scheduling, and UI derive from the manifest.
- Setup exposes copyable Codex, Claude, Work Buddy, and generic MCP JSON/TOML configurations and manages custom CLI profiles containing public argv only.
- Research Studio exports known task JSON and imports arbitrary-agent results into a `draft_review_required` area.
- Import binds industry/task, schema, 500 KiB, HTTP(S) citations, and stable IDs; atomic content-hashed writes are idempotent and audited without touching facts.
- Electron uses operating-system secure storage. Provider credentials are scoped to their selected provider; keys do not enter DOM, API, logs, or artifacts.
- Every native workflow now runs the complete Python, DOM, production-build, OpenAPI-drift, repository, Desktop, sidecar, and renderer first-run/reopen contracts.
- Legacy v2 design/status remain under `docs/archive/`; aligned complete Chinese and English current architecture/status replace them at the root.

## C1–C10 reconciliation

| ID | Result | Evidence |
| --- | --- | --- |
| C1 | Pass | Manifest/factory set test; no handwritten provider option/allow-list in UI |
| C2 | Pass | Unready manual and automatic providers reject without a queued job |
| C3 | Pass | Four MCP configuration structure tests and Setup copy surface |
| C4 | Pass | Unknown task, uncited result, invalid profile/path, and oversize rejection |
| C5 | Pass | Atomic write, content-hash duplicate, one audit, unchanged fact statistics |
| C6 | Pass | Command is a PATH basename; argv rejects paths and shell metacharacters |
| C7 | Native gate established | Electron renderer fills onboarding, observes Task Center, and reopens; three native runners must execute it |
| C8 | Local pass/native pending | Desktop encrypted-file/clear tests pass; native E2E checks plaintext leakage where secure storage exists |
| C9 | Pass | Current bilingual architecture/status; old evidence bound to `7709e88`; current conclusion is NOT_READY |
| C10 | Pass | Existing providers, task packages, read-only MCP, and the full regression suite pass |

## Verification

- Python: 168 passed.
- Web DOM: 7 passed; TypeScript and Vite production build passed.
- Desktop: 2 passed; Electron entry syntax checks passed.
- OpenAPI export/TypeScript generation is idempotent; 108 Python files passed syntax/duplicate-definition checks; compileall and `git diff --check` passed.
- A newly rebuilt current Linux x64 frozen sidecar completed CLI, protected health, Setup, industry creation, model-free bootstrap, job completion, overview read, and graceful shutdown against an isolated temporary data root.

## Remaining release gates

This working tree has no same-revision Windows, macOS, and Linux runner results and no current installer renderer lifecycle across all three hosts. Local WSL is not those hosts. The conclusion remains `NOT_READY_PENDING_NATIVE_GATES`; old `4.0.0-test.1` artifacts are not current. Offline evidence also does not replace real account/API or production live-collection integration evidence.

Round 1 is closed within the local boundary. In the user's required order, Superpowers may now be enabled and the final fresh review may begin.
