# Self-iteration round 2 comprehensive review

Reviewed: 2026-08-31. This is a review and proposal gate, not an implementation
claim. Round 1 is closed in `round-1-closeout.md`. No production data, live
crawl, authenticated model, email, commit, push or deployment was used during
this review.

## Scope and current evidence

The review covers the default React/FastAPI desktop path, the retained Tk legacy
path, collection and source discovery, persistent storage, Story clustering,
reports and research, task execution, recovery, security, accessibility, tests
and documentation. Evidence consists of repository consumers, the 241-test /
758-subtest Round 1 result, the 10,000-row pagination benchmark, the temporary
seven-page browser run and fresh static tracing of the current source tree.

The central finding is architectural: the default Web workbench is usable as an
interactive client, but it does not yet own the complete long-running product.
Scheduling remains in the legacy Tk controller, persistent Stories are not
exposed to Web users, and several already-implemented research actions have no
Web workflow. Retiring Tk now would therefore remove capabilities rather than
complete a migration.

## Necessity ledger

| Subject/kind | Observed consumers and contract evidence | Status | Compatibility/dynamic-discovery risk | Result/rationale | Evidence limits |
|---|---|---|---|---|---|
| React/FastAPI default shell | Desktop launcher, seven lazy routes, README default launch contract | necessary | High if route or launcher contracts move | Keep; it is now the primary interaction boundary | One temporary Linux/Chromium lifecycle, not a fresh Windows shortcut run |
| Tk legacy client | `--legacy`; only current owner of periodic scheduling and several richer generation dialogs | necessary | High until parity and visual acceptance gates close | Keep temporarily; do not mistake duplication for safe removal | No current user visual acceptance of the Web replacement |
| SQLite repository and migrations | All industry, document, Story, job and audit persistence | necessary | Very high; durable user data | Keep transactional canonical core | Repository module remains large and mixed in responsibility |
| File artifact compatibility layer | Existing Markdown/JSON products, MCP and readers consume paths | necessary | High for historical data and external readers | Keep compatibility reads; converge new writes behind typed artifact metadata | External consumer inventory is incomplete |
| Server-side daily pagination | Daily page and bulk selection; 10k benchmark p95 19.123 ms | necessary | Low while cursor remains opaque | Keep; current performance is adequate | Offset-backed cursor can shift under concurrent inserts |
| Persistent Story tables and audits | Repository and tests only; no Web/API consumer | candidate simplify | Medium; premature deletion would discard Round 1 foundation | Expose and evaluate before expanding clustering internals | Synthetic 12-record fixture is not production recall evidence |
| Automatic bilingual clustering rule | Story builder/tests require entity + event key + two-day window | necessary | High if relaxed: false corroboration | Keep conservative rule and surface unresolved candidates to review | No labelled real bilingual corpus yet |
| Explicit source adapters and health | Crawlers, scheduler, source cards, failure injection tests | necessary | Medium; collector-specific paths still coexist | Keep contract and migrate collectors incrementally | Three representative sources/class, not an exhaustive live matrix |
| Dedicated primary API collectors | Academic/news/periodic modules still own provider behavior | candidate merge | High if bulk-rewritten; rate-limit/auth semantics differ | Merge only behind adapter conformance tests, not as a cosmetic rewrite | Live authenticated provider behavior unassessed |
| Source-discovery hard-coded seeds | Bootstrap fallback and initial coverage | necessary | Medium; useful offline safety but risks anchoring | Retain only as transparent fallback, not as coverage proof | Seed freshness and regional recall are not measured |
| LLM source-map prompt and count gates | Bootstrap asks roughly 45 sources and 3–8/category | candidate simplify | High epistemic risk if counts imply completeness | Replace count-led success with an evidence-led coverage frontier | Model/search runs were not authorized in this review |
| Periodic scheduler in Tk | `_start_scheduler`/`_scheduler_tick`; daily/weekly/monthly/quarterly controls | candidate merge | Very high: duplicate owners can double-send | Move durable ownership into one default service, then remove Tk ownership | Restart, clock skew and multi-instance behavior lack end-to-end evidence |
| CLI `PeriodicScheduler` execution | CLI generation/crawl commands and report generation | necessary | Medium | Reuse execution semantics under a durable scheduler rather than duplicate them | It is an executor, not a continuously running owner |
| Persistent JobManager | Web job routes, heartbeat/progress/cancel/shutdown tests | necessary | Medium | Extend for scheduled ownership and recovery | Cross-process lease/failover behavior unassessed |
| Products periodic buttons | Weekly/monthly/quarterly generation in Web | necessary | Low | Keep, but unify with the wider artifact-generation contract | Current browser smoke did not execute a model job |
| Report/deep/impact/bootstrap backend actions | Generate route and CLI implement actions | necessary | Medium; request shapes currently broad | Expose them in a coherent Research Studio instead of hidden capability | Live provider execution remains gated |
| Research Lab | Research page, agenda/tasks/scenario artifacts and tests | necessary | Medium | Keep; connect outputs to evidence and Story timelines | Scientific usefulness has not been evaluated with domain experts |
| Overview knowledge/value-chain graph | Overview metrics, directed graph and artifact readers | necessary | Low | Keep and add real entity/relationship drill-down | Entity/relationship metric links currently return to Overview itself |
| Industry archive and deleted-document trash | Service moves data into `_trash` | necessary | High for user trust | Keep recoverable deletion and add list/restore workflows | Collision, retention and restore UX not tested end-to-end |
| Local shutdown endpoint | Launcher and lifecycle smoke call bodyless POST | necessary | Medium compatibility; high local DoS exposure | Protect with a launch-scoped capability and Host/Origin checks | Threat was established by route shape/static review, not exploitation |
| Generated OpenAPI path/request types | API export, generated TS, deterministic hash/build tests | necessary | Medium | Keep generation; add response models so schema is authoritative both ways | Responses remain broad dictionaries today |
| Hand-authored frontend response types/validators | `api.ts` guards feature payloads | necessary | Medium until generated response schemas exist | Retain during migration, then reduce duplicate schema ownership | Validators are shallow and do not replace behavioral tests |
| Python contract/static frontend tests | Full suite catches routes, strings, source contracts | necessary | Low | Keep as fast regression layer | Cannot establish DOM interaction or accessibility semantics |
| Browser smoke harness | Seven-page navigation and lifecycle evidence | necessary | Medium tooling/environment fragility | Keep as release evidence, not the only UI test | One viewport/browser; no screen-reader or zoom matrix |
| Email, MCP, read-only serve and agent protocols | CLI/docs/tests expose optional integration surfaces | unassessed | Potentially high for external users | Do not remove or redesign without connected-client inventory | No live SMTP or connected MCP/client evidence in this round |
| Monolithic repository/module boundaries | `repository.py` remains about 1.3k lines; several orchestration modules are large | candidate simplify | Medium refactor risk and low immediate user value | Defer broad splitting; extract only when a selected feature needs a boundary | Line count is a smell, not proof of a defect |
| Keyset/snapshot pagination | No current consumer; 10k offset benchmark is fast | candidate remove | Low today, future correctness risk under high write concurrency | Do not build this round unless measured concurrent-session failures emerge | Concurrent insertion behavior has not been benchmarked |

