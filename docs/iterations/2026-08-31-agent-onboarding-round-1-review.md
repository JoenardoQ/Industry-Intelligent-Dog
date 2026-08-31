# Agent and First-run Cycle · Round 1 Comprehensive Review

[中文](2026-08-31-agent-onboarding-round-1-review.zh-CN.md)

## Boundary and freshness

- Baseline: current uncommitted worktree; the downloadable-product baseline closed on 2026-08-31.
- Reviewed: root docs, Search/intdog_core, App runtime/packaging, Web API/React,
  Electron, security, tests, configuration, generated contracts, native workflows,
  and runtime evidence.
- Excluded: production-domain content re-evaluation, paid model calls, email,
  commits, pushes, publication, and deletion.
- Evidence limits: no debuggable Chrome in WSL; two electron-builder runs stalled
  at packaging; no current native Windows/macOS/Linux runner evidence; no real
  agent-account or paid-API availability proof.

## Inventory

| Partition | Current authoritative responsibility | Consumers/evidence |
| --- | --- | --- |
| `DomainIntelSearch/intdog_core` | Schema, facts, migration, entity/Story/evidence/schedule state | Search, Web API, MCP, 161 Python tests |
| `DomainIntelSearch/src` | Collection, history, research, reports, providers, MCP, CLI | sidecar CLI, jobs, report/research UI |
| `DomainIntelApp/runtime` | Compatibility I/O, durable jobs, single instance, shared runtime | Electron sidecar, source launcher, App tests |
| `DomainIntelWeb/api` | Protected local application boundary and scheduler owner | React, Electron, OpenAPI |
| `DomainIntelWeb/src` | Seven-page workbench, onboarding, jobs, artifacts | Desktop users, six DOM workflow tests |
| `DomainIntelDesktop` | Electron lifecycle, secure storage, native packaging | Three installers, sidecar, native smoke |
| Docs/config/generated contracts | User contract, design, status, release, provider config | Users, maintainers, CI |
| `.github/workflows` | Native builds and release gates | GitHub-hosted native runners |
| `DomainIntelData` | Production facts and portable artifacts; excluded from packages | App/Search; read-only in this review |

## Necessity ledger

| Subject/kind | Observed consumers and contract evidence | Status | Compatibility/dynamic-discovery risk | Result/rationale | Evidence limits |
| --- | --- | --- | --- | --- | --- |
| SQLite/intdog_core fact kernel | Web, Search, MCP, migration, all industry data | necessary | High; data format and external JSON readers | Retain as sole business-write authority | Third-party readers unassessed |
| Compatible JSON/dirty views | Reports, portable data, legacy migration | necessary | High; existing data/scripts | Retain reconciliation | Non-core attachments are not transactional |
| Search collection/research/reporting | Core industry knowledge and monitoring outcome | necessary | Medium; network/provider drift | Retain module boundary | No live collection in this review |
| Legacy Orchestrator/ArchiveStore path | Some old CLI/modules still construct it | candidate simplify | High; dynamic module registry and old CLI | Stop implicit construction for modern commands; do not delete yet | Dynamic call graph is incomplete |
| Provider factory/agent adapters | Reports, bootstrap, coverage, task execution | necessary | High; external CLI/API evolution | Retain one construction boundary | DeepSeek Harness is a developer preview |
| Agent registry | `/api/setup`, onboarding, connection status | necessary | Medium; PATH/custom/version differences | Retain capability labels | Real accounts untested |
| Read-only MCP | Claude/Work Buddy/other agent reads | necessary | High; protocol/client compatibility | Keep read-only default; gate result writes separately | Synthetic protocol evidence only |
| Web API/OpenAPI | Sole React/sidecar business boundary | necessary | High; client/generated-type compatibility | Keep and strengthen generation gate | External clients unknown |
| Seven-page React UI | Sole released UI | necessary | Medium; accessibility/responsiveness | Retain | No current visual browser evidence |
| Electron + PyInstaller | Three native downloadable products | necessary | High; signing/OS/secure storage | Keep one shared implementation | Current installers not natively verified |
| Chrome app-mode source launcher | Development/compatibility startup | necessary | Medium; source users may depend on it | Keep as dev entry, not distribution | Usage unknown |
| Provider enums/capabilities | Repeated in factory, schema, CLI, UI, scheduling, docs | candidate merge | High; omission creates selectable-but-broken modes | Consolidate into backend manifest | Handwritten TS migration required |
| Status/design/release docs | Installation and maintenance decisions | candidate simplify | Medium; preserve historical links/evidence | Revision-scope evidence and archive history | Historical readers unknown |
| Native workflows | Package production and publication protection | necessary | High; host differences | Expand gates; keep one implementation | Three hosts unavailable locally |
| Test system | 161 Python, 6 DOM, Node, sidecar/package smoke | necessary | Low; internal contracts | Retain risk-based layers | No real paid API/account |
| Production `DomainIntelData` | Long-lived user fact database | necessary | Extreme; irreversible data risk | Read-only; no cleanup | Content quality excluded |

