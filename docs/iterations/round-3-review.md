# Self-iteration round 3 comprehensive review

Reviewed: 2026-08-31. This is the third-round review and proposal gate, not an
implementation claim. Round 2 is closed in `round-2-closeout.md`. No production
data was changed and no crawl, model, email, commit, push or deployment ran.

## Inventory and evidence boundary

The breadth pass covered the four product roots and their consumers: 62 Search
Python modules, 9 canonical-core modules, 28 retained Tk modules, 16 Web API
modules, 14 Web source/style files, 19 Python test files, five industry profiles,
runtime/shortcut scripts, schema migrations, generated OpenAPI, package locks and
the four top-level usage/design/status documents. Fresh Round 2 evidence is 253
tests plus 758 subtests, deterministic OpenAPI/TypeScript generation, a production
Web build, 118-file AST check, compile/diff checks, a temporary API lifecycle and
Windows headless-Chrome seven-route smoke.

This was a static and deterministic-runtime review. It did not evaluate live
source recall, model output quality, a long-running scheduler, a real desktop
shortcut session, assistive technology, paid APIs, SMTP, MCP clients or production
data. Those areas are named `unassessed` below rather than treated as passed.

## Necessity ledger

| Subject/kind | Observed consumers and contract evidence | Status | Compatibility/dynamic-discovery risk | Result/rationale | Evidence limits |
| --- | --- | --- | --- | --- | --- |
| React/FastAPI local workbench | Default launcher, seven lazy routes and user-approved app direction | necessary | High if launcher/route contract changes | Keep as primary product boundary | No fresh user-operated shortcut acceptance |
| Tk legacy client | Explicit `--legacy`, mature job/research/source pages and fallback contract | necessary | High until Web parity and visual acceptance close | Retain as fallback; do not expand it | Current users of legacy mode are unknown |
| SQLite v12 canonical store | All industry, evidence, Story, coverage, schedule and audit state | necessary | Very high durable-data/migration risk | Keep; additive migrations remain correct direction | Production migration was not run this round |
| JSON/Markdown compatibility artifacts | Existing readers, CLI, reports, MCP and user files | necessary | High external-reader risk | Preserve reads and controlled writes | External consumers are not fully inventoried |
| `IndustryStore`/`IntDogService` compatibility bridge | Search, Tk and Web data access | necessary | Medium-high due mixed SQLite/file ownership | Keep until artifact writes have one canonical transaction boundary | Change-frequency history unavailable |
| Web period buttons and scheduler commands | Products, Research Studio and System invoke `weekly/monthly/quarterly` | candidate simplify | High semantic compatibility risk | One typed pipeline must distinguish aggregate-only from Markdown generation | No model job was executed |
| Durable scheduler rows/leases | Web automation, restart catch-up and tests | necessary | High concurrency/time risk | Keep persistence; repair failure/retry and pipeline semantics | Fake-clock and one-process lifecycle only |
| JobManager and manifests | Web/Tk task centers, cancellation, shutdown and logs | necessary | High process-management risk | Keep one executor; expose existing controls coherently in Web | No sustained multi-process run |
| Web Jobs page | User-visible operations status | candidate simplify | Low API risk, medium UX risk | Expand from read-only log browser into cancel/retry/stage control | Browser smoke did not operate jobs |
| Daily document pagination | Daily list, search, sort and bounded selection | necessary | Medium opaque-cursor contract | Keep; measured 10k performance is adequate | Concurrent insertion drift unmeasured |
| Story persistence and review audit | Daily Story view, evidence independence and review history | necessary | High epistemic/data risk | Keep, but protect manual editorial decisions from reclustering | No labelled real corpus |
| Raw-ID merge/split UI | Only current manual Story correction workflow | candidate simplify | Low data-format risk if API remains | Replace ID typing with visual document/Story selection | Real editorial usability untested |
| Automatic Story reclustering | Verification writes persistent groups after crawl | necessary | High false-merge/split risk | Retain conservative automation with reviewed locks and candidate suggestions | Precision/recall unknown |
| Claim/evidence/contradiction tables | Lab, reports and credibility semantics | necessary | High research-trust risk | Expose them in Story/entity research views | Extraction quality not measured live |
| Coverage cells and query attempts | Research coverage panel and bootstrap planning ledger | necessary | Low additive-schema risk | Keep as open-world state model | Current cells are coarse endpoint×region seeds |
| Deterministic query text generator | `/coverage/plan` creates planned attempts | candidate simplify | Medium search compatibility risk | Make it one planner stage, not a discovery result | No actual search adapter is connected |
| Client-supplied coverage yields | Attempt API accepts counts/evidence from the SPA | candidate remove | High audit-integrity risk | Automated yield must be derived server-side; manual correction must be separately audited | No current UI calls the manual endpoint |
| Source adapters/health/publisher trust | Crawlers, source page, verification and Lab | necessary | High provider-specific behavior | Reuse as validation boundary for coverage execution | Live provider matrix unassessed |
| Hard-coded seed sources | Offline initialization fallback | necessary | Medium freshness/anchoring risk | Retain as disclosed bootstrap only | Freshness not live-audited here |
| Overview knowledge graph | User requires knowledge structure and directed value chain in overview | necessary | Low route risk | Keep overview entry, deepen navigation | Current graph is chain-node summary, not full relation explorer |
| Overview `entities.slice(0, 10)` | Only Web entity presentation | candidate remove | Low compatibility risk | Fixed ten-item truncation contradicts open-world exploration goal | Large-industry UX not browser-tested |
| Repository graph/neighbour queries | Core exposes entity relation graph but Web has no consumer | candidate simplify | Medium schema/API risk | Add bounded entity detail/search consumers before adding graph algorithms | Query scale beyond 500 edges unmeasured |
| Research Studio actions | Direct bootstrap/report/deep/impact/Lab and collection entry | necessary | High model/CLI request-shape risk | Keep unified entry; correct period semantics and artifact refresh | Authenticated provider not run |
| Product library/Markdown reader | Period/report/deep/impact artifact consumption | necessary | Medium historical-artifact risk | Keep typed common card and reader | Citation links and very large Markdown untested |
| Trash/archive restore | System page and recoverable deletion contract | necessary | High user-data risk | Keep; add preflight and audit visibility | Interrupted file/DB restore tested only by unit paths |
| Local session/Host/Origin/CSP boundary | Launcher and all unsafe API methods | necessary | High desktop security risk | Keep launch-scoped capability | No adversarial browser or dependency scan |
| Pydantic/OpenAPI generator | API contract and deterministic generated file | necessary | Medium client compatibility risk | Make it authoritative for responses, not paths only | Several legacy routes remain broad dictionaries |
| Hand-written TS payload types/guards | Every feature imports `api.ts`; generated output supplies only `ApiPath` | candidate merge | Medium compile/runtime drift risk | Generate and consume response types, retain small runtime validators at trust boundary | No external TypeScript client known |
| Python/static frontend tests | 253-test regression and source-contract checks | necessary | Low | Keep fast deterministic layer | Static string checks do not exercise DOM behavior |
| Optional Playwright smoke | Seven routes, Story tab, coverage, schedules and narrow overflow | necessary | Medium host tooling fragility | Keep as release smoke and expand workflows | Not in npm scripts/CI; no axe or screen reader |
| Industry profiles/config | Search keywords and five built-in domains; custom profile fallback | necessary | Medium content-quality risk | Keep configurable profiles without limiting arbitrary industries | Only AI/Chips have substantial historical exercise |
| Email CLI compatibility | Search scheduler/service/docs, explicitly excluded from default App | unassessed | High credential/external-delivery risk | Preserve disabled compatibility; no App expansion | SMTP not authorized |
| MCP/read-only serve/external agent surfaces | Commands, docs and tests expose integration contracts | unassessed | High unknown-client risk | Preserve; exclude from Round 3 mutation unless separately approved | No connected-client evidence |
| Packaging/CI/SBOM | Local launcher and lock files exist; no repository CI/release pipeline | candidate simplify | Low runtime, medium maintenance risk | A CI gate is useful only after UI tests are selected; not a standalone product rewrite | Hosting/release target is not defined |

