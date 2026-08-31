# Self-iteration round 1 closeout

Closed: 2026-08-31. The user selected proposals 1–5 from
`round-1-review.md`. All implementation and verification in this round used
temporary fixtures or deterministic local tests. Production industry data,
authenticated models, live crawling, email, commit, push and deployment were not
used.

## Delivered decisions

1. Daily Intelligence now uses bounded server-side pagination (50 default, 100
   maximum), query/category filtering, global title/category/source ordering and
   an opaque continuation cursor. React only renders loaded pages and calls the
   bulk action “select loaded”; deletion receives exact row identities.
2. Schema 11 persists Story, StoryDocument and StoryReview records. Story identity
   survives overlapping reclusters; manual merge/split is audited. Automatic
   bilingual merging now requires a shared canonical entity, shared structured
   event key and a two-day window. Entity plus time alone was rejected as unsafe.
3. Structured source adapters normalize `fresh`, `stale`, `degraded`, `manual`,
   `unconfigured` and `failed`. Health, retry, last-success/last-good and bounded
   backoff persist. Feed failure cannot become an empty successful collection;
   timeout, HTTP 403 and malformed-feed paths are injected in tests. Source cards
   expose state and last-check/last-good timestamps.
4. FastAPI ownership is split across Daily, Sources, Industries, Content,
   Operations and System routers. React ownership is split into seven lazy feature
   pages with local loading/empty/error/content behavior. The checked OpenAPI file
   reproducibly generates the TypeScript path/request contract; response route
   families also receive dependency-free runtime shape checks. No feature payload
   uses `any`.
5. The default launcher now holds the same single-instance lock for Web and legacy
   modes. Windows app-mode selection covers standard and x86 Chrome and Edge paths.
   A real temporary Uvicorn instance served and navigated all seven destinations;
   shutdown returned 202 and the service exited well inside five seconds.

Tk was deliberately retained behind `--legacy`. Automated Web parity passed, but
the approved removal gate also requires explicit user visual acceptance and a
fresh end-to-end shortcut run on the user's Windows desktop. Keeping rollback is
the correct gated result; it is not evidence for permanent dual UI ownership.

## Measured evidence

- Full suite: 241 passed, 758 subtests passed in 38.35 seconds.
- Timestamp-sensitive research-agenda deduplication passed five consecutive
  focused runs after volatile persistence timestamps were removed from the input
  hash.
- 10,000-document benchmark: 50 rows returned, median 18.253 ms, p95 19.123 ms,
  insertion 0.703 seconds, continuation cursor present.
- Bilingual clustering fixture v1: 12 synthetic records, 6 predicted pairs,
  6 truth pairs, precision 1.00 and recall 1.00.
- OpenAPI SHA-256 was stable across consecutive exports:
  `ccd31ad47d0773a76b459e041cf6f63909e1cee609b7a62f64529a582d1f0d76`.
  Generated TypeScript SHA-256 was stable:
  `ce8622edffd42fd6125b0e747eaf684a04a941efa421d2e663d92d89b0100603`.
- Vite/TypeScript production build emitted seven separate feature chunks.
- Repository checker inspected 116 Python files; compileall, `git diff --check`
  and the production frontend build passed.
- Temporary browser smoke reached Overview, Daily, Products, Sources, Research,
  Jobs and System. Daily sorting/current-page selection and the manual-source form
  were exercised. The Browser Use recording contains five frames at
  `~/.config/browser-harness/agent-workspace/recordings/intdog-round1-seven-pages`.

## Limits carried forward honestly

- The clustering corpus is a small synthetic regression set, not a claim about
  production-language recall. Conservative missing-event-key cases remain
  separate for review.
- The continuation token currently encapsulates an offset; it is opaque and fast,
  but concurrent insertions can shift a long pagination session. Snapshot/keyset
  semantics are a future scale option, not silently implied.
- Primary API collectors still have dedicated implementations even though they
  share normalized adapter/health contracts. Adapter rollout remains incremental.
- Current OpenAPI response bodies are broad objects, so explicit frontend payload
  types plus runtime route validators carry more response detail than generated
  schema components. Rich Pydantic response models remain a possible later change.
- The existing production app on port 8765 was not stopped. Shortcut script,
  launcher selection/lock and service close were verified separately against
  temporary data; a fresh-machine desktop lifecycle matrix was not claimed.
