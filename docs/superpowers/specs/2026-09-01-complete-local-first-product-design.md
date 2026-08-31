# IntDog Complete Local-First Product Design

Status: Conversation design approval completed; awaiting written specification review
Date: 2026-09-01
Corresponding Chinese: `2026-09-01-complete-local-first-product-design.zh-CN.md`

## 1. Objectives

IntDog must meet both hard gates simultaneously:

1. The industry intelligence capability forms a credible, sustainable, auditable end-to-end loop;
2. Windows, macOS, and Linux users can download their respective installers, complete first launch, connect to or hand off to an Agent, create an industry, run the first task, close and reopen the application, and run background recurring tasks.

If either gate is unmet, the product status is `NOT_READY`. Native CI on all three platforms is a release hard gate; real-device feedback after public Beta is supplemental evidence and does not replace native CI.

## 2. Decisions and Non-Goals

### 2.1 Approved Decisions

- Adopt a local-first modular monolith; do not rewrite the entire system or split it into a microservices platform.
- Retain React, Electron, FastAPI, SQLite, and the Python research core, while redrawing their boundaries.
- Add a cross-platform background Worker so recurring tasks can execute after the window is closed.
- Promote Agent results through the path “human review → candidate evidence → automatic verification → accepted fact.”
- Integrate Agents through native CLI, API, MCP, task package, and restricted custom CLI tiers; do not overstate capabilities.
- When there is no Agent or API key, still support a degraded but real credential-free workflow.
- Target 8–10 high-quality representatives for each information-source category; when the credibility threshold is not met, allow fewer and disclose the gap.
- Keep email push disabled.

### 2.2 Non-Goals

- Do not provide IntDog cloud accounts, cloud synchronization, or team collaboration.
- Do not require every Agent to be directly executable by IntDog.
- Do not use a fixed Top 10, fixed China/overseas ratio, or source count to claim industry completeness.
- Do not write model-generated text, a single media report, self-media content, or a leadership Post directly as a fact.
- This design does not authorize deleting production data, making real paid calls, committing, pushing, triggering CI, or publishing.

## 3. Architecture

### 3.1 Desktop Shell

Electron is responsible only for windows, the system tray, first-run onboarding, operating-system secure credentials, updates, background-service installation, and lifecycle management. It does not contain research logic or maintain an independent Provider catalog.

### 3.2 Local API

FastAPI is the only business entry point for React, Electron, the background Worker, the CLI, and external Agents. Pydantic defines requests and responses, OpenAPI is the authoritative contract, and frontend types are generated from the contract. The Local API binds only to the loopback address and uses random session tokens and origin validation.

### 3.3 Research Core

The Python core is responsible for source discovery, collection, normalization, deduplication, entity resolution, industry value chains, evidence graphs, coverage planning, and research artifacts. The core must not depend on Electron or React.

### 3.4 Background Worker

The Worker is an independent, single-instance, least-privilege process. Windows uses Task Scheduler, macOS uses LaunchAgent, and Linux uses a systemd user timer. The Worker executes tasks through a protected local interface and persistent task repository; it does not require the window to remain open.

### 3.5 Data Store

SQLite stores structured state, entities, relationships, assertions, facts, tasks, and audit records. The industry directory stores original documents, necessary snapshots, Markdown, and visualization sidecars. Writes use temporary files and atomic replacement; database migrations are monotonic, backupable, and rollback-capable.

### 3.6 Agent Gateway

The single capability Manifest describes the identity, region, connection method, execution level, authentication, Web capability, structured output, and schedulability of Agents and API Providers. The execution layer uses explicit adapters; unknown Providers are rejected by default.

### 3.7 React Workbench

The workbench is split into industry overview, daily intelligence, knowledge and entities, research, artifacts, sources, tasks, and system settings. Pages consume only strongly typed APIs and do not directly understand disk layouts or Provider-specific exceptions.

## 4. Authoritative Data Flow

The only primary data flow is:

`Source discovery → raw collection → normalization and deduplication → candidate evidence → verification and conflict handling → knowledge graph → research artifacts`