## Coverage ledger

| Dimension | Evidence | Status | Result | Limits |
| --- | --- | --- | --- | --- |
| Product outcome/scope | Original IIOS goal, current README, seven Web routes | Finding | The app now has the right workbench outline, but full-industry exploration is still truncated and discovery is not closed-loop | No user study |
| Domain model/invariants | v12 schema, Story/claim/evidence/coverage/schedule models | Finding | Strong additive model; manual Story decisions and validated coverage yield need explicit invariants | Production distributions unmeasured |
| Architecture/ownership | Web routers, core service/repository, Search CLI, retained Tk | Finding | Default ownership is clearer; generation semantics still duplicated between crawl and generate commands | Dynamic imports/external consumers incomplete |
| Data flow/lifecycle | SQLite facts, compatibility JSON, immutable Lab bundles, trash | Finding | Core data is durable; coverage evidence admission and restore preflight remain weak | Cross-media ACID is unavailable |
| Algorithms/complexity | Story inverted index, coverage ranking, Overview all-entity load | Finding | Story is bounded but uncalibrated; coverage ranking is priority sorting only; Overview performs all-entity O(chain×entity) work to display ten | No million-row benchmark |
| Interfaces/contracts | OpenAPI types, manual TS payloads, broad legacy response dicts | Finding | Contract generation exists but is not the frontend source of truth | External API clients unassessed |
| Correctness/edge cases | Scheduler claim code, operation command map, Story save/review code | Finding | Period “generate” runs crawl only; failed claimed periods do not retry; reclustering can reattach reviewed documents | No live failure injection across OS processes |
| Concurrency/idempotency | SQLite transaction claims, leases, JobManager locks | Finding | Duplicate enqueue is guarded; crash/failure semantics conflate attempted and completed period keys | Long-running two-process test absent |
| Security/privacy | Session capability, Host/Origin, CSP, localhost bind | no change justified | Current local write boundary is proportionate | Dependency vulnerability/adversarial browser review absent |
| Performance/resource bounds | 10k Daily benchmark, bounded job logs, Story/graph limits | Finding | Daily is adequate; Overview and Story/coverage lists need server paging before large industries | Memory profile absent |
| Reliability/recovery | scheduler state, job manifests, trash restore | Finding | Status survives restart, but Web lacks retry/cancel controls and restore collision preview | Power loss not simulated |
| Observability/operations | Job output, heartbeat, scheduler error/next time | Finding | Representative logs exist; pipeline stages, retry reason and schedule-to-artifact link are not visible | No long-duration telemetry |
| Maintainability/redundancy | 1,429-line repository, mixins, manual/generated TS duplication | Finding | Do not split by line count; consolidate only contracts selected below | Git change-frequency unavailable |
| Tests/verification | 19 Python test files, optional Playwright, no JS test dependencies | Finding | Excellent deterministic backend regression; real DOM, focus, keyboard and accessibility behavior remain largely untested | No coverage report/axe/screen reader |
| Developer experience | isolated launcher, package locks, contract scripts, READMEs | Finding | Setup is workable; browser smoke and contract/build checks are not one documented release command | Fresh Windows bootstrap not run |
| UX/accessibility/localization | modern responsive CSS, labels, bilingual UI, raw-ID editing | Finding | Readability improved; entity exploration and editorial correction are still operator-hostile | Only two screenshots and one narrow viewport |
| Build/release/deployment | Vite build, venv/npm bootstrap, no deployment target | no change justified | Local-first delivery matches current authority; do not invent cloud deployment | macOS/Linux packaging not claimed |
| Compatibility/migrations | additive schema v12, legacy Tk/files/CLI retained | no change justified | Compatibility-first policy remains appropriate | Third-party readers unknown |
| Source credibility/breadth | trust registry, source health, open-world prompt/ledger | Finding | Credibility semantics are sounder than count quotas, but planned queries are not validated discoveries | No live recall measurement |
| China-native coverage | origin metadata plus suffix fallback, planner priority | Finding | China gaps are prioritized, but `.com` Chinese publishers can be misclassified without verified publisher metadata | Current production ratio intentionally not reread as proof |
| Research depth/provenance | claims/references/status, reports, Lab, product reader | Finding | Artifact structure is promising; no systematic claim/citation quality evaluation exists | Domain-expert review absent |
| Financial/legal high stakes | draft labels and limitations | Finding | Draft labelling is necessary, but market cap/import-export/policy assertions still require source/date/currency quality gates | No current-market validation authorized |
| Email/MCP/external services | Disabled App email; optional CLI/MCP surfaces | unassessed | Preserve without claims | Credentials/clients unavailable |