## Coverage ledger

| Dimension | Evidence | Status | Result | Limits |
| --- | --- | --- | --- | --- |
| User outcome/scope | bilingual README, onboarding contract, fresh local workflow | Finding | Model-free first task works; agent handoff lacks one-click setup/result journey | No native visual pass |
| Domain model/ownership | core, ProviderCapabilities, AgentSpec, task/artifact states | Finding | Agent, model provider, and MCP client differ correctly, but enum ownership is distributed | External agents evolve |
| Architecture/dependencies | Search→core, Web API→service, Electron→sidecar | Finding | Main direction is sound; legacy Orchestrator can still be constructed implicitly | Dynamic modules limit graph evidence |
| Data/schema/lifecycle | schema v13, compatible views, jobs/trash/audit | no change justified | Additive migration and recovery meet current scope | Attachment ACID excluded |
| Algorithms/resource bounds | pagination, history buckets, coverage gates, timeouts | no change justified | Count/time/publisher and context bounds exist | No new production benchmark |
| Interfaces/protocol/versioning | OpenAPI, MCP 2024-11-05, CLI/API adapters | Finding | MCP is discoverable but UI does not emit client config; provider lists repeat | No multi-client interoperability run |
| Correctness/concurrency | locks, claims, provider gate, onboarding retry | Finding | Unready providers do not queue; native smoke does not operate React | Multi-day sleep untested |
| Security/privacy/supply chain | safeStorage, preload, CSP, session, HTTPS | Finding | Key avoids DOM/API/logs; native secure-storage lifecycle and dependency audit are not full CI gates | Unsigned builds |
| Performance/cost | 50-row pages, 500-context cap, 8-second diagnostics | no change justified | New diagnostics are bounded and parallel | Slow WSL/many CLIs untested |
| Reliability/recovery/observability | logs, manifests, retry, shutdown, marker | Finding | Sidecar observable; API-first package smoke can miss a blank React UI | Local AppImage build blocked |
| Maintainability/extensibility | factory, literals, selects, help, registry | Finding | New agent requires synchronized edits across layers | Third-party extensions unknown |
| Tests/static checks | 161 Python, 6 DOM, Node, compile/check_repo | Finding | Strong local suite; native workflow omits full Python/DOM/OpenAPI drift gates | No coverage percentage |
| Developer experience/docs | root/subsystem READMEs, DESIGN, STATUS | Finding | Install docs improved; design/status/release evidence has revision drift | Preserve historical provenance |
| UX/accessibility/localization | onboarding, Chinese UI, responsive CSS, roles | Finding | First industry is guided; long agent list/font/zoom needs visual evidence | No Chrome/CDP |
| Build/release/rollback | native workflows, signing gates, old prerelease | Finding | Structure sound; current diff has no native evidence, so old READY does not apply | No publication authority |
| Compatibility/adoption | CLI/JSON, source launcher, MCP, old Orchestrator | Finding | Additive compatibility should remain; direct deletion is high-risk | Adoption telemetry absent |

## Three-pass conclusion

