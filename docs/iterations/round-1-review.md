# Self-iteration round 1 review

Reviewed: 2026-08-31. Scope is the complete repository state after the 4.0 web
baseline. Production industry data, authenticated model execution, SMTP, and live
external crawling were not exercised. Temporary SQLite fixtures, real localhost
HTTP, production frontend builds, and headless Chrome rendering were exercised.

## Inventory boundary

- Product and operating contract: root README/DESIGN/IMPLEMENTATION_STATUS, four
  component manuals, IIOS and Data specs, skill documents, iteration records.
- Entrypoints and deployment: `run_intdog.sh`, loading/desktop launcher, PowerShell
  shortcut, Windows batch route, web app-mode shell, CLI, MCP and read-only serve.
- Presentation: React workbench/API and retained Tk shell/pages/components.
- Domain and persistence: `intdog_core`, migrations through schema 10, compatibility
  JSON/Markdown, sources, documents, claims/evidence, entities/relations/value chain,
  reports, Lab artifacts and job manifests.
- Pipelines: profiles, source discovery/audit, HTTP/feed collectors, daily/periodic
  scheduler, verification, reports, bootstrap, agents, providers, email and tasks.
- Verification/build: Search, App and Web tests; Python compile; Vite/TypeScript
  production build; diff validation; real local HTTP and 1440×1000 visual smoke.

Generated `node_modules`, `dist`, bytecode, TypeScript build info and generated Vite
config outputs are excluded from source ownership.

## Necessity ledger

| Subject/kind | Observed consumers and contract evidence | Status | Compatibility/dynamic-discovery risk | Result/rationale | Evidence limits |
| --- | --- | --- | --- | --- | --- |
| Root product/specification documents | Define open-world industry coverage, evidence states, execution modes and user startup | necessary | External readers and future contributors depend on paths | Retain, but keep 4.0 default-entry language synchronized | No external reader telemetry |
| Desktop loading and app-mode launcher | Shortcut creates runtime, builds UI, starts localhost API and owns app window | necessary | WSL/Windows process and installed-browser differences | Current delivery meets “application” outcome without Electron weight | Native Linux/macOS and missing-browser cases not run |
| Retained Tk workbench | `--legacy`, old tests and rollback while Web parity is proven | candidate remove | Existing shortcut/docs or unknown users may invoke modules directly | One-release fallback has positive value; permanent dual UI does not | Full per-page Web parity and user acceptance still pending |
| React workbench | Default overview, daily, products, sources, research, jobs and system UI | necessary | Browser runtime and evolving API shape | Correct presentation owner; current single `App.tsx` is becoming a change hotspot | Only Overview received screenshot review; other pages compile and contract-test only |
| FastAPI local boundary | Browser operations, static app, artifact safety, task control | necessary | Route order and schema changes affect UI | Correct single query/command boundary; current 415-line module mixes concerns | No concurrent multi-client/load test |
| Desktop persistent JobManager | Tk, Web API and scheduler consume manifests, cancellation and sanitized logs | necessary | Process-group semantics vary by OS | Keep as shared supervisor; heartbeat/progress split now closes prior stall ambiguity | Windows cancellation and forced app-window close not yet exercised end-to-end |
| Search CLI dispatcher | Desktop jobs, cron, manual users and docs invoke stable commands | necessary | Public command names and scripts | Retain command compatibility; large dispatcher is a simplification candidate | Dynamic third-party invocation unknown |
| Collector implementations and feed HTTP layer | Daily six-category collection and source health | necessary | Public sites, rate limits and source-specific rules change | Capability is required; generic RSS heuristics are insufficient as the long-term adapter contract | No live crawl this round |
| Source discovery/trust/publisher ownership | Bootstrap gates, UI, verification and quality audits consume it | necessary | Model output and publisher aliases are open-world | Keep canonical publisher boundary; strengthen adapter/health lifecycle | Authority and regional coverage not freshly measured |
| Story grouping and credibility verification | Daily verification, claim evidence and ranking consume title similarity/publisher clusters | candidate simplify | Threshold changes can merge unrelated events or fragment one event | Persist Story identity and make exact dedupe, event clustering and claim verification distinct | No labeled Chinese/English evaluation corpus |
| Shared time windows and scheduler | Daily/weekly/monthly/quarterly commands, checkpoints and UI expectations | necessary | Calendar vs rolling-period interpretation | New shared owner is correct; callers must stop recomputing windows | DST zones beyond Asia/Shanghai not integration-tested |
| `intdog_core` SQLite repository and schema | All canonical read/write operations, FTS, audit, migrations and compatibility views | necessary | Existing local DBs and migrations are high compatibility risk | Retain canonical store during migration | Large DB performance and crash recovery not profiled |
| Compatibility JSON/Markdown views | Human portability, reports, old Tk and some CLI flows | candidate simplify | Users may edit/read files directly | Keep export/artifact role; progressively remove them as competing query inputs | Exact external/manual consumers unknown |
| Knowledge, report, impact and Intelligence Lab modules | Overview, Reports, Research, Lab and CLI consume artifacts | necessary | Model schemas and older artifacts vary | Retain evidence-first separation; unify Artifact presentation contract | No fresh model artifact generated this round |
| Provider factory and Codex/API implementations | Report/bootstrap commands and three execution modes | necessary | Credentials, provider capabilities and CLI versions vary | Single construction boundary is justified | Authenticated execution deliberately not run |
| Email, MCP, read-only serve and agents | Documented optional integrations and CLI commands | unassessed | Dynamic hosts/external clients may depend on protocols | Do not remove without protocol and consumer inventory | No connected client or SMTP evidence this round |
| Industry profiles/configuration | CLI aliases, collector keywords, provider and schedule defaults | necessary | User-local overrides and profile additions | Retain declarative ownership; schema validation should remain centralized | Only repository profiles inspected |
| Tests, fixture boundaries and build tooling | 223 tests/758 subtests, TypeScript build, compile and diff gates | necessary | Platform-specific GUI behavior remains outside unit tests | Strong deterministic base; web component and desktop lifecycle coverage remain thin | No CI host matrix or accessibility audit |
| Temporary/runtime/generated material | Rebuilt from lockfiles and source | candidate remove | None when exclusions and locks are correct | Excluded from versioned ownership through `.gitignore` | Existing local cache remains on disk by design |

