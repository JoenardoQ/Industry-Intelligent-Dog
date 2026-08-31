# IntDog Complete Product One-Time Approval Packet

Date: 2026-09-01
Status: Approved for full delivery, implementation in progress
Overall design: [`specs/2026-09-01-complete-local-first-product-design.md`](specs/2026-09-01-complete-local-first-product-design.md)

## Approval Objective

This approval packet divides the complete product refactor into five connected subprojects. After approval, the execution phase proceeds continuously in the order `1 → 2 → 3 → 4 → 5`; each subproject strictly follows RED, GREEN, regression, specification review, and code-quality review. Unless a real blocker requires new external permissions, an irreversible data operation, a paid call, or a publication action, design approval is not requested item by item again.

At the end of this file, the user may choose the “Local Continuous Implementation” or “Complete Delivery” scope. “Local Continuous Implementation” authorizes only changes to local source code, tests, documentation, and build configuration, plus local validation that incurs no fees. “Complete Delivery” additionally authorizes creating an ordinary commit, pushing to `origin/main`, triggering the existing three-platform CI, idempotently reusing or updating the existing three platform Issues (creating only missing ones) and corresponding public Beta Pre-releases after the gates pass and `$clean-before-commit` reports no blockers, and running one fixed, bounded smoke test with no user data through an existing subscribed Agent CLI when a valid local login is detected. Neither scope authorizes force-pushing, rewriting history, signing, notarization, real paid API calls, or deleting users’ production data.

## Common Product Boundaries

- The product is an installable Windows, macOS, and Linux local-first desktop application, not a source-code project intended only for developers.
- With no API key and no model, it still completes the minimum useful workflow through public information sources that require no credentials.
- Do not implement email push, cloud synchronization, team collaboration, or IntDog cloud accounts.
- Agent results are manually reviewed first and then become candidate evidence; they can be promoted to accepted facts only after citation semantics, reproducible evidence location, numeric/unit/definition consistency, assertion-type corroboration, and all other applicable gates pass.
- Source search runs for at least two rounds, using Chinese and English queries and gap-driven expansion; network, rate-limit, and budget errors may only pause and cannot count as convergence.
- Each source category targets 8–10 qualified publishers, but the quality threshold takes priority; shortages must be reported explicitly and not filled with low-quality sources.
- After the App window closes, authorized scheduled tasks continue through the local background service.
- Three-platform Beta builds must come from the same Git revision and pass lifecycle validation on their respective native runners.

## Subproject 1: Authoritative Contract and Agent Evidence Loop

**Objective:** Eliminate the Agent Bridge’s anonymous contract and file-scan status, and split Agent output into reviewable, verifiable assertions and citations that cannot skip levels.

**Primary deliverables:**

- Schema 14: Agent results, assertions, citations, and review records; old JSON remains immutable and is indexed idempotently.
- Strongly typed Pydantic/OpenAPI API, with limits on Profiles, task packages, result sizes, and path boundaries; extensible capability Manifest, secure discovery, and distinctions among direct, handoff, and import-only.
- State machine: `draft_review_required → rejected/opinion/submitted_for_verification → candidate/disputed/accepted`.
- Assertion-level gates for citation reachability and identity, time/entity/conflict checks, semantic support, evidence location, numeric/unit/currency/period/definition consistency, and assertion-type independent corroboration; only `accepted` enters the Fact projection.
- Per-assertion review UI, citation links, and failure reasons in the research assistant.

**Implementation tasks:** Persistence and migration; strongly typed Bridge; assertion verification; review UI and contract generation; Agent capability catalog, secure discovery, and tiered adapters, 5 items total.

**Acceptance focus:** A valid URL is not valid evidence; `partial/unknown` semantic support, missing locators, inconsistent quantitative qualifiers, or insufficient corroboration must remain candidate. Agent-reported tier is not source identity; draft cannot go directly to accepted; repeated imports do not lose review; OpenAPI does not return anonymous `{}`; path attacks and corrupted files have deterministic errors.

**Documents:**

- [Detailed specification](specs/2026-09-01-subproject-1-agent-evidence.md)
- [Implementation plan](plans/2026-09-01-subproject-1-agent-evidence-plan.md)

## Subproject 2: Data Credibility and Source Coverage Engine

**Objective:** Turn source discovery from a one-off prompt into a continuous search and governance system with a ledger, stopping conditions, and human boundaries, while fixing Document/Assertion deduplication and conflict handling.

**Primary deliverables:**

