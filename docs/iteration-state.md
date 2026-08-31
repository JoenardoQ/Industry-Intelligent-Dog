# IntDog Iteration State

- Lifecycle phase: BASELINE
- Execution status: ACTIVE — unsigned test-release path selected; commit/push pending authorization
- Current round: 3 of 3
- Current baseline: IntDog 4.0 user-facing release readiness; no new optimization round authorized
- Release contract: `docs/release-readiness.zh-CN.md` / `docs/release-readiness.md`
- Scope change: final artifacts must support Windows, macOS, and Linux natively.
- Decision: approved Electron + one PyInstaller API/CLI sidecar + electron-builder;
  one installer, Issue, build job and Release per platform. Shared architecture
  changes invalidate and rerun all three platform gates.
- Platform release tracking: Windows Issue #1, macOS Issue #2, Linux Issue #3.
- Native evidence: Linux x64 sidecar (17 MB) and AppImage (142,063,476 bytes) passed
  two consecutive isolated start-ready-close-reopen cycles. Overall release remains
  NOT_READY until native Windows and macOS gates pass.
- Release channel: `4.0.0-test.1` unsigned GitHub Pre-release. Signing Secrets are
  intentionally not inherited by the three test-release workflows. Stable Windows
  and macOS releases remain blocked until signing/notarization is configured.
- Baseline HEAD: 75e1f463af4b098e4176304c948c1a6b9b61822c
- Baseline working-tree diff SHA-256: 9b476402c2d80b2f340c4a2c664b29f0584eb82f1855983a63c1deb65b4dca68
- Data root: /home/joenardo/My Projects/IntDog/DomainIntelData
- Deletion authority: AI/, intdog.sqlite3, intdog.sqlite3-wal, intdog.sqlite3-shm, _trash/, _jobs/
- Preserve: README.md, skill/, source, docs, config, runtime, unrelated changes
- Commit/push/deploy authority: none
- Active baseline contract: `docs/2026-08-30-iios-workbench-baseline.md`
- Requested optimization rounds after baseline: 3
- Production data mutation authority for this request: executed within the user-confirmed Round 3 reset and fresh-workflow scope
- Network/model execution authority for this request: executed for one fresh complete workflow and long-history extension; email remained disabled

## Baseline

- 2026-08-31 data-governance baseline: `docs/source-governance.zh-CN.md` and
  `docs/source-governance.md` define conservative document deduplication and a
  dynamic, non-destructive source portfolio. Implementation is closed: AI keeps
  all 87 registered sources while governing 41 as active, 40 as manual, and 6 as
  reserve; two category shortages remain explicit. Historical cleanup soft-suppressed
  7 duplicate memberships from 6,813 links and retained all document rows and
  evidence. A second preview reported zero remaining eligible duplicates. Verification:
  148 Python tests, 4 Web tests, TypeScript and production build passed. Ruff was not
  available in the project environment; Python import/pytest gates passed instead.

- 2026-08-30 workbench baseline: implemented and locally verified — overview/knowledge integration,
  linked metrics, daily attribution/sorting/window rules, periodic window rules,
  three period actions, Markdown reader, directed chain visualizations,
  Research/Lab parity, source/entity depth, operations recovery, and meaningful
  task logging are specified before implementation.
- 2026-08-30 architecture constraint revised by user: Tk/SQLite/Search may be
  replaced. Open-source survey recommends a staged React web/PWA workbench over a
  typed local Python API, with no wholesale fork. The user approved the dependency
  migration; React/Vite/FastAPI/Uvicorn are installed in isolated project runtimes,
  and the legacy Tk route was removed in Round 3 after runtime ownership migration.
- 2026-08-31 open-source discovery pass: completed initial crawler/workbench/
  knowledge-system landscape in `docs/2026-08-31-github-project-landscape.md`.
  Taranis AI is the closest end-to-end analogue; source-code deep dives remain
  pending at that checkpoint. No repository had yet been cloned, no dependency
  was installed, and no code was reused.
