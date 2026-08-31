# Self-iteration round 2 closeout

Closed: 2026-08-31. The user selected proposals 1–7 and explicitly excluded
email push. The controlling scope is `round-2-contract.md`.

## Delivered

- The default Web app owns persisted daily/weekly/monthly/quarterly schedules,
  atomic period claims, leases, restart catch-up and run-now. Every Web-started
  job carries `INTDOG_DISABLE_EMAIL=1`; there is no email UI or email schedule.
- Daily has a Story view with typed list/detail APIs, linked evidence, timeline,
  independent-publisher counts and audited merge/split. A publisher is counted
  once even when it contributes multiple documents.
- Coverage cells and deduplicated query attempts persist their dimensions,
  priority, status, rationale, validated yields, evidence and stopping reason.
  Model-proposed candidates remain `planned` with zero yield until validated.
- Research Studio directly submits every supported collection/report/bootstrap/
  impact/Lab action. Period, industry, deep and impact artifacts share a typed,
  openable product library with provenance, limitations and visualization fields.
- Unsafe localhost requests and shutdown require a high-entropy launch session;
  Host and Origin are constrained and security headers are emitted. The SPA reads
  the capability from a URL fragment, stores it per session and removes the
  fragment from the visible address.
- System status lists and restores archived industries and deleted daily batches
  without silent overwrite. Permanent deletion is deliberately unavailable.
- Forms have programmatic labels; merge/split no longer use browser prompts;
  narrow/high-zoom layouts stack without whole-page horizontal overflow. A
  repeatable Playwright browser-smoke harness covers all seven destinations.

## Verification evidence

- Focused Round 2 API, persistence, security, scheduler, coverage, recovery and
  frontend contract tests passed.
- Full offline Python regression: 253 tests and 758 subtests passed.
- OpenAPI JSON and generated TypeScript were deterministic across repeated
  exports; Vite/TypeScript production build passed.
- Repository AST/duplicate-definition check covered 118 Python files;
  `compileall` and `git diff --check` passed.
- A temporary-data Uvicorn lifecycle returned 200 for core reads and all seven
  SPA routes; missing session returned 401, foreign Origin 403, valid writes
  succeeded, shutdown returned 202 and the process exited cleanly.
- Windows headless Chrome exercised all seven pages, Story, coverage and the four
  schedule cards. At a 720 CSS-pixel narrow viewport the document had no
  page-wide horizontal overflow. Evidence screenshots:
  `/mnt/c/Users/Joena/AppData/Local/Temp/intdog-round2-system.png` and
  `/mnt/c/Users/Joena/AppData/Local/Temp/intdog-round2-research-zoom.png`.

## Honest limits

- No live crawl, model call, email, production-data write, commit, push or deploy
  was performed. Source recall, Story recall and real query yield remain unknown.
- The coverage planner exposes an evidence-seeking frontier; it does not establish
  that an industry is complete. Planned queries do not count as discoveries.
- Scheduler tests use fake clocks and a temporary service. Long sleep, DST, power
  resume and two sustained OS processes have not been tested end to end.
- Headless Chrome over temporary Uvicorn is not a user-approved Windows shortcut
  or app-mode lifecycle pass. Tk remains available only as `--legacy`.
- Restore is collision-safe but has no detailed preflight preview, rename-on-
  restore or permanent-delete workflow.
- Accessibility evidence covers labels, keyboard-oriented controls, responsive
  contracts and browser smoke; it is not a screen-reader or automated axe audit.
