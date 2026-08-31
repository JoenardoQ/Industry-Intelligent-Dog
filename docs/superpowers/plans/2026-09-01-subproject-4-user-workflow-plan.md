# Subproject 4: Complete User Workflow Implementation Plan

> **Execution requirement:** Use `superpowers:subagent-driven-development`; perform visual and accessibility review for each page task after specification review.

**Objective:** Organize all implemented core capabilities into a modern research workbench that users can complete, understand, and recover.
**Architecture:** Split pages by functional directory; consume only generated OpenAPI types; shared state components unify loading/empty/partial/stale/error/ready.
**Tech stack:** React 19, TypeScript, Vite, React Testing Library, Vitest, react-markdown.
**Specification:** `docs/superpowers/specs/2026-09-01-subproject-4-user-workflow.md`

## Global Constraints

- Do not create new visual helper flows; implement the approved modern, low-saturation, readable direction.
- Body text ≥16px, auxiliary text ≥14px, long-text line height ≥1.6, and 200% zoom support.
- Pages must not handwrite Provider, Agent, or API response catalogs.
- The UI must not hide unknown, partial, or failed states.

---

### Task 1: Make Generated Types the Sole Frontend Contract

**Files:**
- Create: `DomainIntelWeb/src/api/client.ts`
- Create: `DomainIntelWeb/src/api/runtime.ts`
- Modify: `DomainIntelWeb/src/api.ts`
- Modify: `DomainIntelWeb/src/generated/openapi.ts`
- Test: `DomainIntelWeb/tests/test_frontend_contract.py`

- [ ] **Step 1: Write RED contract tests**

Prohibit `api.ts` from redefining generated Schemas; every feature API path must belong to `ApiPath`; Markdown/Artifact requests use the session client.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelWeb/tests/test_frontend_contract.py -q`

- [ ] **Step 3: Split the client and add minimal runtime guards**

`api<TPath extends ApiPath>()` unifies session headers, the error envelope, cancellation, and JSON parsing; feature files import generated types.

- [ ] **Step 4: Run GREEN and build**

Run: `python -m pytest DomainIntelWeb/tests/test_frontend_contract.py -q && npm run build --prefix DomainIntelWeb`

### Task 2: First-Run Onboarding and Industry-Overview Loop

**Files:**
- Create: `DomainIntelWeb/src/features/setup/DiagnosticsStep.tsx`
- Create: `DomainIntelWeb/src/features/setup/ConnectionStep.tsx`
- Create: `DomainIntelWeb/src/features/setup/IndustryStep.tsx`
- Create: `DomainIntelWeb/src/features/setup/BootstrapStep.tsx`
- Modify: `DomainIntelWeb/src/features/SetupWizard.tsx`
- Modify: `DomainIntelWeb/src/features/OverviewPage.tsx`
- Modify: `DomainIntelWeb/src/features/shared.tsx`
- Test: `DomainIntelWeb/src/test/onboarding.test.tsx`

- [ ] **Step 1: Write RED first-run-flow tests**

Cover no-model, CLI, API, MCP, diagnostic failure, source→industry value chain→entity gates, cancellation/recovery, reopen, industry create/switch/rename/import/export/recycle-bin restore, overview count links, and persistent directed edges.

- [ ] **Step 2: Run RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: Implement the four-step wizard and linked metrics**

The first task displays stages and failure actions within the page instead of immediately dropping the user into a context-free task list.

- [ ] **Step 4: Run GREEN**

Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`

### Task 3: Daily, Knowledge, Sources, and Artifact Workspaces

**Files:**
- Modify: `DomainIntelWeb/src/features/DailyPage.tsx`
- Create: `DomainIntelWeb/src/features/KnowledgePage.tsx`
- Modify: `DomainIntelWeb/src/features/SourcesPage.tsx`
- Modify: `DomainIntelWeb/src/features/ProductsPage.tsx`
- Create: `DomainIntelWeb/src/features/artifacts/ArtifactReader.tsx`
- Modify: `DomainIntelWeb/src/App.tsx`
- Modify: `DomainIntelWeb/package.json`
- Modify: `DomainIntelWeb/package-lock.json`
- Test: `DomainIntelWeb/src/test/content-workflows.test.tsx`