- 2026-08-31 source-code pattern study: completed for the highest-value contracts
  and counterexamples; see `docs/2026-08-31-source-code-pattern-study.md`.
  Temporary shallow clones were used under `/tmp/intdog-oss-study`; no third-party
  project was run or installed, no source was copied, and production data is
  unchanged during study. The later React/FastAPI dependency gate was approved.

- 2026-08-31 web baseline evidence: `DomainIntelWeb` now provides the default
  desktop app-mode workbench and typed localhost API. Daily and periodic collection
  windows share `src/time_windows.py`; report metadata carries a deterministic
  directed value-chain graph; jobs persist heartbeat and progress timestamps.
  Production data was not used by tests. Full automated verification passed:
  223 tests and 758 subtests, frontend production build, compileall, and
  `git diff --check`. Real Uvicorn/API/static smoke tests returned HTTP 200 against
  `/tmp/intdog-web-smoke.p1y55p`. Headless Chrome visual review found and fixed an
  initial empty-industry fetch race and a CSS status-name collision; the final
  1440×1000 overview screenshot is
  `/mnt/c/Users/Joena/AppData/Local/Temp/intdog-baseline-final.png`.

- Shortcut: passed
- Reset: passed
- Clean AI workflow: passed_after_fix_round_2
- Automated verification: Task 8 Fix Round 4 gates passed (focused 19, App 146, Search 70, checker/compile/diff/data); independent re-review and Task 9 GUI evidence remain pending; measured AI-data quality gaps remain
- GUI verification: passed for the current Research Studio history surface via local Chrome 1440×1100 screenshot and HTTP lifecycle logs
- UI redesign: active — modern professional research workbench; automated cleanup is in Task 8 and screenshot/WSLg acceptance remains Task 9
- Workbench Tasks 1–7: complete and independently reviewed — shortcut, design system, shell/global context, overview/system, daily/periodic, knowledge/reports/research/Lab, sources/industry management/task center.
- Workbench Task 8: review Fix Round 4 implementation complete, awaiting independent re-review — the controller guard now performs scope-sensitive ordered bind/kill/rebind for module, class, local, and self aliases; class/self/chain mutations are rejected while parameter shadow and non-Tk local rebinding remain legal. Frozen UI metadata drives Sources 名称、类别、来源地区、层级、访问、可达性、监测状态和发布者；Overview 来源指标统计已采集文档的中国 / 国外 / 未知分布。No GUI was launched.
- Algorithm reference: `last30days-skill` methods recorded for later search/ranking rounds; not installed or invoked
- UI/algorithm reference: `worldmonitor` methods recorded for later workbench and search rounds; AGPL code/assets are not used, copied, installed, or invoked
- Task 5 baseline decision: PARTIAL — automated gates pass; collection, corroboration, and entity-coverage limitations remain explicitly open for Task 6/round review

## Round 1

- Status: complete
- Proposal decision: user selected proposals 1–5 on 2026-08-31. Implementation
  order is pagination, persistent Story, source adapters/health, typed Web slices,
  then desktop lifecycle verification and gated Tk retirement.
- Closeout: `docs/iterations/round-1-closeout.md`. Delivered bounded pagination,
  persistent/audited Story clustering, explicit adapters and durable source health,
  generated/runtime-checked Web contracts, feature routers and seven lazy React
  slices, single-instance/browser fallback fixes, and temporary-data lifecycle
  smoke. Full verification passed: 241 tests and 758 subtests.
- Tk decision at Round 1: retained temporarily. Round 3 later closed the gate and
  removed it after runtime migration and replacement tests.
- Production-data mutation, commit, push, deployment, and live model/crawl remain
  unauthorized for this round.

## Round 2

- Status: complete
- Proposal decision: user selected proposals 1–7 on 2026-08-31, with email
  push explicitly excluded from proposal 1.
