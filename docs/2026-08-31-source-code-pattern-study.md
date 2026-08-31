# Source-code pattern study

Checked: 2026-08-31. Repositories were read from public GitHub sources and minimal
temporary shallow clones. Nothing was installed, executed, copied into IntDog, or
written into production data.

## Taranis AI: closest workflow reference

### Verified implementation

- `NewsItem` stores collected and published time separately, links to a configured
  OSINT source, validates incoming payloads, and uses a unique hash to reject exact
  repeats.
- `Story` groups multiple news items, owns analyst-facing summary/relevance/read/
  important state, supports revisions, tags, votes, bookmarks, links, and report
  membership. This is materially better than treating each URL as an isolated fact.
- The queue manager separates collector, bot, presenter, publisher, connector, and
  miscellaneous queues. Cron definitions live separately from task instances; a
  leader lock prevents multiple schedulers from acting as leader.
- Task APIs distinguish queued/running/success/failure/not-found and attach worker
  metadata. User-triggered jobs can be prioritized.
- Health checks distinguish database, seed data, broker, and workers, and return 503
  when a required dependency is down.
- Its realtime redesign correctly defines events as lossy invalidation hints. REST
  and the database remain authoritative; missed/duplicate/reordered events trigger a
  refetch. Publication failure must not roll back the domain transaction.
- Realtime audience is explicit (global/organization/user), payloads contain opaque
  identifiers rather than confidential entity bodies, and locks are separated from
  notification delivery.

### Weaknesses not to copy

- Exact deduplication is based primarily on title plus link, which cannot cluster
  syndicated or rewritten coverage by itself.
- Redis, RQ workers, cron process, ingress, realtime broker, database, and multiple
  services are disproportionate for IntDog's current single-user local deployment.
- A queue being reachable is not proof that tasks are advancing. IntDog must measure
  heartbeat age and stage/event age separately.

## WorldMonitor: reliability and dense monitoring

### Verified structure and tests

- Contract-first domain APIs coexist with narrow per-domain handlers.
- The repository contains dedicated implementations/tests for circuit-breaker state,
  stale ceilings, stale-while-revalidate eviction, last-good news state, digest
  deduplication, health readiness, feed validation, China-coverage projection, and
  virtual lists.
- Its architecture explicitly uses request coalescing, cache tiers, negative caching,
  stale-on-error, adaptive refresh, tab-visibility throttling, source convergence,
  and graceful zero-key operation.

### IntDog translation

- Reuse the behavior, not the platform code: per-source circuit state, bounded
  last-good artifacts, request-key coalescing, and visible fresh/stale/degraded
  status.
- Virtualize long Daily/Source/Entity lists in the web UI.
- Never let a degraded HTTP 200 overwrite a valid last-good result; “empty”,
  “unconfigured”, “failed”, and “stale” are different states.

## OpenCTI: connector and knowledge contracts

### Verified implementation model

- Connectors have explicit roles: external import, enrichment, stream, file import,
  and file export. They authenticate independently and exchange a standardized
  bundle through an API/queue boundary.
- Connector helpers own registration, scheduling, heartbeat, queue/stream listening,
  and bundle processing rather than forcing each adapter to reinvent operations.
- Entities and relations carry source linkage, confidence, and temporal information.

### Important counterexamples

- A 2026 concrete-type filtering defect allowed History/Activity records to leak into
  Work queries because a filter expanded into parent types. IntDog must never use a
  broad hierarchy expansion for concrete task/document types.
- Stream recovery with origin filters exposed first-run catch-up ambiguity. IntDog
  must make initial backfill policy explicit and persist its cursor/window decision;
  “start live now” and “replay history” cannot be implicit variants of one option.

## Folo: reading experience, not knowledge authority

- The monorepo contains desktop, mobile, SSR, CLI, and a dedicated readability
  package. Desktop uses Electron/Vite, and the product separates subscription,
  timeline, mixed-media reading, summary, translation, and discovery experiences.
- This makes Folo a strong UX reference for Daily Intelligence: calm reading pane,
  list/detail separation, read state, saved lists, and continuous navigation.
- It is an AGPL product with separate asset restrictions and relies on a feed service;
  it should not become IntDog's data or licensing foundation.

## Onyx and RAGFlow: research workflow and operational warnings

- Onyx's connector/indexing architecture separates document fetching, batch
  processing, monitoring, and completion, but public 2026 reports show indexing can
  finish while the UI remains `In Progress` when the completion monitor stalls.
- RAGFlow exposes parser/chunk/embedding/index/entity-resolution/community progress,
  but a 2026 defect allowed an earlier parser failure to be overwritten by a later
  “no chunks” success. Another reported limitation is that graph-task pause did not
  cooperatively cancel inner work.
- These are directly relevant to IntDog's stalled Task Center: terminal states must
  be monotonic, a failure cannot be overwritten by generic completion, progress and
  worker heartbeat are distinct, and cancellation must be checked inside long stages.

## Resulting IntDog contracts

### Core records

1. `Source` — publisher identity, category, authority tier, access policy, health.
2. `CollectorRun` — explicit window/cursor, source adapter, attempts, outcome.
3. `Document` — canonical URL/content identity, publisher/author, published and
   collected timestamps, immutable raw provenance.
4. `Story` — clustered coverage of one event/topic across documents.
5. `Claim` and `Evidence` — extracted assertion and supporting/contradicting sources.
6. `Entity` and `Relationship` — typed, temporal, evidence-backed knowledge.
7. `Artifact` — report/digest/graph with provider, inputs, window, status and review.
8. `JobRun` and `JobEvent` — persisted lifecycle and representative progress log.

### Task-state invariants

- Terminal states are `completed`, `partial`, `failed`, or `cancelled`; transitions
  out of a terminal state require a new attempt, never an overwrite.
- An error flag is sticky within an attempt.
- `last_heartbeat_at`, `last_progress_at`, and `updated_at` are separate.
- “Stalled” means a running attempt exceeded its stage-specific progress/heartbeat
  threshold; “idle” means no attempt is expected to run.
- Cancellation is a persisted request that every long-running stage checks.
- UI notifications are hints; the UI always refetches the authoritative job record.

### Collection invariants

- Every run stores timezone-aware `window_start`, `window_end`, window reason, and
  prior cursor/checkpoint.
- Initial backfill, scheduled incremental collection, retry, and manual refresh are
  explicit modes.
- Adapter output is normalized before storage; adapter-specific fields remain in a
  namespaced raw payload.
- Source failure produces a failure record, not an empty successful result.
- Exact URL/hash deduplication and semantic story clustering are separate operations.

## Recommended first architecture slice

Build a local typed API and new web workbench while retaining the current canonical
store until parity is proven. Add no Redis, message broker, graph server, or separate
realtime service initially:

```text
React workbench ── REST + local SSE hints ── FastAPI
                                            │
                                  local job supervisor
                                            │
                           collectors / domain services
                                            │
                              SQLite + FTS5 + artifacts
```

This retains simple one-click local operation while adopting the mature contracts.
If profiling later proves one-process supervision insufficient, the `JobRun` and
collector contracts provide a clean boundary for RQ/Celery/other workers without
redesigning the product.

## Remaining gate

The next implementation slice introduces frontend and API dependencies. Per the
self-iteration protocol, dependency/framework migration still requires explicit
approval before packages are added or installed.