- Schema 15: Source campaigns, queries, candidates, and review history.
- Chinese and English query families for nine source categories, an authoritative baseline round, and a gap-expansion round.
- Publisher identity, ownership, representativeness, coverage contribution, access status, and periodic review.
- Strict automatic-activation boundary for official primary sources; media, self-media, leadership, and individual sources require human review.
- Stable deduplication and conflict groups for URLs, content, reposts, cross-language events, and same-owner sites.
- Entity/industry value-chain coverage matrix, expansion frontier, identity disambiguation, evidence-backed relationships, and source campaign API and review workbench.
- Immutable cross-day Story observations, day-over-day deltas, seven-day momentum, and IntDog’s own seven/thirty-day quality drift. Parquet/DuckDB remain measurable triggers rather than current dependencies.

**Implementation tasks:** Campaign persistence; two-round state machine; source review; deduplication and conflicts; entity and industry value-chain coverage; API/UI; signal momentum and drift, 7 items total.

**Acceptance focus:** Candidate pool exceeds the final target; convergence requires two consecutive rounds with no new qualified sources/entities/relationships/coverage units; 403/429/timeouts are `paused`; input order does not change deduplication results; China-source gaps are prioritized without sacrificing credibility; entity breadth and high-value endpoint depth have evidence-backed thresholds.

**Documents:**

- [Detailed specification](specs/2026-09-01-subproject-2-source-credibility.md)
- [Implementation plan](plans/2026-09-01-subproject-2-source-credibility-plan.md)

## Subproject 3: Background Tasks and Recovery

**Objective:** Replace scheduling coupled to the window/API process with a persistent task ledger and system-level local scheduling, so tasks continue after the App closes without duplicate execution.

**Primary deliverables:**

- Schema 16: Unified task ledger, leases, checkpoints, attempts, and trigger sources.
- Windowless `worker --once` entry point; when App scheduling and the Worker run concurrently, only one obtains the lease.
- Daily 04:00 boundary and week/month/quarter/half-year/two-year/five-year period rules calculated from the last successful time; adaptive 3–5-per-day density and time-bucket gates targeting about 3,000 over two years and about 8,000 over five years.
- Windows Task Scheduler, macOS LaunchAgent, and Linux systemd user timer adapters; background credentials travel through a one-shot anonymous pipe and never enter argv, environment variables, or files.
- Background-service, permission, latest/next-run, pause, retry, and recovery states in the task center and system page.

**Implementation tasks:** Task ledger; one-shot Worker and time boundaries; three-platform services; state API/UI, 4 items total.

**Acceptance focus:** `partial` does not advance the success boundary; DST, time-zone changes, dual ticks, and crash leases are recoverable; long periods cover at least 90% of applicable month buckets without padding with duplicate/low-quality entries; canary credentials are absent from argv/env/logs/ledger/state/temp files and revocation prevents new claims; email remains disabled; uninstalling the application does not delete user industry data.

**Documents:**

- [Detailed specification](specs/2026-09-01-subproject-3-background-worker.md)
- [Implementation plan](plans/2026-09-01-subproject-3-background-worker-plan.md)

## Subproject 4: Complete User Workflow

**Objective:** Organize existing scattered capabilities into a complete research workbench that is understandable on first open, operable day to day, and recoverable from errors.

**Primary deliverables:**

- Generated OpenAPI types become the sole frontend contract; remove parallel handwritten DTOs.
- Four-step first-run onboarding: data directory and privacy, industry, no-model/Provider/Agent, and first task.
- Industry overview integrates knowledge structure, information sources, documents, entities, and the directed industry value chain, with clickable drill-down.
- Daily intelligence supports the 04:00 window, title/category/source/time sorting, select all/multi-select/recoverable deletion, and accurate source attribution.
- Closed loops for sources, knowledge, periodic artifacts, research assistant, Intelligence Lab, task center, and system status.
- A mature open-source Markdown parsing chain supporting a table of contents, GFM, citation backlinks, search, and visualization sidecars, with safe HTML/URL filtering.
- Markdown plus a self-contained single-file HTML briefing requiring no backend/CDN, with a separate artifact quality gate for evidence, concrete summaries, dates/sources, duplicates/placeholders, sidecars, links, and anchors.
- A modern, low-saturation, readable responsive design system and keyboard/zoom/long-text accessibility tests.

**Implementation tasks:** Frontend contract; onboarding and overview; intelligence/knowledge/sources/artifacts; research/Lab/tasks/system; design and real renderer smoke tests; portable briefing and artifact quality gate, 6 items total.

**Acceptance focus:** Every page distinguishes loading/empty/partial/stale/error/ready; background tasks do not block navigation; industry management is recoverable; six periods are parallel direct-access buttons; long text, Markdown, dropdowns, lists, and 200% zoom remain readable; reports and charts are not placeholders.