- Review: `docs/iterations/round-2-review.md`. Seven qualifying proposals were
  identified: durable default-Web automation, Story-centric evidence review,
  open-world coverage planning, a typed Research Studio, localhost session
  hardening, recovery workflows, and accessible component-level UI verification.
  selected. The controlling implementation and acceptance boundary is
  `docs/iterations/round-2-contract.md`; no email delivery is in scope.
- Closeout: `docs/iterations/round-2-closeout.md`. Delivered durable no-email Web
  scheduling, Story evidence review, persisted open-world coverage planning, typed
  Research Studio/product artifacts, launch-session security, recovery and
  responsive accessibility/browser evidence. Full offline verification passed:
  253 tests and 758 subtests. No live crawl/model/email or production-data mutation
  was performed.

## Round 3

- Status: complete; final gates passed; round closed
- Proposal decision: user selected proposals 1–7 and explicitly authorized
  evidence-backed legacy architecture/test/code cleanup, historical knowledge
  deletion, Windows app/desktop shortcut delivery and one fresh complete workflow.
- Review: `docs/iterations/round-3-review.md`. Seven qualifying proposals were
  identified after the full necessity, breadth, cross-cutting and completeness
  passes: truthful period pipelines/retry semantics, an executable validated
  coverage loop, a complete knowledge explorer, editorial Story/claim integrity,
  Web operations/recovery controls, authoritative API/DOM accessibility tests and
  an industry-intelligence quality benchmark. Implementation has passed the
  pre-reset gate: 126 Python tests, 3 DOM workflow tests, generated OpenAPI,
  production Web build, runtime migration and old Tk removal.
- Contract: `docs/iterations/round-3-contract.md`. React/FastAPI becomes the sole
  workbench; the old Tk workbench may be removed only after shared runtime owners
  move and replacement tests pass. Email, cloud deployment, commit and push remain
  excluded.

### Final extension and completion evidence

- Time-stratified historical collection covers weekly, monthly, quarterly, semiannual,
  biennial and five-year horizons with resumable bucket manifests, provider degradation,
  canonical deduplication and count/time/publisher gates. App status and direct collection
  are available under Research Studio.
- Production AI five-year corpus: 6,808 unique records, 60/61 covered monthly buckets,
  1,435 indexed publishers. All horizons pass: weekly 82, monthly 170, quarterly 395,
  semiannual 759, biennial 2,785, five-year 6,808.
- Regenerated from the new corpus: weekly, monthly, quarterly, six-month technology,
  two-year popularity and five-year trend Markdown plus visualization sidecars. All model
  outputs remain `draft_review_required`.
- Publisher attribution no longer collapses controlled Google News RSS items into one
  `news.google.com` publisher. Indexed labels remain unverified secondary evidence; the
  30-day verification found 21 multi-publisher Stories.
- Final verification: 134 Python tests, 3 DOM tests, deterministic OpenAPI generation,
  React production build, 97-file syntax/duplicate-definition check, compileall and
  `git diff --check` passed. Local Chrome/API lifecycle returned HTTP 200 and shut down cleanly.
- Known data-quality limits: historical corpus is news-heavy; Chinese-origin recall is
  1:3.12; OpenAlex production-scale enrichment remains unavailable without an optional
  `OPENALEX_API_KEY`. These are visible warnings, not hidden successes.
- Final hygiene: the history module is consumed by CLI, report gates and Web API;
  generated types and tests cover the surface. No additional proven-dead repository code
  was found in the affected scope. Existing ambiguous compatibility/migration surfaces were
  retained. No commit, push, deployment, email or credential mutation occurred.

## Blockers and resumptions