## Three-pass synthesis

### Pass 1 — reachability and semantic truth

The seven-route shell is no longer the main gap. The sharper issue is whether a
button does what its label promises. Both Products “生成周/月/季” and Research
Studio period actions map to `crawl-*`, which writes aggregation/task metadata;
only `generate-period` creates Markdown. Automation uses the same crawl mapping.
This is a correctness defect, not a naming preference. Likewise, “生成搜索计划”
only persists query strings; no search, URL validation or entity/source admission
follows it.

### Pass 2 — evidence integrity and long-running failure behavior

The system now persists the right operational and epistemic state, but two
transitions are too permissive. A scheduler claim writes `last_period_key` before
the job succeeds, so a failed or crashed job cannot automatically retry that
period. Coverage attempts accept yield counts and arbitrary evidence directly
from a write client, so those values are not yet computed facts. Story review is
audited, but later automatic groups are free to attach reviewed documents again
because document membership is not protected by an editorial lock.

### Pass 3 — breadth, usability and proof

The original goal is broad knowledge expansion. Overview loads all entities but
shows a hard-coded ten and exposes no searchable entity/relationship/evidence
detail. This recreates the Top-10 boundary at the UI layer. At the same time,
there is no labelled evaluation corpus or claim/citation quality gate capable of
showing that broader search, clustering or reports are actually better. More
sources and longer prose would therefore increase volume before confidence.

