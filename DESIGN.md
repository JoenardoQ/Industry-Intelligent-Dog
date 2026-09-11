# IntDog Current Architecture

[中文](DESIGN.zh-CN.md) · [User guide](README.md)

## Product boundary

IntDog is a local-first desktop industry-intelligence workbench. It builds an open-world knowledge system, continuously discovers sources, value chains, entities, events, and emerging directions, and produces research artifacts with explicit evidence status. Model output is review-required draft material, not confirmed fact or investment advice.

The released product uses Electron, React, FastAPI, and SQLite. The three desktop platforms share business source code and produce separate native packages. Industry data, databases, logs, and generated artifacts remain on the user's machine and are excluded from Git.

## Runtime and dependency direction

```text
Electron: window, lifecycle, operating-system secure storage
  └─ React: the only released user interface
      └─ session-protected localhost FastAPI
          ├─ intdog_core: SQLite, schema, evidence, jobs, and audit
          ├─ Search: source connectors, retrieval, research, and reports
          └─ Agent/provider adapters: local CLI, API, MCP, task packages
```

- SQLite owns knowledge records, task state, conversations, schedules, and workflow-setting inheritance.
- Local Agent bindings live in `_settings/agent_profiles.json`; encrypted API configuration belongs to Electron. Browser storage holds interface preferences, not authoritative provider settings.
- Markdown, report sidecars, and portable HTML are local artifacts, read alongside SQLite records. Industry export and restore must preserve this file boundary.
- Electron does not write domain facts; React has no filesystem or credential access.
- API keys enter only operating-system secure storage and reach the sidecar through a one-shot anonymous pipe.

## Settings inheritance

Industries inherit shared task and Agent/provider defaults. Only actual user overrides are persisted:

```text
system default → global setting → global task override
               → industry override → industry-task override
```

A global change affects inherited values only. Every override reports its scope and can be reset to “inherit global.” Workflow settings persist only the provider, execution mode, and periodic pipeline mode. Secrets remain outside SQLite in desktop secure storage.

## Agents and providers

The capability manifest is the sole Agent/API catalog. Every local Agent uses one diagnosis pipeline: candidate discovery, path normalization, bounded fingerprinting, version probe, authentication probe, and capability decision. A legitimate large CLI must not fail solely because it exceeds a fixed 64 MiB threshold; the executable binding is still revalidated before execution.

The default connection boundary is one operating system and one user account. Discovery merges the desktop process `PATH`, a bounded list of conventional install directories, and a command file explicitly selected through the native file picker. It never scans the home directory or disk and does not bridge Windows/WSL by default. A verified manual binding is stored in local `_settings/agent_profiles.json` and shared by onboarding, foreground tasks, and background scheduling; a changed file requires diagnosis again.

- Codex CLI and Claude Code execute directly only when their stable non-interactive adapters and public login probes pass.
- DeepSeek Harness, Work Buddy, Qwen Code, CodeBuddy, Kimi, Gemini CLI, OpenCode, and future Agents use the same diagnosis pipeline. Without a direct adapter they expose MCP, task-package, or result-import workflows only.
- A running GUI is not a callable Agent. Unknown Agents never gain direct execution implicitly.
- Readiness requires version and public authentication probes. A user-triggered live connection test must also complete one minimal non-interactive request containing a fixed response marker. Static MCP configuration is not evidence of a working direct Agent.
- OpenAI, DeepSeek, Qwen, Azure OpenAI, and compatible APIs require explicit configuration. Remote endpoints require HTTPS.

## One-click workflows and progress

Knowledge structure, industry bootstrap, periodic products, deep research, and Intelligence Lab expose documented defaults. The primary action starts immediately; advanced options may be expanded before execution, but task-package creation is not an implicit second-confirmation step.

Execution still uses durable jobs and leases. The initiating page shows semantic stage, elapsed time, heartbeat, representative counters, and artifact links. A percentage is shown only when the total is measurable; otherwise the UI reports indeterminate progress. Task-package creation or an empty artifact cannot masquerade as completed research.