1. **Breadth:** every code root, entry point, test/config/schema/dependency/build/generated/doc/runtime partition is inventoried; production content is boundary-only.
2. **Cross-cutting:** agent extensibility, dropdown drift, and scheduler validation share one root cause—a capability catalog without one owner. Downloadability risk comes from native jobs testing the shell/sidecar without the complete product contract.
3. **Completeness challenge:** SQLite, compatible JSON, source launcher, and read-only MCP have real consumers. There is no deletion evidence. Legacy Orchestrator is simplifiable but not safely removable now. Commercial databases, full social APIs, and a bundled local model are not low-risk completion items.

## Complete proposal set — awaiting selection

### 1. P0 — Upgrade native gates into product gates

- Problem: `_native-package.yml` runs Desktop Node tests, sidecar health, and an API-first desktop smoke, but omits the full Python/DOM/OpenAPI-drift gates and does not prove that React onboarding is operable.
- Change: run Python/DOM/types/OpenAPI/check_repo on every host; have desktop smoke inspect renderer DOM for onboarding, first-industry creation, task center, and reopen persistence. Where safe storage exists, test encrypted write/clear with a dummy secret and prove non-disclosure.
- Benefit: the installer gate matches “a user can download and use it.”
- Cost/risk: medium; longer native jobs and OS-specific renderer timing. Reversible test/workflow/E2E changes.
- Acceptance: every runner passes; Web, DOM, Python, OpenAPI, sidecar, first task, reopen, or credential leakage failure blocks the artifact.

### 2. P0 — Complete the Agent Bridge user loop

- Problem: Setup detects nine agents, but never presents/copies `mcp_command`; MCP is read-only; custom agents require environment variables; task packages lack a visible claim→execute→import→review loop.
- Change: generate copyable Codex/Claude/Work Buddy/generic MCP config; add validated custom CLI profiles; list/export task packages and import results. Writes remain `draft_review_required`, with industry-path, size, schema, citation, audit, and atomicity checks. MCP remains read-only by default; write capability requires explicit desktop-session authorization.
- Benefit: unbundled domestic and international agents become usable, not decorative catalog entries.
- Cost/risk: high; new API/schema/UI/audit/security tests. Additive and reversible through read-only default.
- Acceptance: four config families generate; an unknown agent can export a task and import a valid result; traversal, oversized, invalid-schema, and unauthorized writes fail without partial mutation.

### 3. P1 — Establish one capability manifest

- Problem: provider/agent IDs and capabilities repeat in `provider_factory.py`, `llm_service.py`, Pydantic literals, repository validation, CLI help, two React selects, TypeScript unions, and docs.
- Change: one backend manifest owns ID, region, connection/execution type, web search, auth, model/API base, and docs. API exposes typed data; UI/scheduling render dynamically; adapter map stays explicit and unknown IDs fail closed.
- Benefit: adding an agent/API changes one definition plus its adapter and cannot create a selectable-but-broken mode.
- Cost/risk: medium cross-layer contract migration; retain old provider IDs.
- Acceptance: no second handwritten provider dropdown/allow-list; manifest/factory/API/scheduler/UI sets agree under contract tests.

### 4. P1 — Reconcile current docs and revision-scoped release evidence

- Problem: `IMPLEMENTATION_STATUS.md` omits the new onboarding/agents and has stale counts; `DESIGN.md` is primarily a v2 historical architecture and contains mojibake; release `READY_FOR_PUBLIC_TESTING` evidence belongs to an older commit and is invalid for the current diff.
- Change: concise aligned Chinese/English current architecture/status docs; move historical design under an explicit archive; bind native evidence to commit/diff and set current conclusion to `NOT_READY_PENDING_NATIVE_GATES`; keep root README focused on the user path.
- Benefit: users do not download the old EXE expecting new onboarding, and maintainers do not implement against obsolete architecture.
- Cost/risk: low-medium documentation migration with link preservation; fully reversible.
- Acceptance: bilingual structure/semantics align; commands work; version/test counts/platform/agent boundaries/release conclusion match code and evidence; no mojibake or conflicting architecture claims.

## Dependency and order

Recommended order: `1 → 3 → 2 → 4`. Proposal 3 gives proposal 2 stable capability data, while proposal 1 can establish regression protection first. Commit, push, CI execution, and publication remain separately gated.