## Correctness defects independent of proposal preference

- Web “生成周报/月报/季报” and automatic period cards execute `crawl-*`, not
  `generate-period`; the labelled Markdown product is not produced.
- `claim_schedule` stores the period as consumed before successful completion.
  Failure, process death after claim, or callback loss leaves the period unable
  to retry automatically even after its lease expires.
- Coverage yields and evidence can be asserted by an authenticated local client;
  they are not derived from validated URLs/documents/entities.
- Automatic Story persistence does not reserve documents affected by a manual
  merge/split, so later reclustering can undermine the reviewed grouping.
- Overview claims open-world knowledge exploration while hard-truncating entities
  with `slice(0, 10)` and offering no entity/relationship drill-down.

## Qualifying proposals

### 1. P0 — make period generation and scheduler completion truthful

**Evidence.** `operations.py`, `automation.py` and the Products buttons map period
generation to `crawl-*`; `generate_periodic` is the only Markdown path. Schedule
claims update `last_period_key` before completion.

**Change/benefit.** Define one typed period pipeline: aggregate → optionally
generate Markdown with a configured provider → register artifact. Let users choose
“仅聚合” or “生成报告”; default labels must match. Separate attempted, running,
completed and retryable period keys; use idempotent artifact identity and bounded
retry/backoff. Email remains impossible in the Web pipeline.