## Coverage ledger

| Dimension | Evidence | Status | Result | Limits |
|---|---|---|---|---|
| Correctness | 241 tests; time-window, clustering, adapter and lifecycle checks | Finding | Default Web lacks continuous scheduling and several Web workflows; those are functional gaps | No live full workflow in this review |
| Security and privacy | Localhost bind; no CORS, Host/Origin or launch-capability enforcement; bodyless shutdown POST | Finding | Add local-session authorization before treating the localhost API as a trusted desktop boundary | No adversarial browser test yet; production auth model is unresolved |
| Data integrity and recovery | SQLite migrations/audits plus recoverable filesystem moves | Finding | Destructive actions are recoverable internally, but users cannot inspect or restore trash in Web | Restore collision/partial-failure behavior untested |
| Performance and scale | 10k documents, page 50, median 18.253 ms, p95 19.123 ms | no change justified | Pagination is adequate; do not spend this round on keyset complexity | Does not cover million-row or concurrent-write workloads |
| Reliability and operations | Durable jobs and clean shutdown exist; scheduling owner does not | Finding | One scheduler owner needs leases, checkpoints, catch-up and visible status | Sleep/resume/clock-change matrix absent |
| Architecture and maintainability | Typed routers/features exist; repository and compatibility paths remain mixed | Finding | Make selected product contracts authoritative before broad code splitting | Static dependency graph only; no change-frequency history |
| UX and information architecture | Modern shell and seven routes; hidden backend actions, dead-end metric links, no Story/recovery UI | Finding | The workbench still exposes storage categories more than research workflows | User visual acceptance and usability study pending |
| Accessibility and visual density | Larger typography landed; placeholder-only forms and no focus/zoom/reader matrix | Finding | Add semantic labels, focus behavior and component-level checks | No assistive-technology session performed |
| API and schema quality | OpenAPI generation is deterministic; response bodies are broad objects | Finding | Define Pydantic response models and generate both request and response contracts | External API compatibility consumers unassessed |
| Source credibility | Source tiers, selection reasons, health and primary-source preference exist | Finding | Credibility metadata is present, but count gates cannot establish source completeness | No current live source re-audit |
| Breadth and open-world recall | Categories and seeds exist; no persisted coverage frontier or saturation ledger | Finding | Coverage must be measured across region, chain, entity, source and event dimensions | True open-world recall has no knowable denominator |
| China/foreign balance | Prior data had China 2 vs foreign 66; user prefers more native Chinese coverage without a hard ratio | Finding | Optimize marginal native-source coverage and disclose imbalance; do not game a fixed ratio | Old measured dataset may not represent new runs |
| Entity and value-chain depth | Directed nodes/entities exist; prior bootstrap left four stages uncovered | Finding | Deepen by uncovered chain endpoint and entity type, not a global “Top 10” quota | No newly authorized bootstrap data |
| Story corroboration and uncertainty | Conservative clusters/audits exist; prior production claims had zero multi-publisher confirmation | Finding | Make corroboration, conflict and missing evidence first-class review objects | Historical data predates the new Story workflow |
| Research/report provenance | Draft status, claims, references, provider/model metadata and visualizations exist | Finding | Unify generation and evidence viewing; do not present drafts as verified conclusions | Domain-expert evaluation absent |
| Internationalization | Chinese/English text and bilingual clustering fixture exist | Finding | UI/source attribution must preserve native publisher/author names and bilingual evidence | RTL and languages beyond Chinese/English not in scope |
| Observability | Jobs expose logs/heartbeat/progress | Finding | Scheduled run state, next run, last success, skipped/catch-up reason remain absent | No long-duration telemetry run |
| Deployment and portability | Local launchers and temporary Linux lifecycle passed | Finding | Fresh Windows shortcut/app-mode/close verification remains a retirement gate | macOS and packaged distribution not claimed |
| Documentation fidelity | Round 1 closeout and implementation status reflect current gates | no change justified | Keep docs-first reconciliation per selected round | Older design-history documents intentionally retain historical plans |
| Legal/licensing/supply chain | Own code, standard dependencies, OSS patterns studied without copying | no change justified | No wholesale fork is justified; continue dependency/license review when adding packages | No automated SBOM or vulnerability scan yet |
| Email/MCP/external clients | Unit/docs coverage only | unassessed | Preserve compatibility and defer claims | Requires explicit credentials/connected-client authorization |

