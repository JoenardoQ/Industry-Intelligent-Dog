# Subproject 4: Complete User Workflow Specification

Status: Approved, awaiting implementation verification
Dependency: APIs, source campaigns, and background states from Subprojects 1–3

## Objective

Converge the existing React workbench into a discoverable, readable, operable complete product flow covering first-run onboarding, industry management, overview, daily intelligence, knowledge, sources, research, artifacts, tasks, and system status.

## Information Architecture

- First-run onboarding: environment diagnostics, connection method, industry creation, first task, and result confirmation.
- Industry management: create, switch, rename, import, export, move to recycle bin, and restore; permanent deletion requires a separate second confirmation.
- Industry overview: knowledge modules, directed industry value-chain graph, source/document/entity/assertion/fact counts and links, quality, and coverage gaps.
- Daily intelligence: title/category/source/time sorting, filtering, pagination, select all, multi-select, and recoverable deletion; show first appearance, heating/tracking/cooling/unresolved status, change since yesterday, and seven-day trends.
- Knowledge and entities: browse by category, region, industry value-chain endpoint, and status; entity details display relationships, evidence, and time.
- Source governance: candidates, review, monitoring, health, gaps, and manual addition.
- Research and Lab: direct generation, Agent handoff, assertion review, coverage map, and long-period status.
- Artifacts: week/month/quarter/half-year/two-year/five-year reports, Markdown, citations, limitations, and visualizations; daily briefings also export as serverless/CDN-free single-file HTML.
- Task center: stage logs, heartbeat, source, cancellation, retry, and recovery.
- System: Provider, background Worker, data directory, version, secure storage, and diagnostics.

## UI Constraints

- Body text defaults to at least 16px and auxiliary text to at least 14px; long-text line height is at least 1.6.
- Forms, lists, dropdowns, and touch targets support keyboard input and 200% zoom.
- Use low saturation, rounded corners, clear hierarchy, and stable spacing; state must not be conveyed by color alone.
- Split long pages into focused components and avoid the currently unmaintainable structure compressed into one-line JSX.
- Markdown links, citations, and external URLs use a secure-opening policy.
- The Markdown reader uses a mature open-source parsing chain (`react-markdown`, GFM, and HTML sanitization), supports a table of contents, tables, code blocks, citation backlinks, in-document search, and visualization sidecars; it does not execute raw HTML or arbitrary scripts.

## Portable Briefings and Artifact Quality Gate

Daily briefings must generate both Markdown and a fully self-contained single-file HTML document. HTML embeds styles and required data, supports offline search and filtering by source, review status, and value-chain stage, stores favorites only in browser-local storage, and prints or saves to PDF directly. Every item retains evidence links, review state, and generation time. Opening the file requires no IntDog backend, CDN, or network script.

Passing fact verification does not make an artifact readable. After generation, an independent deterministic quality gate requires evidence for important conclusions; concrete Chinese summaries, dates, and sources for highlighted items; no vague templates, placeholders, anomalously short sections, or duplicate paragraphs; parseable chart sidecars whose referenced data exists; and valid Markdown links, internal anchors, and HTML filter data. Failures produce `partial` with machine-readable reasons. A file that merely opens or looks structurally complete cannot be marked as research success.

## Data and Error States

Pages use only generated OpenAPI types. Each page must distinguish loading, empty, partial, stale, error, and ready. Errors display impact scope and the next step; background execution does not block navigation.

## Acceptance

- A new user can complete the no-model first-run flow without editing source code and can subsequently configure CLI/API/MCP.
- All overview statistics navigate to their corresponding lists.
- Agent assertions and citations are readable, and source search and review are traceable.
- Daily and recurring windows, sorting, multi-select, deletion recovery, and artifact-reading behavior comply with the contract.
- Cross-day momentum is traceable to daily observations; day-over-day and seven-day trends are unchanged by syndicated duplicates or repeated runs.
- Portable HTML remains searchable, filterable, favoritable, and printable with networking disabled and the backend stopped, contains no external script/CDN, and uses the same content/evidence manifest as Markdown.
- The artifact quality gate deterministically returns `partial` for missing evidence, vague/duplicate/placeholder content, broken sidecars, links, or anchors, independently of Fact verification state.
- Week, month, quarter, half-year, two-year, and five-year periods use parallel direct-generation buttons rather than being hidden in a dropdown; buttons display the expected window, data threshold, run status, and latest successful time.
- Keyboard, focus, semantic labels, long Chinese/English text, empty states, narrow screens, and 200% zoom have DOM/accessibility evidence.
- Browser/renderer smoke operations exercise the real UI and do not use API-only fake-GUI acceptance.