## Coverage ledger

| Dimension | Evidence | Status | Result | Limits |
| --- | --- | --- | --- | --- |
| User outcome and scope | Baseline contract, README, final screenshot, startup code | Finding | Default path is now an application window and core requested surfaces exist; full-page parity acceptance remains | Only Overview visually inspected |
| Domain model and invariants | SQLite schema, source trust, verification, Lab/report contracts | Finding | Document/claim/entity/evidence are explicit; persistent Story identity is still missing | No labeled domain corpus |
| Architecture and dependency direction | launcher → API → dataio/service → repository; React API calls | Finding | Direction is sound, but Web API and UI top-level files own too many unrelated changes | Runtime concurrency not profiled |
| Data flow/state/lifecycle | migrations, compatibility views, collection checkpoints, job manifests | Finding | Canonical SQLite ownership is clear; compatibility files still participate in a few reads | Manual file editing unknown |
| Algorithms/complexity | story inverted index, list limits, source heuristics, time windows | Finding | Story grouping is bounded better than all-pairs, but long UI lists still render eagerly and semantic recall is unevaluated | No 10k/100k benchmark |
| Interfaces/protocols/versioning | FastAPI routes, CLI, JSON artifacts, job status | Finding | Unknown API routes now fail honestly; OpenAPI is not yet used to type the frontend | No external API consumers |
| Correctness/concurrency/idempotency | tests, locks, atomic writes, job terminal states | Finding | Baseline tests pass and shutdown reaps tasks; app-close lifecycle remains platform-sensitive | Windows end-to-end close not run |
| Security/privacy/trust | localhost bind, artifact path boundary, log redaction, dependency audit | No change justified | Current local trust boundary is proportionate; no web auth is needed while strictly localhost | Browser extension/local malware outside scope |
| Performance/cost | bundle output, 5,000-document API limit, eager React map | Finding | Acceptable for small fixtures, not for long-running industry history | No representative production-scale benchmark |
| Reliability/recovery/observability | heartbeat/progress timestamps, status UI, last-good research notes | Finding | Jobs improved; source-level circuit state and bounded last-good data remain absent | No injected network-failure campaign |
| Maintainability/duplication | Tk+Web, monolithic App/API/CLI, shared service | Finding | Temporary dual UI and weakly typed Web payloads create avoidable drift | Removal waits for parity acceptance |
| Tests/static verification | full suites, compile, Vite build, HTTP and Chrome smoke | Finding | Strong Python regression base; React behavior/a11y and OS lifecycle tests are insufficient | Browser Use CDP could not attach in WSL |
| Developer experience/docs | lockfiles, launcher fingerprint, updated manuals | Finding | One command remains valid; first npm resolution was slow but is now locked | Fresh-machine run not performed after cache removal |
| UX/accessibility/localization | screenshot, semantic buttons/forms, focus CSS, responsive CSS | Finding | Visual hierarchy is materially improved; long-list keyboard behavior and all-page responsive review remain | No screen-reader or 100/125/150% matrix |
| Build/release/deployment/rollback | runtime fingerprints, npm lock, `--legacy`, app-mode shell | Finding | Reversible migration is present; dedicated packaged binary is not yet justified | Chrome/Edge fallback not executed via shortcut |
| Compatibility/migration/adoption | retained CLI/Tk, SQLite migrations, JSON artifacts | Finding | Safe staged adoption; permanent dual ownership would be harmful | Unknown external scripts |

