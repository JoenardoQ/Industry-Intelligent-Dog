# IIOS Workbench Baseline — 2026-08-30

## Outcome

IntDog must be a runnable industry-research workbench whose overview, monitoring,
reports, research tools, and operations surfaces share one auditable data model.
This baseline is mandatory work and does not consume any of the three requested
optimization rounds.

## Product contract

### Industry overview

- Make Overview the home of the knowledge structure; remove the duplicate
  standalone Knowledge navigation destination once parity is verified.
- Show source, document, entity, and relationship totals as interactive cards.
  Sources navigate to Sources; documents navigate to Daily Intelligence; entities
  and relationships focus the corresponding knowledge sections on Overview.
- Show the ordered value chain, entity coverage, and supporting evidence without
  implying that row count equals research completeness.

### Daily intelligence

- The canonical collection window is previous local day at 04:00 through the
  current system time. Store `window_start`, `window_end`, and timezone with the
  collection result.
- Default ordering is normalized title ascending. Users can sort by title,
  category, or displayed source.
- `display_source` is category-aware: news publication, GitHub owner/developer,
  paper author list, or self-media publisher/account. Unknown values are visibly
  `N/A`, never inferred from an unrelated field.
- Filtering, multi-select, select-all-visible, and recoverable deletion remain.

### Periodic products

- Weekly, monthly, and quarterly generation are three parallel actions, not a
  dropdown.
- If a successful prior crawl exists and its elapsed age is at least one cycle,
  use `[last_success, last_success + cycle]`. Otherwise use
  `[now - cycle, now]`. Persist the selected window and decision reason.
- The reader renders Markdown as structured rich text with headings, lists,
  links, code, and tables. An external renderer may replace it only after a
  license, maintenance, packaging, and offline-runtime review and explicit
  dependency approval.

### Reports, Research Assistant, and Intelligence Lab

- Industry reports include a directed value-chain graph. Nodes are ordered by
  upstream/midstream/downstream position and arrows express direction.
- Research Assistant and Intelligence Lab use the same generate/read/evidence/
  visualization interaction model and expose provenance and limitations.

### Sources and entities

- Expand source categories to cover primary institutions, regulators/statistics,
  standards/associations, company disclosures, journals, established media,
  specialist platforms, developer communities, and representative self-media.
- Each category targets 3–5 authoritative, well-known, representative sources;
  this is a quality target, not permission to fabricate or pad a category.
- Entity coverage spans all chain stages and entity types, while each entity must
  retain roles, geography, evidence, relationships, strengths, risks, trade
  exposure where supported, and time-sensitive market facts with as-of dates.

### Operations and logging

- Task Center and System Status must refresh without blocking the browser UI,
  tolerate incomplete/corrupt job records, and distinguish idle from stalled.
- Long-running tasks print a small set of representative stage transitions,
  progress counts, warnings, artifact paths, and terminal status. Logs must not
  expose credentials or flood the UI with every low-level record.
- Startup, empty-data operation, local dry runs, and the automated suites must be
  runnable without changing production industry data.

## Architecture constraints

- Tkinter, SQLite, and the existing search pipeline are implementation history,
  not mandatory constraints. A component or layer is retained only when its
  contracts, tests, and migration cost make retention better than replacement.
- Before restructuring, compare mature open-source products and components for
  product fit, license compatibility, activity, packaging, offline use, Chinese
  typography, accessibility, and operational complexity. Learning from a project
  does not authorize copying its code or visual identity.
- During migration there remains exactly one canonical query surface; compatibility
  JSON/Markdown files are artifacts, not competing sources of truth.
- Time windows are computed in one shared module and passed explicitly to
  crawlers/generators. UI code does not recreate scheduling rules.
- UI presentation helpers normalize labels and source attribution without
  mutating persisted records.
- The production deliverable remains a desktop application. On the current WSL
  deployment, the shortcut owns a loading window, local-only API process, and a
  dedicated Chrome app-mode window without browser chrome; closing that window
  stops the local service. React is the view implementation, not a requirement
  for users to operate IntDog as a browser tab. A packaged Tauri/Electron shell
  remains an evidence-driven later option rather than a baseline dependency.
- New dependencies and any framework migration require a separate approval gate.
  Network/model execution and
  production-data mutation require separate execution approval.

## Round 1 selected contract

The user selected all five proposals in `docs/iterations/round-1-review.md`.
They are one dependency-ordered change set, not permission to begin Round 2.

1. Daily intelligence uses bounded server-side pagination and filtering. The
   client renders only loaded pages and labels selection scope exactly; deletion
   never silently expands from loaded rows to all matching rows.
2. Story is a persistent, versioned domain record linked to documents and
   publisher clusters. Exact duplicate detection, event clustering, and claim
   corroboration remain separate decisions. Automatic merge precision is
   evaluated on a labeled bilingual fixture; recall and corpus limits are
   reported. Manual merge/split writes an audit record.
3. Source collection uses an explicit adapter registry and normalized result
   states: `fresh`, `stale`, `degraded`, `manual`, `unconfigured`, or `failed`.
   A failed collection is never stored as an empty success. Retry state,
   last-success/last-good timestamps, bounded backoff, and safe errors persist.
4. FastAPI feature routers and React feature slices replace monolithic ownership.
   The checked OpenAPI document generates the TypeScript contract reproducibly;
   feature payloads do not use `any`, and each destination owns loading, empty,
   error, and content behavior.
5. The default desktop path must prove shortcut/loading/window/close and
   single-instance behavior on Windows/WSL. The historical Tk rollback route was
   removed after the Round 3 replacement and interaction tests passed.

Round 1 verification uses temporary data roots only: 10,000-document pagination
benchmark, Story clustering corpus and review audit tests, injected adapter
failure/backoff tests, OpenAPI generation/build checks, all Python suites, and
desktop lifecycle/interaction smoke where the current host supports them.

Round 1 closed on 2026-08-31; implementation evidence, measured results,
limitations and the gated decision to retain `--legacy` are recorded in
`docs/iterations/round-1-closeout.md`.

## Verification gates

1. Unit tests for time-window boundaries, source attribution, ordering, directed
   chain order, navigation, and non-blocking job/status refresh.
2. App and Search test suites, compile checks, repository checker, and
   `git diff --check`.
3. Launch smoke test with a temporary data root, followed by visual review of
   Overview, Daily, Periodic, Reports, Research, Lab, Task Center, and System.
4. Only after explicit approval: one real industry crawl/model workflow and
   production artifact review.

## Iteration lifecycle

- Baseline: implement and verify everything above.
- Rounds 1–3: read the review matrix immediately before each round, audit the
  complete system, present every qualifying optional proposal, and wait for the
  user's selection before implementing that round.
- Round 3 additionally follows the final-round closeout protocol.
