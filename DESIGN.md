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

- SQLite is the sole business-state write authority.
- JSON, Markdown, and portable single-file HTML are views and artifacts, not a second database.
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

- Codex CLI and Claude Code execute directly only when their stable non-interactive adapters and public login probes pass.
- DeepSeek Harness, Work Buddy, Qwen Code, CodeBuddy, Kimi, Gemini CLI, OpenCode, and future Agents use the same diagnosis pipeline. Without a direct adapter they expose MCP, task-package, or result-import workflows only.
- A running GUI is not a callable Agent. Unknown Agents never gain direct execution implicitly.
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

Source discovery and industry bootstrap reuse one canonical source prompt so their primary gate cannot drift. Report, research-assistant, and Agent modules still own domain-specific templates. They share evidence states and artifact-quality gates but have not yet migrated to one `PromptSpec`; consolidation must wait for prompt snapshots, output-schema compatibility checks, and regression evaluation.

## Documentation and release

The public repository retains only current, necessary, aligned Chinese and English user guides, architecture, source-governance, and release documentation. Approval packets, iteration logs, screenshot evidence, machine-specific paths, and obsolete state snapshots remain in Git-ignored local work directories instead of product documentation.

Verification uses a risk-driven minimal set covering settings inheritance, Agent diagnosis, job state, source and paper budgets, first-run drift semantics, Git data exclusion, Web production build, and desktop contracts. The user performs the real cold-start industry acceptance; the project supplies a repeatable entry point and checklist without creating user industry data.