## Three-pass synthesis

### Pass 1 — contract and reachability

The code contains more capability than the default app exposes. Periodic
execution, deep reports, impact analysis and bootstrap are real backend paths,
but several are reachable only through CLI or legacy Tk. Stories are persisted
but not consumable through the Web API. Conversely, Overview shows entity and
relationship counts as links without a destination that can explain those
objects. The first priority is therefore to finish product contracts, not add
more disconnected features.

### Pass 2 — failure, trust and long-running behavior

A durable intelligence system must survive restart, missed schedules, source
failure and user mistakes. Source health and jobs now have useful foundations,
but the scheduler is tied to a UI process, recovery is hidden, and localhost
mutations rely on network location rather than a session boundary. These are
trust defects. A prettier interface cannot compensate for duplicate delivery,
silent missed runs, unrecoverable-looking deletion or an unprotected shutdown
route.

### Pass 3 — epistemic breadth and research value

The stated goal is an expanding map of an industry, not answers to a fixed list
of questions. A prompt requesting a number of sources and per-category quotas is
not evidence of comprehensiveness. The system needs a persisted coverage
frontier, explicit gaps and marginal-yield stopping reasons. Story-level
corroboration then turns collected documents into reviewable evidence. This is
more important than increasing raw source counts or generating longer prose.