**Effort/risk.** Medium-high; model authentication and crash recovery are the main
risks. CLI commands/files remain compatible and the pipeline can be feature-
flagged. Depends on JobManager and scheduler schema migration.

**Acceptance.** Period buttons create nonempty Markdown plus metadata under fake
provider tests; aggregate-only is explicitly labelled; failed/crashed jobs retry
without duplicate successful artifacts; two owners cannot run one period
concurrently; restart/DST/catch-up tests cover all periods; UI links schedule run
to job and artifact; no task calls email.

### 2. P0 — execute and validate the open-world coverage loop

**Evidence.** `/coverage/plan` creates deterministic strings only; no adapter runs
them. `/attempts` accepts client-supplied yields/evidence. Bootstrap model claims
correctly remain planned but have no promotion path.

**Change/benefit.** Add a budgeted planner worker that dispatches queries to
source-appropriate search/adapters, canonicalizes and fetch-validates candidate
URLs, resolves publishers, records rejected candidates, admits sources/entities
through existing services, then computes marginal yield from canonical IDs. Keep
manual correction as a separately audited assertion, never an automated yield.
Prioritize native Chinese authoritative gaps without a ratio quota.

**Effort/risk.** High and methodologically central. Network variability, rate
limits and query cost require explicit budgets and deterministic fake adapters.
Additive and reversible; old planned rows remain readable.

**Acceptance.** Fake adapters exercise planned→running→completed/failed/stopped;
only validated canonical objects increase yield; duplicate or unreachable URLs do
not; publisher origin is evidence-backed; rejected reasons and stopping logic are
visible; retries are bounded; a gated live evaluation reports yield and gaps
without claiming completeness.

### 3. P0 — turn Overview into a full industry knowledge explorer

**Evidence.** Overview loads every entity, renders ten, and has no entity detail,
relation, evidence, subdomain, learning-module or long-tail navigation despite
core graph/neighbour queries.

**Change/benefit.** Keep knowledge structure inside Overview but add server-paged
search/filter for chain stage, entity type, geography, confidence and status;
entity detail drawers/pages with aliases, roles over time, upstream/downstream
relations, claims/evidence and source links; expandable directed graph; subdomain
and learning-dependency views. “重点” may be a ranked view, never the only ten.

**Effort/risk.** High UI/API effort, low data migration risk. Large graphs require
bounds and progressive expansion. Existing Overview summary remains a fallback.

**Acceptance.** Every active entity is reachable by paging/search; no fixed Top-10
cap defines the knowledge boundary; relation/evidence links resolve to source
documents; graph expansion is bounded and keyboard-operable; 10k-entity fixture
meets explicit latency/memory budgets; empty/unknown/conflicting states are shown.

### 4. P0 — protect Story review and expose claim/conflict editing

**Evidence.** Merge/split uses raw IDs; reviewed membership has no lock; Story
detail omits claim/evidence relations already present in the core.

**Change/benefit.** Store editorial constraints (must-link, cannot-link, locked
membership and supersession) that reclustering must honor. Replace raw IDs with
selectable Story/document candidates and side-by-side evidence. Show claims,
supports/contradicts/qualifies, publisher ownership, missing evidence and review
reason; automatic suggestions remain reversible proposals.

**Effort/risk.** High epistemic value, medium-high migration and clustering risk.
Additive constraints preserve historical audits; document view remains available.

**Acceptance.** Repeated reclustering cannot undo reviewed split/merge; one
document has one active Story membership unless explicitly modelled as a link;
conflicting claims remain separate; visual selection prevents foreign-document
IDs; labelled bilingual fixtures measure precision/recall and browser tests cover
keyboard merge/split/undo/error flows.

### 5. P1 — complete the Web operations and recovery control plane

**Evidence.** Backend supports cancellation but Jobs has no cancel control and no
validated retry path. Scheduler/job/artifact linkage is absent. Restore has no
preflight collision detail or audit viewer.

