# IntDog Architecture

[中文](DESIGN.zh-CN.md) · [User guide](README.md) · [Current status](IMPLEMENTATION_STATUS.md)

## Product boundary

IntDog is a local-first desktop industry-intelligence workbench. Electron owns the native lifecycle and encrypted credential boundary; a frozen Python sidecar serves one localhost FastAPI application; React is the released user interface. Windows, macOS, and Linux share the same source and have independent native artifacts and gates.

It is not a bundled language model, a commercial-data entitlement, or a promise that a detected desktop agent is authenticated. Task-package mode works without a model. Direct generation requires an authenticated Codex/Claude CLI or an explicitly configured API provider.

## Runtime

```text
Electron
  ├─ safeStorage + minimal preload IPC
  ├─ starts one frozen Python sidecar on 127.0.0.1:random-port
  └─ React renderer
       └─ session-protected FastAPI/OpenAPI
            ├─ intdog_core SQLite fact and audit store
            ├─ collection, research, reports, scheduling, jobs
            ├─ read-only MCP
            └─ review-gated Agent Bridge
```

Electron generates a random session capability on every launch. The renderer never receives API keys. Keys are accepted only through preload IPC, encrypted with the operating-system secure store, and transferred through a bounded anonymous one-shot pipe. If secure encryption is unavailable, storage is refused.

Background execution is a separate, revocable per-user permission. Platform Task
Scheduler/LaunchAgent/systemd entries launch the same frozen Worker; they do not own
schedules or broaden provider authorization. Mutable data lives in the OS user-data
directory and is retained when the application is uninstalled.

## Data and evidence

SQLite through `intdog_core` is the sole business-write authority. Compatibility JSON and Markdown remain portable views and artifacts. Facts, claims, relations, sources, documents, Stories, tasks, runs, and audits use stable identifiers. Model and external-agent output defaults to `draft_review_required`; absence of evidence remains explicit.

Industry coverage is open-world: subdomain, chain stage, region, entity kind, source class, event, and time horizon are measured as gaps instead of assuming a fixed Top 10 is complete. Long-history acquisition is bounded by count, time-bucket, and publisher-diversity gates.

## Agent and provider architecture

`DomainIntelSearch/src/services/capability_manifest.py` is the authoritative catalog for domestic and international agents and API providers. It owns IDs, region, connection and execution modes, public commands, authentication, Web capability, defaults, and scheduling eligibility. Provider construction remains an explicit fail-closed adapter map.

- Codex CLI and Claude Code have bounded direct adapters.
- OpenAI, DeepSeek, Qwen, and Azure OpenAI use explicit API configuration.
- DeepSeek Harness, Work Buddy, Qwen Code, CodeBuddy, Kimi CLI, Gemini CLI, OpenCode, and unknown agents use read-only MCP or task-package handoff unless a verified adapter exists.
- Agent Bridge exports tasks and imports validated results atomically into a review-required area. It never writes imported assertions directly into the fact store.

## Dependency direction

- `intdog_core`: schema, repositories, deterministic domain rules.
- `DomainIntelSearch/src`: collection and research services; depends on core.
- `DomainIntelApp/runtime`: neutral data/job compatibility used by applications.
- `DomainIntelWeb/api`: protected application boundary; depends on services/runtime.
- `DomainIntelWeb/src`: generated-contract React client; no filesystem access.
- `DomainIntelDesktop`: lifecycle and packaging only; no domain writes.

The older v2 design is preserved as [historical material](docs/archive/DESIGN-v2-legacy.md). It is not an implementation contract.

## Release gates

Every native host must run the complete Python suite, Web DOM tests and production build, generated OpenAPI drift check, repository check, desktop tests, frozen-sidecar smoke, renderer first-run workflow, restart persistence, and secure-credential lifecycle where available. Unsigned test builds are Pre-releases. Windows signing and macOS signing/notarization are mandatory for stable release.

Current readiness and evidence limitations are recorded in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md); evidence from an older commit never proves a changed working tree.

`NOM-01`, native installation/service/uninstall lifecycle, and real logged-in Agent
deep smoke are external gaps until their matching environment produces evidence.
The SP4 and SP5 A local freeze reports are necessary local evidence, not substitutes.