**Documents:**

- [Detailed specification](specs/2026-09-01-subproject-4-user-workflow.md)
- [Implementation plan](plans/2026-09-01-subproject-4-user-workflow-plan.md)

## Subproject 5: Three-Platform Productization and Beta Gate

**Objective:** Generate three genuinely installable and first-runnable Beta packages from the same source version, capable of connecting to Agents/Providers and scheduling in the background.

**Primary deliverables:**

- Windows x64 NSIS `.exe`, macOS arm64 `.dmg`, and Linux x64 AppImage.
- A frozen sidecar and explicit resource manifest containing API, CLI, Worker, and runtime resources.
- Lifecycle smoke tests for installation, first launch, real public credential-free collection with a deterministic oracle, virtual secure credentials, background service, close/reopen, persistence, and uninstall retention.
- Three-platform CI path filters, SHA-256, test reports, same-revision gates, and signing conditions.
- A local reference Agent/API harness contract and at least one authorized, logged-in real Agent CLI bounded redacted smoke test; mocks cannot replace real-Agent acceptance.
- Complete and aligned Chinese and English documentation for README, installation, first use, Agent/API, background permissions, troubleshooting, uninstall, and data location.
- Retirement of the old Worker, WSL/Tk development entry points, plaintext configuration scripts, expired fixtures, and build debris after reference/replacement audits; tests with regression value are retained.

**Implementation tasks:** Freeze runtime; installer lifecycle; CI/artifact evidence; bilingual documentation; old-architecture audit and retirement; final release gates, 6 items total.

**Acceptance focus:** Do not publish if any platform fails; unsigned Windows/macOS builds may only be warning-labeled Pre-releases; the stable release must meet signing requirements, and macOS also requires notarization; Release must not precede native evidence.

**Documents:**

- [Detailed specification](specs/2026-09-01-subproject-5-native-product.md)
- [Implementation plan](plans/2026-09-01-subproject-5-native-product-plan.md)

## Dependencies and Execution Order

| Stage | Dependency | Completion gate | Downstream consumers |
|---|---|---|---|
| 1. Agent evidence | Current Schema 13, Agent Bridge | Schema 14, strongly typed contract, verification loop | Source governance, research UI |
| 2. Source credibility | Subproject 1 assertions and evidence | Schema 15, campaign state machine, deduplication and conflicts, entity/industry value-chain coverage | Background tasks, workbench |
| 3. Background tasks | Subprojects 1–2 task and source entry points | Schema 16, Worker, three-platform adapter contracts | Task UI, installers |
| 4. User workflow | Subprojects 1–3 APIs | Complete-flow UI, contract, and renderer gates | Native productization |
| 5. Native product | All Subproject 1–4 gates | Old-architecture retirement, three-platform runner evidence, and installer artifacts | Beta release candidate |

Schema migration order is fixed as `13 → 14 → 15 → 16`; every level must be idempotent, old data must remain readable, and tests must not modify real user data.

## Requirements-to-Test Traceability Entry Point

This summary is navigation, not a completed coverage audit. See the [requirements-to-test traceability matrix](2026-09-01-requirement-test-traceability.md) for requirement IDs, risks, partitions/boundaries, test IDs, decision oracles, priorities, execution platforms, current gaps, and evidence states. Until the corresponding tests run and produce evidence, their status is planned/unverified rather than covered.

| Requirement domain | Covered by | Plan tasks | Evidence type |
|---|---|---|---|
| Agent/domestic and overseas Agent interfaces | 1, 4 | 1.1–1.5, 4.4 | Capability Manifest, diagnostics, API contract, state machine, DOM |
| Source search effort, credibility, 8–10 target | 2 | 2.1–2.4, 2.6 | Decision table, state machine, property tests |
| Entity categories, industry value-chain breadth and endpoint depth | 2, 4 | 2.5–2.6, 4.2–4.3 | Coverage matrix, disambiguation/relationship tests, navigable UI |
| Deduplication, conflicts, knowledge/fact gates | 1, 2 | 1.3, 2.4 | Metamorphic tests, atomic transactions |
| Daily and long-period time boundaries | 3, 4 | 3.2, 4.3 | Clock/DST/fallback tests |
| Continue running after App closes | 3, 5 | 3.3, 5.2 | Service contract, native lifecycle |
| Complete UI, onboarding, charts, and recovery | 4 | 4.1–4.5 | DOM, axe, renderer smoke |
| Installable three-platform product | 5 | 5.1–5.5 | Native runner, hash, report |
| Bilingual installation and usage documentation | 5 | 5.4 | Structural alignment and command validation |
| Old architecture, unused code, and test debris | 5 | 5.5–5.6 | Reference/replacement list, release-surface contract, complete regression |
| Minimum useful no-model workflow | 4, 5 | 4.2, 5.2 | `NOM-01` live source/document/entity/value-chain/zero-Provider-call oracle |
| Cross-day momentum and system drift | 2, 4 | 2.7, 4.3 | Immutable observations, versioned trends, fixed evaluation set, and drift decision table |
| Portable briefing and artifact quality | 4 | 4.6 | Offline single-file contract, content manifest, deterministic partial oracle |
| Conditional columnar analysis layer | 2 | 2.7 | Scale/latency/write-blocking/backup triggers; SQLite sole write authority |