- [ ] **Step 1: Write RED behavior tests**

Cover the 04:00 window, title/category/source/publication-time sorting, paginated selection, select all across pages, recoverable deletion, entity filtering/details, source review, and unified artifact metadata and citations.

- [ ] **Step 2: Run RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: Implement focused components**

Split list toolbars, selection model, entity details, source review cards, and ArtifactReader into their own directory components; ArtifactReader uses `react-markdown`, GFM, and sanitization plugins, and does not duplicate loading/error logic.

- [ ] **Step 4: Run GREEN**

Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`

### Task 4: Research, Lab, Tasks, and System-Recovery Workspace

**Files:**
- Modify: `DomainIntelWeb/src/features/ResearchPage.tsx`
- Modify: `DomainIntelWeb/src/features/JobsPage.tsx`
- Modify: `DomainIntelWeb/src/features/SystemPage.tsx`
- Create: `DomainIntelWeb/src/features/research/ArtifactWorkbench.tsx`
- Test: `DomainIntelWeb/src/test/research-operations.test.tsx`

- [ ] **Step 1: Write RED workflow tests**

Cover Agent review, source campaigns, coverage planning, long-period gates, direct generation by research/report/Lab, task stage logs, pause/retry/recovery, and background-service status.

- [ ] **Step 2: Run RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: Implement unified operations and state presentation**

Remove the `document.body.innerHTML` close method; use accessible confirmation dialogs and Electron/Local API lifecycle actions.

- [ ] **Step 4: Run GREEN**

Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`

### Task 5: Design System, Accessibility, and Real Renderer Smoke Tests

**Files:**
- Create: `DomainIntelWeb/src/styles/tokens.css`
- Create: `DomainIntelWeb/src/styles/layout.css`
- Create: `DomainIntelWeb/src/styles/components.css`
- Modify: `DomainIntelWeb/src/styles.css`
- Modify: `DomainIntelWeb/src/test/setup.ts`
- Modify: `DomainIntelWeb/scripts/browser_smoke.cjs`
- Modify: `DomainIntelDesktop/src/main.cjs`

- [ ] **Step 1: Write RED accessibility coverage**

Add axe, keyboard, focus-recovery, long Chinese/English text, empty/error-state, narrow-screen, and 200% zoom tests to all routes; remove unused test dependencies or actually use `vitest-axe`.

- [ ] **Step 2: Run RED**

Run: `npm test --prefix DomainIntelWeb`

- [ ] **Step 3: Implement layered token and component styles**

Use text/icons together for state; selection boxes, tables, cards, Markdown, and long logs have consistent spacing and wrapping.

- [ ] **Step 4: Subproject gate**

Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb && npm test --prefix DomainIntelDesktop`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### Task 6: Portable Single-File Briefing and Artifact Quality Gate

**Files:**
- Create: `DomainIntelSearch/src/artifact_quality.py`
- Create: `DomainIntelSearch/src/portable_briefing.py`
- Modify: `DomainIntelSearch/src/report_tasks.py`
- Modify: `DomainIntelWeb/src/features/DailyPage.tsx`
- Modify: `DomainIntelWeb/src/features/ProductsPage.tsx`
- Test: `DomainIntelSearch/tests/test_artifact_quality.py`
- Test: `DomainIntelWeb/src/test/portable-briefing.test.tsx`

- [ ] **Step 1: Write RED artifact and offline contracts**

Cover missing evidence, vague/anomalously short/placeholder/duplicate paragraphs, missing dates/sources, broken sidecars, and invalid Markdown links/anchors. Assert that single-file HTML has no external script/CDN, remains searchable/filterable/favoritable/printable with the backend stopped and networking disabled, and shares one content/evidence manifest with Markdown.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_artifact_quality.py -q && npm test --prefix DomainIntelWeb`

- [ ] **Step 3: Implement the deterministic quality gate and self-contained export**

The quality gate is independent of Fact state; failures store machine-readable reasons and mark the artifact `partial`. HTML embeds only escaped JSON, CSS, and fixed local script; favorites use browser localStorage and do not write to the IntDog database.

- [ ] **Step 4: Run GREEN and the offline browser smoke test**

Run: `python -m pytest DomainIntelSearch/tests/test_artifact_quality.py -q && npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`