## Source, paper, and collection budgets

The complete source catalog is preserved non-destructively. The monitored portfolio selects sources by marginal coverage value: authority, region, topic or value-chain node, independent publisher, valid yield, and update frequency. A category normally monitors 3–10 sources and may expand when a source adds material coverage; volume never proves completeness.

Relative to the previous baseline:

- source-discovery and retrieval-candidate budgets increase by 50%;
- general collection limits increase by 50%;
- paper targets increase by 100%.

Paper retrieval is also a frontier-discovery channel for possible new subfields, cross-disciplinary transfer, pre-commercial directions, and leading-edge technology. Such observations remain direction candidates and never become industry facts automatically. Expansion remains bounded by deduplication, publisher independence, time windows, rate limits, and artifact quality gates; it may stop early when marginal yield is exhausted.

## Evidence, drift, and prompts

Facts, claims, relations, sources, documents, Stories, jobs, and reviews use stable IDs. Reachable URLs do not prove a claim. Fact admission also requires evidence localization, semantic support, numeric and unit consistency, and claim-type corroboration.

On first run or without a same-version baseline, the summary reads “no drift detected; insufficient data for a trend” and does not raise an alert. Full metrics live in a details view.

Source discovery and industry bootstrap reuse a source prompt. Report, research-assistant, and Agent modules own output-specific templates. Reports and `execute-tasks` share `artifact_quality`: body, references, placeholders, duplication, and structured evidence checks. Research chapters are not news items; per-item dates and sources are required for explicitly typed `briefing` output, not every research heading. A passing artifact remains a draft, not a verified fact. Task bundles distinguish drafts, partial output, and skipped tasks; the CLI returns nonzero for an incomplete bundle.

Native Agent sessions receive full recent context on creation and only the new user turn on continuation or successful resume. Stateless CLI/API calls, including native-session fallback, receive full recent context. Unknown publication dates cannot satisfy the title-based deduplication time window; canonical URL and sufficiently matching content remain independent deduplication rules.

## State and failure boundaries

The workbench reads its effective provider from the settings API. A failed request displays an error instead of selecting a fallback provider. Industry changes remount industry-scoped pages and conversations. Artifact and entity requests are cancelled when selection changes; stale responses cannot overwrite the latest selection. Document anchors must not change the workbench page.

Handle errors at HTTP responses, user actions, durable job outcomes, transactions, and process cleanup. Do not convert failed required reads to empty successful results. Keep source-level failure isolation so one unreachable publisher does not abort collection.

## Known limitations

- Artifact checks validate presentation and citation structure, not semantic support or research completeness.
- Title-based deduplication deliberately retains uncertain matches when publication dates are missing.

## Run persistence and conversation ordering

Each task-bundle execution allocates a unique local run directory. The manifest is atomically replaced before an Agent call and after each task result. Provider failures preserve completed results, mark the failing task, and leave later tasks unstarted; they do not trigger an automatic retry. Each run retains its own output snapshots. An explicitly requested output path remains the latest-copy destination. A killed process leaves its last checkpoint, not a fabricated success; disk failures may prevent further checkpoint writes.

Within the desktop backend process, each industry/provider conversation serializes history reads, Agent calls, and reply persistence. Other conversations remain independent. Locks are released on failure. This is a single-backend contract, not multi-process coordination.

## Documentation and release

The public repository retains only current, necessary, aligned Chinese and English user guides, architecture, source-governance, and release documentation. Approval packets, iteration logs, screenshot evidence, machine-specific paths, and obsolete state snapshots remain in Git-ignored local work directories instead of product documentation.

Verification uses a risk-driven minimal set covering settings inheritance, Agent diagnosis, job state, source and paper budgets, first-run drift semantics, Git data exclusion, Web production build, and desktop contracts. The user performs the real cold-start industry acceptance; the project supplies a repeatable entry point and checklist without creating user industry data.