## Correctness and security defects independent of proposal preference

- The README's default-app periodic-update expectation is not satisfied by the
  default Web runtime. Continuous scheduling remains owned by legacy Tk.
- `/api/shutdown` accepts a bodyless POST without a launch-scoped capability,
  Host validation or Origin validation. A local-only bind reduces exposure but
  does not by itself prevent a hostile web page from attempting localhost denial
  of service.
- Web entity and relationship metric “links” do not provide entity/relationship
  drill-down; they navigate back to their current Overview context.
- Archive/delete actions are internally recoverable but the default Web client
  offers no recovery workflow, so the user-facing contract is incomplete.

## Qualifying proposals

### 1. P0 — make automation a durable default-Web service

**Evidence.** Tk owns `_start_scheduler`/`_scheduler_tick`; FastAPI starts jobs
but no continuous scheduler. The CLI scheduler executes work but is not a durable
owner.

**Change and benefit.** Add a single scheduler service with persisted schedules,
leases, last-success/next-run state, exactly-once period keys, missed-run/catch-up
rules and visible Web controls. Reuse current daily and periodic window logic and
JobManager execution. Disable legacy ownership when the Web scheduler is active.
This completes the long-running daily/weekly/monthly/quarterly and email product
contract.

**Cost/risk/dependencies.** High effort, high operational value. Depends on job
idempotency and explicit local-time/DST rules. Reversible behind a scheduler-owner
configuration flag; legacy manual commands remain compatible.

**Acceptance.** Fake-clock tests cover daily, weekly, monthly and quarterly due
times; restart catches up each period at most once; two app instances cannot
double-enqueue; next/last/error state is visible; email is sent only after a
successful artifact; shutdown completes within five seconds.

### 2. P0 — expose Story-centric evidence and editorial review

**Evidence.** Story persistence, links, audits and merge/split exist only below
the API. Daily still presents raw documents, hiding corroboration and conflict.

**Change and benefit.** Add typed Story list/detail/review endpoints and a Daily
Story/document toggle. Show timeline, publisher clusters, native source/author,
claims, conflicts, missing evidence and bilingual documents. Expose audited
merge/split without allowing a single publisher to count as corroboration.

**Cost/risk/dependencies.** Medium-high effort. Main risk is overstating cluster
quality; default to conservative automatic merges and explicit review. Existing
document view remains a reversible fallback.

**Acceptance.** Stable Story identity survives reclustering; merge/split creates
audits; one publisher never satisfies independent corroboration; bilingual
fixture behavior remains stable; browser tests cover Story list/detail/review and
error/empty states.

### 3. P0 — replace quota-led discovery with an open-world coverage planner

**Evidence.** Current seeds and model prompt target source counts/categories, but
there is no persisted query plan, coverage frontier, marginal-yield history or
stopping rationale. Prior data was strongly foreign-skewed and had uncovered
chain stages.

**Change and benefit.** Persist discovery hypotheses and queries across region ×
subdomain × value-chain endpoint × entity type × source type × event type × time.
Rank gaps by research value and source credibility, expand native Chinese primary
and authoritative/self-media leads where evidence is missing, record marginal
new-source/entity yield and stop only with an explicit reason. Keep authoritative
seeds as fallback, never as completeness proof. Avoid fixed Top-10 or preset
question boundaries.

**Cost/risk/dependencies.** High effort and highest methodological value. Search
and model variability require deterministic fixtures plus later explicitly
approved live evaluation. Planner state is additive and can be disabled without
changing existing artifacts.

**Acceptance.** Deterministic fixture produces a deduplicated query ledger and
visible uncovered cells; every admitted URL has provenance/validation; gap and
marginal-yield metrics persist; native-Chinese and primary-source coverage are
reported without enforcing an artificial ratio; uncovered chain/entity types
drive the next queries; stopping reasons are auditable.