Agent imports must enter through candidate evidence. No UI, CLI, scheduler, or adapter may bypass verification and write directly to accepted facts.

## 5. Data and Credibility Model

### 5.1 Four-Layer Objects

- `Source`: publisher and entry point; records region, category, owner, authority level, access method, crawl health, and selection rationale.
- `Document`: original document; records canonical URL, publication time, author, publisher, language, collection time, content hash, and snapshot reference.
- `Assertion`: verifiable assertion; must point to evidence and distinguish facts, opinions, forecasts, company disclosures, policy texts, and secondhand retellings.
- `Fact`: knowledge that has passed source, time, entity, and conflict verification.

Credibility states are unified as:

`raw → candidate → corroborated / disputed / rejected → accepted`

Important disputes must not be overridden by a simple majority vote. Facts must retain their source chain and verification time.

### 5.2 Source Strategy

Government, regulatory, statistical, standards-organization, original company-disclosure, and peer-reviewed materials have priority; news is used for cross-validation; self-media and leadership Posts are used to discover leads and opinions. High-quality sources that cannot be fetched enter manual-access recommendations and are not marked as successfully collected.

Each source category targets 8–10 authoritative, well-known, representative publishers. Different industries may share sources. The system must not introduce untrusted sources to meet the quantity target; when the target is not met, it displays the gap and the reason.

China-source share does not use a fixed ratio. The system measures differences in China and overseas coverage across subfields, industry-value-chain endpoints, entities, and time; it prioritizes filling China gaps while retaining a uniform quality threshold.

### 5.3 Source Discovery, Selection, and Continuous Review

Sources must pass an auditable discovery and review pipeline:

`Query planning → multi-round search → candidate normalization → publisher identity verification → quality and representativeness assessment → coverage and diversity review → access audit → activation or manual review`

- The system generates Chinese and English query families by industry, source category, and industry value-chain endpoint. Query families cover official directories, regulatory and statistical sources, associations, standards, company disclosures, academic journals, professional media, platforms, self-media, and leadership accounts.
- Each source-mapping run must execute at least two rounds: the first establishes the authoritative baseline; the second performs targeted expansion based on gaps in region, endpoints, entities, and source types. The candidate pool must exceed the final 8–10 selected-source target.
- Stopping conditions require both the coverage threshold and marginal-gain convergence. Stopping is allowed only after two consecutive rounds produce no new qualified sources, or new sources only duplicate existing publishers and coverage units. Budget limits, rate limiting, or network interruptions must be recorded as pause reasons and must not be disguised as convergence.
- Each candidate source records the discovery query, discovery time, publisher entity, ownership, primary- or secondary-source status, region, access method, historical stability, citation quality, update frequency, and the reason for selection or rejection.
- Official primary sources whose identity, ownership, and URL have been verified may be activated automatically. Media, platforms, self-media, leadership accounts, and other individual sources must first enter the manual-review queue.
- Active sources are re-reviewed periodically. If a source persistently fails, changes ownership, becomes a content farm, or provides no marginal new value over an extended period, downgrade it to manual, fallback, or rejected status; historical documents and evidence relationships must not be deleted as a result.
- The UI provides views of candidate sources, review records, coverage gaps, and selection or rejection reasons, and allows users to add sources manually, reassess them, and change their monitoring status.

When fewer than 8 qualified sources are available, the system must show the queries already executed, candidate count, rejection reasons, and remaining gaps; it must not return only an empty list or low-quality filler results.

### 5.4 Deduplication and Open-World Coverage

Deduplication considers canonical URLs, content hashes, near-duplicate text, events, publishers, and citation relationships simultaneously. When duplicate documents are merged, multi-source relationships are retained and the evidence chain is not deleted.

Coverage objects include enterprises, research groups, government institutions, associations, investment institutions, people, products, technologies, standards, and policies. The system reports “known coverage” and “completeness not proven”; it does not use Top 10 as a substitute for an industry panorama.

## 6. Product Workflows

### 6.1 First Launch