## Three-pass synthesis

Breadth review found five shared root causes: eager list materialization, absent
persistent Story identity, heuristic source adaptation without explicit health
state, weak Web contract typing/large modules, and temporary dual desktop UI.
Cross-cutting review shows these are not independent: persistent stories reduce UI
duplication, adapter health improves task diagnostics, and typed slice boundaries
make eventual Tk retirement safer. The completeness challenge rejected adding
Redis, a graph server, microservices, or Electron now: current evidence does not
show benefits exceeding operating and migration cost.

## Qualifying optional proposals

### 1 — P0: paged and virtualized intelligence exploration

- Evidence: `/daily` can return 5,000 records and React creates one DOM row per
  result; Sources and entity blocks also materialize eagerly.
- Change: cursor-based API pagination, server-side search/sort/filter, virtualized
  list rendering, and explicit select-page versus select-all-results semantics.
- Benefit: stable interaction after months/years of collection and clearer bulk
  deletion scope.
- Effort/risk: medium; selection semantics and compatibility need tests. Reversible
  behind the current endpoints.
- Acceptance: 10,000-document fixture renders fewer than 200 rows, first usable
  content under 1 second on the local test host, filter/sort p95 under 300 ms, and
  bulk selection tests prove exact deletion scope.

### 2 — P0: persistent Story and cross-language evidence clustering

- Evidence: documents and claims persist, but story groups are recomputed from
  title overlap; no durable event/story identity or review history exists.
- Change: add Story/StoryDocument records, separate exact duplicate detection from
  event clustering, retain algorithm/version/review state, and evaluate Chinese ↔
  English entity/time-aware similarity before optional embeddings.
- Benefit: stronger corroboration, less repeated news, durable development
  timelines and honest disagreement tracking.
- Effort/risk: high; false merges are dangerous and migrations must be reversible.
- Acceptance: versioned labeled corpus, precision ≥0.95 for automatic merges,
  recall reported rather than hidden, manual split/merge audit, and no claim gains
  corroborated status from one publisher cluster.

### 3 — P0: explicit source adapters, health state and graceful degradation

- Evidence: feeds are inferred from URL/note strings; failures are logged per run
  but there is no persistent per-source circuit, retry window or last-good state.
- Change: adapter registry by access type, normalized collection result, source
  heartbeat/error/retry fields, bounded last-good content, and `fresh/stale/
  degraded/manual/unconfigured` UI states.
- Benefit: more trustworthy coverage, fewer false empty successes, clearer manual
  recommendations for high-quality non-crawlable sources.
- Effort/risk: medium-high; adapter rollout can be incremental per source class.
- Acceptance: injected timeout/403/malformed-feed tests, no failure stored as empty
  success, exponential retry ceiling, visible stale age, and three representative
  adapters each for primary records, feeds and manual sources.

### 4 — P1: typed Web slices and generated API contract

- Evidence: `App.tsx` and `api/main.py` combine all features; frontend payloads use
  pervasive `any`, so OpenAPI and TypeScript can drift silently.
- Change: feature routers/services and lazy React pages, generated TypeScript types
  from OpenAPI, runtime response validation at the boundary, component tests and
  per-page error states.
- Benefit: safer feature expansion and faster identification of contract breaks.
- Effort/risk: medium; mostly structural and reversible, but should follow stable
  pagination shapes from proposal 1.
- Acceptance: no feature payload typed as `any`, contract generation is reproducible,
  each page has loading/empty/error/content tests, and production bundle/pages build.

### 5 — P1: finish desktop lifecycle, then retire duplicate Tk ownership

- Evidence: default app-mode shell works and `--legacy` remains; two UI trees and
  two scheduling surfaces will otherwise diverge.
- Change: verify shortcut → loading → app window → close lifecycle and single
  instance on WSL/Windows; complete Web parity; then remove Tk pages/scheduler while
  retaining a time-bounded rollback tag or branch rather than a second live UI.
- Benefit: a real application experience with one UI owner and lower maintenance.
- Effort/risk: medium-high and platform-sensitive; depends on proposals 1 and 4 plus
  user visual acceptance. Removal is delayed and explicitly gated.
- Acceptance: one shortcut starts one service/window, close reaps tasks within five
  seconds, Chrome and Edge fallback pass, all seven Web destinations pass interaction
  smoke, and no documented operation requires Tk before removal.