### 4. P1 — create one typed Research Studio and artifact contract

**Evidence.** Backend actions support bootstrap, report, deep report and impact;
Web Products exposes only three period buttons and Research mostly exposes Lab.
OpenAPI responses remain broad dictionaries.

**Change and benefit.** Build one direct-generation workflow for period reports,
industry reports, deep research, impact analysis, bootstrap and Lab. Define typed
Pydantic request/response/artifact schemas, generated frontend response types,
provenance, status, evidence, limitations and visualization links. Generated
artifacts appear immediately in a shared library and reader.

**Cost/risk/dependencies.** Medium-high effort. Depends on stable artifact
identity and job result schemas. Preserve existing files and CLI commands through
compatibility adapters.

**Acceptance.** Every existing backend action is reachable and validated in Web;
job progress/failure is visible; successful artifacts appear and open with
citations/limitations/visualization; OpenAPI includes concrete response schemas;
browser tests exercise each non-model submission flow with deterministic fakes.

### 5. P0 — harden the localhost desktop trust boundary

**Evidence.** The server is localhost-only, but shutdown has no session
capability, Host check or Origin check; route responses are readable only under
browser policy, while a hostile page can still attempt write-only local actions.

**Change and benefit.** Generate a launcher-scoped random capability, pass it to
the app-mode client without persisting secrets, validate it on mutations and
shutdown, restrict Host/Origin, and add a restrictive CSP. Keep read-only health
available only if needed for startup. This prevents ambient browser access from
being treated as desktop authority.

**Cost/risk/dependencies.** Medium effort, compatibility-sensitive. External
MCP/read-only clients must not be silently broken; protect desktop routes at a
separate boundary. Reversible via a development-only flag, not production
default.

**Acceptance.** Correct session can mutate and close; absent/wrong capability,
foreign Origin and invalid Host are denied; malicious-origin regression cannot
trigger shutdown; token is redacted from logs; launcher lifecycle remains under
five seconds.

### 6. P1 — complete recovery and retention workflows

**Evidence.** Industries and documents move to `_trash`, but Web cannot list or
restore them.

**Change and benefit.** Add typed trash inventory, restore, collision preview,
retention and permanent-delete confirmation with audit entries. Provide industry
and Daily recovery views and optional export-before-delete.

**Cost/risk/dependencies.** Medium effort. Filesystem/SQLite partial failure is
the main risk; use transactions or compensating operations. Existing trash layout
remains readable.

**Acceptance.** Archive/delete/restore round-trips preserve identities and
artifacts; collisions never overwrite silently; interrupted restore is either
rolled back or explicitly repairable; permanent deletion requires exact target
confirmation; browser and filesystem tests cover both object classes.

### 7. P1 — establish accessible component-level UI verification

**Evidence.** Several forms rely on placeholders; current Python static tests and
one browser smoke do not verify focus, keyboard behavior, semantics or zoom.

**Change and benefit.** Add semantic labels/descriptions, consistent modern form
and select components, dialog focus management, keyboard operation and readable
line height. Introduce a small React component/integration test layer plus
automated accessibility checks; verify 125%, 150% and 200% zoom for dense lists,
long text and menus.

**Cost/risk/dependencies.** Medium effort, low data risk. Adds focused frontend
test dependencies; visual changes remain token-driven and reversible.

**Acceptance.** Core forms have programmatic labels; navigation/actions work by
keyboard; dialogs trap and restore focus; no critical automated accessibility
violations on seven routes; primary workflows remain usable without horizontal
page overflow at 200% zoom; Daily rows and menus preserve readable spacing.

## Deliberate non-proposals

- A wholesale repository rewrite is not justified. Large modules should be split
  only along a selected product boundary; line count alone is weak evidence.
- Keyset pagination is not justified this round. Current measured performance is
  strong, and concurrent-insert session drift has not produced a user defect.
- Replacing SQLite, React or FastAPI has no current evidence-based benefit.
- Adding more sources by quota is explicitly rejected as a completeness metric.

## Decision gate

No Round 2 proposal has been approved or implemented. The user may select any
proposal numbers, select all, or reject the round. After selection, the chosen
contracts and acceptance tests must be written into the active baseline before
source implementation begins.