1. Check the data directory, disk, background service, network, available Agents/APIs, and credential store;
2. Select no-model, logged-in CLI, API, MCP/task package, or restricted custom CLI;
3. Create an industry and pass the information-source, industry-value-chain, and entity-coverage gates in sequence;
4. Run a real bootstrap that is observable, cancellable, and resumable;
5. After completion, enter the industry overview; after reopening, retain the industry and task state.

No-model mode uses credential-free public sources to complete the basic source, document, entity, and industry-value-chain candidate workflows. Deep search, synthesis, and reports are enabled after connecting an Agent/API, with capability differences shown explicitly.

### 6.2 Industry Overview

The overview displays the knowledge structure, directed industry-value-chain graph, sources, documents, entities, evidence quality, and coverage gaps together. Every count links to the corresponding list; unsupported decorative metrics are not allowed.

### 6.3 Daily and Recurring Intelligence

The daily window is from 04:00 on the previous day to the current system time. The list supports sorting by title, category, source, and publication time, as well as select all, multi-select, and recoverable deletion. The source displays the actual website, developer, paper author, or self-media name.

Recurring intervals support week, month, quarter, half-year, two years, and five years. The interval starts at the boundary of the last successful run; when there is no history or less than one period of history, look backward to fill a complete period. Long intervals use uniform time buckets and must simultaneously meet total-volume, time-coverage, publisher-diversity, and evidence-quality gates.

### 6.4 Research and Artifacts

The research assistant, industry reports, and Intelligence Lab use a unified artifact model: Markdown, citations, structured assertions, limitations, and visualization sidecars. Industry value chains, competitive landscapes, trends, technology roadmaps, and event impacts can generate directed graphs or timeline graphs.

### 6.5 Agent Review

Users must be able to inspect every assertion and citation in Agent results, then choose to reject it, retain it as an opinion, or submit it for verification. Human approval does not equal fact acceptance. Only after citation reachability, source identity, time, entity, and conflict checks pass may an item be promoted to an accepted fact.

### 6.6 Task Center

The task center displays stage logs, heartbeats, progress, retries, cancellation, failure reasons, and recovery actions. Background tasks involving paid calls or the first addition of new credentials must wait for user confirmation.

## 7. Task States and Recovery

Task states are:

The authoritative state set is `queued / running / cancelling / paused / completed / partial / failed / cancelled / interrupted`. The normal completion path is `queued → running → completed`; cancellation passes through `cancelling → cancelled`; `partial`, `failed`, `cancelled`, and `interrupted` never advance the last-success boundary, while `paused` and recoverable `interrupted` runs may be requeued.

Each stage stores its inputs, time window, Provider, model, progress, heartbeat, output location, and failure category. After a crash, it resumes from a checkpoint or fails safely; repeated execution must be idempotent.

Errors are classified into five categories: configuration, source, data, model, and system. The UI displays the reason, impact scope, and an actionable next step, rather than only a traceback or endless planning.

Deletion first moves items to the IntDog recycle bin. Permanent deletion requires explicit second confirmation. A controlled backup is created before migration, and failures roll back automatically. Industry exports include the Schema version and checksum. The desktop App and Worker use a single-instance lock and task leases to prevent duplicate execution.

## 8. Security and Privacy

- API keys are stored only in the operating system’s secure storage and never enter SQLite, the DOM, APIs, logs, task packages, or artifacts.
- Custom CLIs do not use a shell; commands and arguments use an allowlist, with limits on paths, size, runtime, and output.
- MCP is read-only by default; writes require item-by-item authorization.
- Agent imports are limited by size, Schema, industry, task ID, citations, and target path; path traversal is rejected.
- Logs scrub credentials before persistence and have a per-task size limit.
- By default, all industry data is stored only on the user’s device.

## 9. Test Coverage Contract

The test ledger must cover the following P0 risks and trace each risk to tests and evidence that can distinguish pass from fail:

