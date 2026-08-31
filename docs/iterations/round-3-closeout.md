# Round 3 closeout

Date: 2026-08-31

## Delivered before the destructive reset gate

- Period buttons and schedules now distinguish aggregate-only from report generation;
  only successful jobs advance a period, failures retain attempted keys and bounded retry state.
- Coverage plans can execute through a provider, validate canonical URLs and compute admitted
  source/entity yield server-side. Manual yield correction is explicit and audited.
- Overview provides bounded entity search/filter/paging plus relation and claim/evidence detail.
- Story merge/split decisions lock reviewed documents against later automatic regrouping and can
  be explicitly unlocked; the UI uses Story/document selection rather than raw identifiers.
- Job/System surfaces expose stage, progress, cancellation, safe retry ancestry, artifacts,
  schedule mode/provider, restore preflight and recent audit records.
- Core FastAPI responses have concrete Pydantic schemas; generated OpenAPI types are consumed by
  the client. Vitest/Testing Library exercises daily selection/deletion, restore preflight and job retry.
- Versioned CC0 synthetic AI/Chips fixtures gate retrieval precision, publisher attribution,
  Story pairwise quality, entity linking and high-risk citation coverage.
- Shared application runtime moved to `DomainIntelApp/runtime`; the duplicate Tk workbench and
  `--legacy` entry were removed after replacement tests passed.
- The Windows shortcut was created at the system Desktop and points to the WSL `/home` production tree.

## Verification

- Python: `126 passed` across Search, App and Web.
- DOM: `3 passed` critical workflow tests.
- Quality evaluation: AI and Chips fixtures passed every configured threshold.
- Deterministic OpenAPI export/type generation: passed.
- React production build and `git diff --check`: passed.
- Shortcut: target `C:\Windows\System32\wsl.exe`; arguments pin `Ubuntu-D` and
  `/home/joenardo/My Projects/IntDog/run_intdog.sh`.

## Post-reset workflow and long-duration evidence

- The user confirmed the exact deletion scope. Historical industry data and obsolete Tk material were
  removed; current source, docs, runtime, Git metadata and credentials were preserved. A clean AI
  workflow rebuilt sources, chain, entities, daily evidence, coverage and reports with email disabled.
- Long-duration collection now covers weekly/monthly/quarterly/semiannual/biennial/five-year horizons.
  It stores the full deduplicated corpus, samples model context across time, persists each bucket and
  blocks complete-report generation until count, time coverage and publisher diversity pass.
- Production AI five-year collection admitted 6,808 unique items across 60/61 covered monthly buckets
  and 1,435 publishers. The same corpus passes all six horizon gates: weekly 82, monthly 170,
  quarterly 395, semiannual 759, biennial 2,785 and five-year 6,808.
- Weekly/monthly/quarterly and semiannual/biennial/five-year reports were regenerated from the new
  evidence. All remain `draft_review_required`; historical collection volume does not constitute
  claim verification.
- The Research Studio displays six responsive coverage cards and direct history collection. A
  1440×1100 Chrome screenshot loaded all cards without garbling or horizontal overflow; API logs
  returned HTTP 200 for industries, research, coverage and history. The temporary server shut down
  cleanly.

## Updated verification

- Focused history/App contract: 24 passed before production execution; resumable empty-bucket regression
  then increased history coverage to 6 focused tests.
- Full pre-final regression: 132 Python tests, 3 DOM tests and the React production build passed.
- Final regression and repository hygiene results are recorded in `docs/iteration-state.md`.

## Horizon-expansion review (future proposals only)

These are intentionally not implemented in this round:

1. Build expert-labelled, licence-cleared AI/Chips corpora; synthetic fixtures prove mechanics, not
   real-world recall or epistemic correctness.
2. Run multi-process scheduler, power-loss, suspend/resume and DST endurance tests on Windows/WSL.
3. Add external-identifier entity resolution and temporal corporate-control modelling before semantic
   or vector retrieval increases recall at the cost of harder-to-audit matches.
4. Add claim-level numeric provenance gates for market cap, trade and policy assertions, including
   currency, as-of date, unit and primary filing lineage.
5. Consider a signed installer only after the app-mode lifecycle is stable; Electron/Tauri would add
   release and security cost without improving the current research algorithms.

## Final necessity ledger extension

| Subject/kind | Observed consumers and contract evidence | Status | Compatibility/dynamic-discovery risk | Result/rationale | Evidence limits |
| --- | --- | --- | --- | --- | --- |
| `src/history_backfill.py` / retrieval and gates | CLI `backfill-history`, report preconditions, Web history API, production manifest and focused tests | necessary | Provider behavior is external and time-varying | Canonical owner for policies, bucket execution, resume and evaluation | GDELT/OpenAlex availability cannot be proven offline |
| GDELT, Google News RSS and OpenAlex adapters | Historical bucket executor; provider state is persisted and visible | necessary | External schemas, quotas and indexing can change | Redundant provider design prevents one optional source from making the gate impossible | Google RSS is an index; OpenAlex needs a Key at production scale |
| `/api/industries/{folder}/history` and generated schema | Research Studio status cards and runtime response validation | necessary | FastAPI generated route/type contract | Read-only status owner; avoids duplicating evaluation in React | Interactive click was contract-tested; browser harness CDP was unavailable |
| Research Studio history cards and action | User requirement for direct App control and six-horizon visibility | necessary | Responsive/browser rendering | Shows count, time buckets and publishers; direct action uses canonical Job Manager | Visual evidence covers 1440×1100, not every OS scaling setting |
| Full-corpus report injection | Six report generators and regenerated production artifacts | candidate simplify | Prompt/provider behavior is dynamic | Full storage plus at-most-500 time-stratified context is simpler and bounded | Relevance ranking remains lexical/metadata based |
| Legacy Tk workbench and obsolete tests | No active consumer after Web/runtime migration; replacement tests/build/lifecycle passed | candidate remove | Historical external imports were not found | Removed under explicit deletion authority earlier in Round 3 | External unpublished consumers cannot be observed |

## Final gates

- Hygiene: entry points, generated contracts, dependencies, tests, runtime and affected docs were
  re-inventoried. No new sufficiently proven dead code remained after the authorized Tk/data cleanup.
  `feedparser` was already an installed crawler dependency; no dependency was added for history.
- Verification: 134 Python tests, 3 DOM tests, production React build, OpenAPI regeneration,
  compileall, repository AST checks and whitespace checks passed. Production readback and
  six horizon gates passed; the temporary local server stopped cleanly.
- Horizon expansion: the expert corpus, endurance, external-identifier, numeric-provenance and
  signed-installer proposals above remain future ideas only. None was implemented or authorized
  as a new round.
- Round 3 is closed. Email, commit, push, deployment and credential changes were not performed.
