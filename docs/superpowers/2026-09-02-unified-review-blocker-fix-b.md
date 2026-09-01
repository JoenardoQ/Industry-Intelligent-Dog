# Unified Review Blocker Fix B

Date: 2026-09-02

## Scope

This freeze closes the local product-loop and release-contract blockers without
network access, native installation, user data, CI, commit, or publication.

## Implemented

- Added an injectable credential-free public-feed bootstrap. Only fetched public
  Documents with publisher identity, timestamps, content hashes, entity evidence,
  and persisted relationship evidence count toward NOM-01. Insufficient evidence
  is `partial`; seeds and task packages never complete the gate.
- Added explicit `taskpack | direct` execution mode across the generation API,
  CLI, onboarding, products, and research workbench. Direct execution requires a
  named ready Provider. Task packages remain `waiting_for_agent`; the CLI no longer
  falls back to Codex.
- Bound native NOM evidence to the isolated data root, database hash, task ledger,
  and zero Provider-call ledger. A NOM external gap no longer skips unrelated
  lifecycle checks. Uninstall retention compares file hashes and SQLite integrity.
- Completed architecture path filters and idempotent Issue find/reuse/create/readback.
- Added one-query Story momentum batching, Daily momentum summaries/timelines, and
  System seven/thirty-day quality drift.
- Wired the six-month, two-year, and five-year controls to `tech_6m`, `popular_2y`,
  and `trend_5y`; direct reports backfill their matching horizon before writing.
- Report graphs use only persisted evidence edges and expose an explicit gap when
  none exist. Artifact quality rejects dangling reference numbers, Document/Evidence
  links, unsupported sidecar schemas, and sidecar data references.
- Updated both traceability matrices to the current implementation status. Mail is
  a hard-disabled compatibility surface and cannot be enabled by config or env.

## Focused evidence

- Python product/release/observability focused gate: `31 passed`.
- Final shortened Python closure gate: `21 passed`.
- Scheduler/API explicit-execution compatibility gate: `7 passed`.
- Web DOM/axe suite: `33 passed`; production renderer build passed.
- Desktop workflow contract passed.
- OpenAPI and generated TypeScript contract were regenerated successfully.

These results are focused evidence, not a full-repository claim.

## External gates

Live NOM-01 collection remains external and must meet the strict oracle on each
native installed build. Windows/macOS/Linux lifecycle and service mutation, native
credential stores, a real logged-in Agent, Windows signing, macOS signing and
notarization, downloaded-byte checksums, and GitHub release/Issue second-run
readback remain external. No external gate is reported as passed here.