| Risk domain | Must prove |
| --- | --- |
| First use | Fresh installation, no-model, CLI, and API paths can create an industry and complete the first task |
| Data credibility | Source, Document, Assertion, and Fact cannot skip levels; conflicts and missing citations cannot become facts |
| Source discovery and review | Chinese and English query families, two-round expansion, candidate normalization, identity/ownership/URL verification, manual-review boundaries, and stopping conditions are all traceable |
| Deduplication and coverage | URL, content, cross-source duplicates, uniform time buckets, and the China-source gap strategy comply with the contract |
| Agent Bridge | Export, import, review, candidate verification, idempotency, and malicious inputs all produce deterministic results |
| Background scheduling | App closure, system restart, duplicate wakeups, time zones, daylight saving time, overlap, and failure recovery |
| Task states | Cancellation, pause, timeout, crash, retry, idempotency, expired heartbeat, and partial writes |
| Security | Credentials are not leaked; path traversal, command injection, and unauthorized writes are rejected |
| Migration and recovery | Upgrade of old databases, failure rollback, backup restoration, and compatibility with old versions |
| UI | Empty states, long text, lists, dropdowns, keyboard, zoom, bilingual support, and error recovery |
| Resource boundaries | Large files, insufficient disk space, oversized output, rate limiting, offline operation, and corrupted data fail safely |
| Packaging | Frozen sidecars, static assets, secure storage, and background-service files are included in installers |
| Lifecycle | Installation, launch, operation, close, background execution, reopen, update, and uninstall do not accidentally delete industry data |

Test levels include Python unit, property, state-machine, and fault-injection tests; FastAPI contract and security tests; React DOM and accessibility tests; Electron renderer first-run-flow tests; frozen sidecar/Worker integration tests; and native installer lifecycle tests on all three platforms. A small number of credential-free public sources may enter controlled network contract tests; paid APIs and real Agent accounts must be labeled separately and cannot use mocks to claim a pass.

## 10. Three-Platform Release Gates

1. The Windows x64, macOS arm64, and Linux x64 workflows for the same Git revision all pass;
2. Each platform independently generates an installer, checksum, and test report;
3. The installer completes the first-run flow, background tasks, close/reopen, and data persistence;
4. Unsigned Windows/macOS builds may be released only as public Beta; the stable release must be signed, and macOS must be notarized;
5. If any P0 risk remains open, the status stays `NOT_READY`.

## 11. Implementation Decomposition

This design is a system-level master specification and cannot safely be compressed into one implementation task. It will subsequently be split in dependency order into five independent subprojects; each subproject separately executes its specification, plan, TDD, review, and verification:

1. **Authoritative Contract and Agent Evidence Loop**: unified response Schema, human-readable review, candidate evidence, and fact-promotion thresholds;
2. **Data Credibility and Coverage Engine**: four-layer objects, multi-round source discovery and continuous review, source composition, deduplication, conflicts, and open-world coverage;
3. **Background Tasks and Recovery**: cross-platform Worker, system scheduling, leases, checkpoints, and recovery;
4. **Complete User Workflow**: first-run onboarding, industry management, overview, daily, recurring, research, artifacts, and task center;
5. **Three-Platform Productization**: frozen resources, native lifecycle, signing status, installation documentation, and Beta gate.

Each subproject must keep old data migratable and rerun the shared risk gates after completion. The contract of the preceding subproject is the input to the next subproject.

## 12. Completion Criteria

Completion may be claimed only when all of the following conditions are met:

- The approved contracts for all five subprojects have been implemented;
- Every row in the P0 risk ledger has execution evidence from the source revision used for that run;
- The no-model basic workflow and at least one logged-in Agent/API deep workflow both run successfully;
- Agent results cannot bypass candidate-evidence verification;
- Source mapping has traceable evidence for queries, selection, rejection, review, and convergence;
- Recurring tasks continue to execute safely after the App is closed;
- Installers for all three platforms come from the same source version and pass the native CI lifecycle;
- Documentation, UI, API, installers, and release status are mutually consistent;
- Incomplete or unverified capabilities are explicitly marked; historical builds or mock results are not used as substitutes.