## Risk-Driven Test Model

The test set combines the following dimensions rather than covering only ideal paths:

- Data state: new, old Schema 13, repeated import, partial write, conflict, corrupted, oversized.
- Time state: first run, previous success, insufficient period, crossing 04:00, skipped/repeated DST, changed time zone, sparse long-period sampling.
- Runtime state: foreground, window closed, duplicate wakeup, crash, restart, pause, cancellation, exhausted backoff.
- Connection state: no-model, CLI, API, MCP, missing/invalid credentials, rate limiting, offline, login wall, and paywall.
- Source state: official, media, platform, self-media/individual, duplicate ownership, cross-language repost, URL variant, low-quality candidate.
- UI state: loading, empty, partial, stale, error, ready; keyboard, long Chinese/English text, narrow screen, 200% zoom.
- Platform state: Windows x64, macOS arm64, Linux x64; paths with spaces/Unicode, installation, upgrade, background registration, uninstall retention.
- Security state: path traversal, malicious URL, oversized input, log/environment leakage, packaged data contamination, dangerous shell arguments.

Cross-domain scenarios that must not be omitted include: repeated Agent import after upgrading an old database; recovery of a source campaign after a 429; the App and Worker simultaneously claiming a task that crosses 04:00; reopening the UI after a background run generates artifacts; deduplicating a cross-language repost while retaining the publisher relationship; an Agent’s conflicting assertion not overriding an accepted Fact; the no-model first-run flow; and the credential, background-service, and data-retention lifecycle after installation on all three platforms. Every scenario must be traceable to specification clauses, automated tests, or explicitly recorded native-runner evidence.

## Execution and Reporting Rules

1. Use the `$self-iteration` documentation–implementation–verification loop and the `superpowers:subagent-driven-development` two-stage review for each task; use test-first development by making the target test fail first, then implement the minimum and run relevant regression tests.
2. After each implementation is complete, perform a specification-conformance review followed by a code-quality review; major issues must be fixed before moving to the next item.
3. Route repetitive and mechanically verifiable work to GPT-5.6-Luna when the runtime explicitly supports and confirms a successful switch; this environment does not provide a verifiable switching interface, so it must not claim to have used Luna or `ultra`.
4. Do not substitute “many tests” for risk coverage; the final completeness statement must include the coverage model, gaps, and native evidence.
5. Do not modify real industry data; use isolated temporary data directories and fixtures for migration and end-to-end validation.
6. If the local environment cannot produce Windows/macOS native evidence, execution stops at `NOT_READY_PENDING_NATIVE_GATES`; do not claim three-platform completion.
7. The user selected the “Complete Delivery” scope, so ordinary commits, push, CI, idempotent reuse/update of existing platform Issues (creating only missing ones), and public Pre-releases satisfy the implementation plan’s external-action authorization point; publication still requires all native gates to pass first.

## One-Time Approval Semantics

One of the following explicit authorizations may be selected:

- Reply “Approve the five subprojects and execute continuously”: approves the five specifications, five plans, execution order, and local modification/validation boundary; it does not authorize external GitHub writes.
- Reply “Approve the five subprojects and deliver completely”: in addition to the above, authorizes an ordinary commit after a blocker-free audit, push to `origin/main`, the existing three-platform CI, idempotent reuse/update of the existing three platform Issues (creating only missing ones) and corresponding public Beta Pre-releases after the gates succeed, and one fixed, bounded smoke test with no user data through the existing subscribed Agent CLI when a valid local login is present. The user has agreed in this round, so this authorization point is satisfied and recorded in the iteration ledger.

Neither authorization permits force-pushing, history rewriting, paid calls, signing/notarization, or deleting real user data. If any of these needs or an external blocker that cannot be completed with existing credentials/runners is found, report the real status; do not substitute simulated results.