**Change/benefit.** Add job cancel, safe retry-from-known-operation, stage/progress,
schedule origin and produced-artifact link. Add recovery preview showing target,
collisions, skipped records and compensating action; expose immutable operation/
restore audits. Do not add permanent deletion by default.

**Effort/risk.** Medium. Retry must reconstruct only allowlisted operations, not
execute arbitrary historical command arrays. Restore remains compensating rather
than pretending SQLite/files are one ACID transaction.

**Acceptance.** Active jobs cancel from Web; eligible failed jobs retry with a new
run ID and parent link; arbitrary command replay is rejected; stages/logs update;
restore preview exactly predicts collisions/skips; injected failures are
repairable and audited; browser tests cover idle, running, failed and recovered.

### 6. P1 — make OpenAPI authoritative and add real DOM/accessibility tests

**Evidence.** Generated TypeScript interfaces exist but features consume manual
payload types; generated output contributes only `ApiPath`. Several older routes
have dictionary responses. Frontend tests are Python string assertions plus an
optional heading smoke; there is no React DOM or accessibility dependency.

**Change/benefit.** Type all API responses/errors, generate operation-aware client
types, consume them in features and retain focused runtime validation. Add a small
Vitest/Testing Library/axe layer for forms, focus, keyboard, live status, Story,
jobs and recovery; make browser smoke a documented command with zoom matrix.

**Effort/risk.** Medium and mostly engineering quality. New dev dependencies add
maintenance cost but no runtime weight. Migrate route families incrementally.

**Acceptance.** No duplicate manual API payload interface remains for typed
routes; OpenAPI diff is deterministic and breaking changes fail tests; seven
routes have rendered behavior tests; no critical axe findings; dialogs/forms
restore focus and work by keyboard; 125/150/200% browser checks have no page-wide
overflow.

### 7. P1 — establish an industry-intelligence evaluation and quality gate

**Evidence.** Unit fixtures verify mechanics, but there is no labelled benchmark
for retrieval, publisher attribution, Story clustering, entity linking, citation
validity or report claim traceability. Current quality claims therefore stop at
determinism, not professional research accuracy.

**Change/benefit.** Create versioned, licence-safe offline evaluation packs across
AI and Chips with Chinese and foreign sources, duplicates/reprints, conflicting
claims, entity aliases and expected chain classifications. Score query precision
and marginal yield, Story pairwise precision/recall, publisher independence,
entity linking, citation reachability/as-of dates and report claim coverage.
Separate offline regression from explicitly approved live freshness evaluation.

**Effort/risk.** Medium-high curation effort and highest credibility leverage.
Benchmarks can overfit, so keep hidden holdouts/versioned datasets and report
confidence intervals/sample sizes. No production mutation required.

**Acceptance.** A single offline command emits machine-readable metrics and
threshold failures; every metric names denominator and dataset version; Chinese
publisher/origin errors are represented; report claims with market cap, import/
export, policy or forecasts fail when currency/date/source is missing; live
evaluation is opt-in and never silently mixed with deterministic CI.

## Deliberate non-proposals

- Do not rewrite SQLite/FastAPI/React or copy an open-source dashboard. Current
  boundaries support the selected product; evidence does not justify migration.
- Do not remove Tk until the user completes a fresh Windows shortcut/app-mode/
  close acceptance pass. Duplication alone is not enough.
- Do not add email, cloud deployment, vector search, Neo4j or fixed source/entity
  quotas. None solves the observed correctness and evidence gaps.
- Do not split large Python files solely by line count. Extract boundaries only
  where a selected proposal creates a concrete owner and test contract.

## Decision gate

No Round 3 proposal is approved or implemented. The user may select proposal
numbers, select all, or reject this round. Implementation starts only after the
selected scope, non-goals and acceptance tests are written into a Round 3
contract.
