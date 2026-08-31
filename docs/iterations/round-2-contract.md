# Self-iteration round 2 implementation contract

Approved: 2026-08-31. The user selected proposals 1–7 from
`round-2-review.md` with one explicit exclusion: **no email push**. This contract
is the implementation boundary for Round 2.

## Product outcome

The default React/FastAPI app becomes the complete local research workbench: it
owns durable collection/report schedules, exposes Story evidence review,
maintains an open-world coverage frontier, directly generates all supported
research artifacts, protects local mutations with a launch session, restores
recoverable data, and remains readable and keyboard-operable at high zoom.

The system must not claim industry completeness. It reports observed coverage,
gaps, marginal yield, stopping reasons and evidence limitations. It must not use
fixed Top-10 lists or a China/foreign quota as a substitute for coverage.

## Non-goals and authority

- No email delivery, email schedule, SMTP verification or email settings.
- No live crawl, authenticated model run or production-data mutation during
  automated verification without a separate explicit authorization.
- No Tk removal until default-Web parity, user visual acceptance and a fresh
  Windows shortcut lifecycle pass.
- No wholesale storage/framework rewrite, commit, push or deployment.
- Existing CLI, artifacts and legacy reads remain compatible.

## Required contracts

### A. Durable Web scheduling

- One scheduler owner persists per-industry enabled state, local schedule,
  period keys, next run, last attempt, last success and error.
- Supported actions are daily, weekly, monthly and quarterly collection/product
  generation only. Email is never enqueued.
- A lease prevents two processes from enqueuing the same period. Restart catch-up
  schedules a missed period at most once. Manual commands remain available.
- System UI shows status and permits enable/disable/configure/run-now.

### B. Story evidence review

- Typed list/detail endpoints expose persistent Stories, linked documents,
  independent publishers, timeline, corroboration and review history.
- Daily can switch between documents and Stories. Automatic clustering remains
  conservative. Manual merge/split is explicit and audited.
- One publisher never satisfies independent corroboration.

### C. Open-world coverage planner

- Persist coverage cells and query attempts across region, subdomain,
  value-chain stage, entity type, source type, event type and time horizon.
- Each attempt records query, rationale, status, discovered source/entity counts,
  marginal yield, evidence and stopping reason.
- The next-plan endpoint prioritizes uncovered/high-value cells, including native
  Chinese primary/authoritative sources, without enforcing a numerical ratio.
- URLs must retain discovery provenance and must not be represented as validated
  merely because a model emitted them.

### D. Typed Research Studio

- The Web directly exposes daily/weekly/monthly/quarterly, industry report, deep
  report, impact, bootstrap and Intelligence Lab actions.
- Request and response models are concrete in OpenAPI. Job result and artifact
  cards expose status, provenance, citations/limitations and visualizations.
- Deterministic fake jobs test submission; automated tests do not invoke a model.

### E. Local desktop trust boundary

- Launcher creates a high-entropy session capability. Protected mutation and
  shutdown requests require it; invalid Host and foreign Origin are rejected.
- Capability values are not written to logs. A development/test injection path
  is explicit. Read-only compatibility is retained where safe.
- The SPA receives the capability through a URL fragment or equivalent channel
  that is not sent as an HTTP referrer/request target, then removes it from the
  visible address and keeps it in session memory/storage.

### F. Recoverability

- Web lists archived industries and deleted document batches, previews restore
  collisions, restores without silent overwrite, and audits the action.
- Permanent deletion is not required for this round; recoverability takes
  precedence over destructive cleanup.

### G. Accessibility and UI verification

- Inputs have programmatic labels; dialogs manage and restore focus; key actions
  are keyboard-operable; status messages use appropriate live semantics.
- Dense lists, long text and menus remain readable at 125%, 150% and 200% zoom,
  without whole-page horizontal overflow.
- Add focused component/DOM behavior tests where practical, plus deterministic
  contract and browser checks. A dependency is added only if its testing value
  justifies the maintenance cost.

## Acceptance matrix

| Area | Required evidence |
|---|---|
| Scheduler | fake-clock due/catch-up/idempotency/lease tests; state visible; clean shutdown |
| Story | list/detail/merge/split API tests; publisher independence; Daily Story browser flow |
| Coverage | deterministic plan/dedup/yield/stop tests; visible coverage gaps |
| Research | all supported action forms submit validated fake jobs; artifacts remain readable |
| Security | valid session succeeds; missing/wrong capability, bad Host and foreign Origin fail; shutdown lifecycle passes |
| Recovery | archive/delete inventory and collision-safe restore round trips |
| Accessibility | labels/focus/keyboard assertions; seven-route build/browser smoke; zoom CSS constraints |
| Regression | full Python suite, OpenAPI export/type generation, TypeScript/Vite build, compile/check/diff |

## Implementation order

1. Persistence schemas and typed API contracts.
2. Scheduler ownership and session security.
3. Story and coverage services/routes.
4. Research Studio and recovery routes.
5. React workflows, accessibility and responsive styling.
6. Focused tests, full verification, browser/lifecycle evidence and closeout.
