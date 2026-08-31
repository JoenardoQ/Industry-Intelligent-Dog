# Self-iteration round 3 implementation contract

Approved: 2026-08-31. The user selected all proposals 1–7 from
`round-3-review.md` and expanded the final-round authority to remove proven
obsolete architecture/tests/code, erase historical industry knowledge, deliver
the Windows desktop app/shortcut, and run one fresh complete workflow.

## Outcome

Ship one coherent Windows-first IntDog application whose product surface is the
React/FastAPI workbench. It must discover and validate evidence, expose the full
reachable industry knowledge space, protect editorial decisions, produce real
research artifacts, survive/recover operational failures, and report measured
quality rather than raw volume.

## Product and architecture decisions

- React/FastAPI is the sole workbench. The historical Tk workbench and `--legacy`
  product route are obsolete and may be removed after their still-used runtime
  services are moved behind neutral owners and replacement tests pass.
- A small launcher/loading window is permitted; it is bootstrap UI, not a second
  workbench architecture.
- SQLite remains the canonical fact store. Existing JSON/Markdown artifact reads
  remain compatible where required by the current Search engine and reports.
- “Windows app” means the local Windows app-mode Chrome/Edge experience launched
  from a desktop `.lnk`, backed by the isolated runtime and localhost service. A
  standalone signed installer or Electron binary is not required.
- Default Web tasks and schedules never send email.

## Selected implementation scope

1. One truthful period pipeline supporting explicit aggregate-only and generated
   Markdown modes, provider selection, artifact registration, retryable failure
   states and idempotent successful periods.
2. A budgeted coverage executor using source-appropriate adapters/search,
   server-side URL/publisher validation, canonical source/entity yields,
   rejection evidence and stopping reasons. Client-asserted automated yields are
   forbidden; manual correction is separately audited.
3. A server-paged, searchable knowledge explorer inside Overview with chain,
   entity type, geography, status and confidence filters; entity detail,
   aliases/roles, relations, claims/evidence, sources and bounded graph expansion.
   No fixed Top-10 boundary.
4. Editorial Story constraints that survive reclustering; visual Story/document
   selection; claim support/contradiction/qualification and audit/undo semantics.
5. Web cancellation, allowlisted retry, stage/progress, parent/schedule/artifact
   links, restore preflight and visible immutable audits.
6. Concrete response/error models for current routes, generated frontend types as
   the source of truth, focused DOM/accessibility tests and repeatable browser
   workflow/zoom checks.
7. Versioned offline AI/Chips evaluation packs and metrics for retrieval,
   publisher attribution, Story clustering, entity linking, citations and
   high-risk claim provenance.
8. Long-duration evidence collection for weekly, monthly, quarterly, semiannual,
   biennial and five-year work. Evidence must be time-stratified, resumable and
   deduplicated; total count, time-bucket coverage and publisher diversity gate
   report generation. The App must expose coverage and direct collection. Email
   remains disabled and an unavailable optional provider must not make completion
   mathematically impossible.

## Authorized deletion and preservation

Authorized after reference/call/build evidence:

- the historical Tk workbench modules, route/shell/theme/page/dialog code,
  `--legacy` launcher branch, and tests whose only consumer is that removed UI;
- superseded architecture documentation and dependencies solely supporting that
  UI, after current documents are updated;
- orphaned caches, compiled bytecode, test/build intermediates, stale runtime
  logs/environments and repository-local trash;
- all historical industry knowledge and operational data under
  `DomainIntelData/`, including active industry folders, SQLite/WAL/SHM, `_trash`
  and `_jobs`, immediately before the fresh workflow.

Preserve:

- repository source/history, licence, current docs, Search/core functionality,
  Web runtime, migrations and file compatibility required by the new app;
- job/data/launcher utilities until moved and replacement tests prove parity;
- tests that still protect active Search/core/Web behavior, regardless of age;
- user credentials and external Codex/ChatGPT state; they are never copied,
  printed, deleted or placed into artifacts.

Deletion is not permission to erase `.git`, the repository root, user profile,
Windows desktop contents other than the resolved IntDog shortcut target, or any
external data.

## Fresh workflow and side effects

- After implementation and pre-reset verification, delete the exact historical
  knowledge targets above and reinitialize one AI industry from an empty store.
- Run bootstrap, daily collection, verification, coverage execution, weekly/
  monthly/quarterly generation, industry reports, one deep report, one impact
  report and Intelligence Lab. Use the locally authenticated Codex subscription
  when available; external/network/model execution is authorized for this one
  workflow. Email remains disabled.
- If authentication/network/model execution fails, preserve partial fresh output,
  record the exact terminal/checkpoint state and stop instead of fabricating a
  completed workflow.
- Build the Web production bundle/runtime, create or replace only the resolved
  `IntDog.lnk` desktop shortcut, launch it once, verify API/browser lifecycle and
  close it cleanly.

## Acceptance criteria

- Every proposal-specific acceptance criterion in `round-3-review.md` is covered
  by deterministic tests or a precisely disclosed external limitation.
- No active UI label promises Markdown when it only creates aggregation metadata.
- Failed scheduled periods are retryable without duplicate successful artifacts.
- Coverage yield is derived from validated canonical records and is auditable.
- Every active entity in a 10k fixture is reachable through search/paging; graph
  and detail responses are bounded.
- Reviewed Story constraints survive repeated clustering; conflicts stay visible.
- Web can cancel/retry allowed jobs and preview/restore without silent overwrite.
- Generated API types are consumed by the frontend; DOM/a11y and browser zoom
  workflows pass.
- Offline quality evaluation reports dataset versions, denominators and thresholds.
- Final hygiene gate proves deleted legacy material has no active consumer and
  reports any ambiguous retained compatibility surface.
- Full Python regression, type/build, OpenAPI determinism, lint/static/compile/
  diff checks, temporary-data API/browser lifecycle, Windows shortcut readback and
  fresh-workflow artifact/database integrity all pass or remain open with an exact
  classified blocker.

## Non-goals

- No email, SMTP setup or email verification.
- No cloud deployment, public server, multi-user permissions, commercial data
  subscription, signed installer or app-store packaging.
- No fixed China/foreign ratio, Top-10 knowledge boundary or claim of complete
  industry recall.
- No commit, push, force-push, release or repository publication.

## Implementation order

1. Contract/schema/test fixtures.
2. Period pipeline and coverage execution.
3. Knowledge and Story APIs/UI.
4. Operations/recovery and generated contracts/UI tests/evaluation.
5. Runtime ownership migration, legacy deletion and documentation reconciliation.
6. Full verification and final gates.
7. Historical-data reset, Windows build/shortcut/lifecycle.
8. One fresh AI end-to-end workflow and final integrity/readback.