- 2026-08-29T21:32:16+08:00 — Step 3 `bootstrap-industry --industry ai --provider codex` could not start Codex in the sandbox because `/home/joenardo/.codex/sqlite/state_5.sqlite` was read-only; command exit `2`.
- The required elevated retry was rejected by the approval layer because authenticated Codex/public-network processing and artifact writes require an explicit trusted-user authorization. The rejection expressly prohibited workaround or indirect execution.
- Resume only after that authorization is available, by rerunning the exact Step 3 bootstrap command with approved elevated execution. Do not run Steps 4–8 until bootstrap records a non-paused terminal state with sources, value chain, and entities completed.
- Preserved progress: Python 3.12.3 and ChatGPT subscription authentication were confirmed; the clean AI skeleton, 14 seed sources, 8 candidate chain nodes, three report tasks, and `DomainIntelData/intdog.sqlite3` were created. No Chips directory was created and no generated data was deleted.
- 2026-08-29T21:45:18+08:00 — Resumed after the controller executed the exact elevated bootstrap once in trusted context. Independent ledger verification found overall `ready_for_review`, sources `passed`, value chain `passed`, entities `review`, `review_required=true`, and `artifact_status=draft`. Steps 4–8 may proceed; entity coverage limitations remain disclosed for review.
- 2026-08-29T21:55:18+08:00 — Paused at `generate-period --folder AI --kind weekly --provider codex`: the isolated context again made Codex's authenticated state database read-only; command exit `2`. Steps 4–6 and all three Step 7 aggregations completed before this pause. Resume by executing that exact weekly generation once in trusted context, then continue monthly, quarterly, and Step 8 in brief order.
- 2026-08-29T21:58:10+08:00 — Controller executed weekly generation once in trusted context; it exited `0` and produced `2026-W35.md` plus metadata with provider `codex_subscription`, model `subscription_default`, and status `draft_review_required`.
- 2026-08-29T21:58:33+08:00 — Isolated monthly generation exited `2` before model execution due the read-only Codex state database. Resume with the exact monthly command once in trusted context; quarterly and Step 8 remain unattempted.
- 2026-08-29T22:02:30+08:00 — Controller executed monthly generation once in trusted context; it exited `0` and produced `2026-08.md` plus metadata with provider `codex_subscription`, model `subscription_default`, and status `draft_review_required`.
- 2026-08-29T22:02:44+08:00 — Isolated quarterly generation exited `2` before model execution due the read-only Codex state database. Resume with the exact quarterly command once in trusted context; Step 8 remains unattempted.
- 2026-08-29T22:08:00+08:00 — Controller executed quarterly generation once in trusted context; it exited `0` and produced `2026-Q3.md` plus metadata with provider `codex_subscription`, model `subscription_default`, and status `draft_review_required`.
- 2026-08-29T22:08:23+08:00 — Isolated `trend_5y` generation exited `2` before model execution due the read-only Codex state database. Resume with the exact trend command once in trusted context; the other four Step 8 commands remain unattempted.
- 2026-08-29T22:16:41+08:00 — Controller executed `trend_5y` generation once in trusted context; it exited `0` and produced `one_time/reports/trend_5y.md` plus `trend_5y.viz.json`. The report is explicitly `draft`, includes `claims[]` and `references[]`, and uses `N/A` limitations.
- 2026-08-29T22:16:41+08:00 — Isolated `popular_2y` generation exited `2` before model execution due the read-only Codex state database. Resume with that exact command once in trusted context; `tech_6m`, deep-chain, and impact remain unattempted.
- 2026-08-29T22:22:16+08:00 — Controller executed `popular_2y` generation once in trusted context; it exited `0` and produced `popular_2y.md` plus visualization metadata. The report is explicitly `draft`, includes `claims[]` and `references[]`, and retains `N/A`/unverified limitations.
- 2026-08-29T22:22:16+08:00 — Isolated `tech_6m` generation exited `2` before model execution due the read-only Codex state database. Resume with that exact command once in trusted context; deep-chain and impact remain unattempted.
- 2026-08-29T22:28:19+08:00 — Controller executed `tech_6m` generation once in trusted context; it exited `0` and produced `tech_6m.md` plus visualization metadata. The report is explicitly `draft`, cites sources, includes `claims[]`/`references[]`, and retains `N/A`/待核验 limitations.
- 2026-08-29T22:28:19+08:00 — Isolated chain deep-report generation exited `2` before model execution due the read-only Codex state database. Resume with that exact deep command once in trusted context; impact remains unattempted.
- 2026-08-29T22:35:30+08:00 — Controller executed the chain deep-report once in trusted context; it exited `0` and produced `one_time/reports/deep/chain.md` plus visualization metadata. The research draft contains citations, `claims[]`, `references[]`, and `N/A`/待核验 limits.
- 2026-08-29T22:35:30+08:00 — Isolated final impact generation exited `2` before model execution due the read-only Codex state database. Resume with the exact event `人工智能算力供应受限` command once in trusted context; no later workflow command remains.
- 2026-08-29T22:35:51+08:00 — Controller executed the final impact command once in trusted context; it exited `0` and produced `one_time/impact/人工智能算力供应受限/analysis.md` plus `impact.json` and `analysis_task.json`. Task 4 is complete and execution returned to `ACTIVE` for later baseline tasks.
- Final Task 4 verification: SQLite integrity `ok`; bootstrap `ready_for_review`; artifact audit valid 4/invalid 0; scenario completed with 7 nonempty paths; three period drafts are `draft_review_required`; five requested reports are nonempty, cited, and limitation-aware; no Chips directory exists.
- Remaining non-blocking concerns: entities remain review-required with 4 empty chain nodes; 0/66 stories have at least two independent confirmations; daily origin recall is China 2/foreign 66; 2 duplicate URLs; Semantic Scholar failed with HTTP 429 and two GitHub searches failed with HTTP 403 rate limits. These sources are not represented as successful.
- 2026-08-29T22:57:00+08:00 — User-requested pause before restarting Codex. The Task 4 independent review remains open: six HTTP 403/paywall endpoints are incorrectly counted as reachable; deep-report structured sidecars, impact structured result fields, and durable Step 8 provider/model provenance remain incomplete. Fix round 1 had created `DomainIntelSearch/tests/test_report_generation.py` and its test bytecode, but source implementation, data reconciliation, fix report, and scoped re-review were not completed. Resume Task 4 fix round 1 from this exact point; do not rerun bootstrap, crawl, or the eight completed model-generation commands.
- 2026-08-29T23:46:49+08:00 — Fix round 1 completed without bootstrap, crawl, aggregation, model generation, deletion, or Chips creation. Stored access checks were reclassified through the production source-audit path (33/59 reachable; all HTTP 401/403 and declared paywalls manual), the bootstrap audit was refreshed, and all five Step 8 artifacts were reconciled from existing Markdown with deep sidecars, structured impact fields, and provider/model/status provenance. Focused tests, the 70-test Search suite with ResourceWarnings treated as errors, repository checker, and data assertions passed; execution returned to `ACTIVE`.
- 2026-08-30 — Task 5 fresh automated verification passed: Search 70/70, App 14/14, repository checker, compileall, and `git diff --check` all exited 0; SQLite integrity is `ok` and migrations are monotonic through 10. The baseline decision is `PARTIAL`, not a clean-data-quality pass: the current 68 documents are China 2/foreign 66, hiring and CEO counts are zero, 0 of 66 claims have two independent publisher clusters, 2 duplicate canonical URLs remain, all 14 canonical `value_chain_nodes.evidence_count` values are zero, and the bootstrap entity audit remains `review` (four uncovered stages; audit count 27 versus 41 active distinct industry entities). Generated reports retain citations and durable draft/provider/model metadata. The known timestamp-sensitive agenda-dedup test did not reproduce in this fresh full Search run.
