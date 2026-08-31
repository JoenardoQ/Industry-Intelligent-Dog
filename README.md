# IntDog Industry Intelligence System

[中文文档](README.zh-CN.md) · [Source-governance contract](docs/source-governance.md)

> Version 4.0 Preview. Model output is review-required draft material, not confirmed fact or investment advice.

IntDog is a local-first industry-intelligence workbench. It maps sources and value chains, continuously collects news, papers, GitHub activity, funding, hiring, and leadership posts, and produces cited periodic and industry research.

## System goal

IntDog does not require the user to begin with a fixed question set. Its default goal is a broad, traceable, continuously expanding industry knowledge system that exposes both established knowledge and the current boundary of discovery.

- Discover subfields, value-chain activities, products, technologies, companies, research groups, people, standards, policy, and capital activity.
- Treat the database as an incomplete observation of an open world.
- Make smaller companies, startups, labs, and uncovered nodes visible alongside leaders.
- Attach conclusions to sources, dates, scope, and conflicting evidence.
- Reuse canonical entities across industries while preserving industry-specific roles.

## Components

| Component | Responsibility | Network access |
| --- | --- | --- |
| `DomainIntelSearch` | Discovery, collection, verification, knowledge modeling, and reports | Yes |
| `intdog_core` | Canonical schema, SQLite, evidence, tasks, locks, and migrations | No |
| `DomainIntelData` | Structured facts and portable JSON/Markdown artifacts | No |
| `DomainIntelWeb` | React workbench and local FastAPI boundary | Existing data works offline |
| `DomainIntelApp` | Startup, isolated runtime, shortcuts, and shared job runtime | No |
| `DomainIntelDesktop` | Electron shell and native packaging | No |

```text
source adapters → normalization → intdog_core → intelligence/knowledge engines
                → queries and reports → desktop app / agents
```

`Intelligence Lab` adds deterministic evidence-gap compilation, source observation, explainable value-chain scenarios, and a research-boundary agenda. Its outputs are analyses, not automatically accepted facts. See [Intelligence Lab](DomainIntelSearch/INTELLIGENCE_LAB.md).

SQLite is the canonical store for entities, documents, Stories, relations, claims, evidence, source health, schedules, and jobs. The filesystem stores raw material, portable views, Markdown, and charts. Business writes pass through the application service.

## Execution modes

| Mode | Authentication and cost | Result |
| --- | --- | --- |
| Codex subscription | Local ChatGPT/Codex login; no API key | Draft output |
| Provider API | Provider key; API charges may apply | Draft output |
| Task package | No model call | JSON prompt/task, not a report |

Secrets must be supplied through environment variables or system credential storage. They must not be committed to YAML or the data directory. Remote model endpoints must use HTTPS.

## Five-minute start

```bash
cd "/home/joenardo/My Projects/IntDog"
./run_intdog.sh
```

The source/development launcher prepares an isolated Python and Web runtime and opens the React workbench. The local API binds only to `127.0.0.1`; closing through System Status stops the backend. Windows + WSL uses the generated desktop shortcut. A native Windows checkout may run `DomainIntelApp/run_app.bat`.

Typical first use:

1. Create or select an industry.
2. Run industry initialization in Codex, API, or task-package mode.
3. Let source, value-chain, and entity gates complete in order.
4. Collect daily intelligence and generate periodic or deep research when needed.

Command-line equivalent:

```bash
cd DomainIntelSearch
python -m pip install -e .
python -m src.main init-industry --industry semiconductor
python -m src.main bootstrap-industry --industry semiconductor --provider codex
python -m src.main crawl-daily --industry semiconductor
python -m src.main run-lab --industry semiconductor
```

Use `--industry` for a name or alias and `--folder` for an exact data folder.

## Native test distributions

The approved package is an Electron shell plus one PyInstaller API/CLI sidecar. Each installer contains only its native runtime:

- Windows x64: NSIS `.exe`
- macOS Apple Silicon arm64: `.dmg`
- Linux x64: `.AppImage`

Every shared architecture, API, schema, runtime, or UI change triggers all three native package gates. Test builds use `4.0.0-test.*`, are marked GitHub Pre-release, and are unsigned. Windows SmartScreen or macOS Gatekeeper may therefore require manual approval. Stable Windows and macOS releases require signing; macOS also requires notarization. See the aligned [release contract](docs/release-readiness.md) and [Chinese release contract](docs/release-readiness.zh-CN.md).

## Main artifacts

| Path | Content |
| --- | --- |
| `sources.json` | Nine source classes, reachability, region, and monitoring role |
| `one_time/knowledge/` | Industry, value chain, entities, and learning structure |
| `periodic/daily/` | News, papers, GitHub, funding, hiring, and leadership posts |
| `periodic/{weekly,monthly,quarterly}/` | Aggregates, Markdown, and chart metadata |
| `one_time/reports/` | Five-year, two-year, six-month, and deep reports |
| `one_time/research/history/` | Resumable time-bucket history manifests |
| `one_time/intelligence/` | Evidence, source observation, scenarios, and research agenda |

Artifact states are distinct: `candidate`, `collected`, `verified/corroborated`, `draft_review_required`, and human-only `reviewed/published`. A generated task or report is never silently presented as reviewed fact.

## Workbench and scheduling

The workbench provides Overview, Daily Intelligence, Research Products, Sources, Research Assistant, Task Center, and System Status. Lists are server-paginated; bulk selection applies to the loaded page. Industry and daily-item deletion is recoverable through `_trash/`.

The Web scheduler is the only schedule owner. It persists daily/weekly/monthly/quarterly schedules, leases, period keys, next run, last success, and errors. Restart catch-up is idempotent. Email is always disabled in the default workbench path.

## Trust boundaries

- Source volume does not prove collection balance or claim quality.
- Government, regulatory, statistical, standards, corporate disclosure, and peer-reviewed sources take priority.
- Media corroborates; social/self-media content is a lead until verified.
- Paywalled or non-machine-readable sources may remain manual recommendations and must not be reported as collected.
- A competition landscape is an evidence skeleton; weakly supported entities remain on a Watchlist.
- “Not observed” never means “does not exist.” Report coverage gaps and failed sources.
- The project does not claim commercial-database coverage for global funding, customs, hiring, real-time markets, or social platforms.

## Documentation

- [Search engine](DomainIntelSearch/README.md) · [中文](DomainIntelSearch/README.zh-CN.md)
- [Data contract](DomainIntelData/README.md) · [中文](DomainIntelData/README.zh-CN.md)
- [Application guide](DomainIntelApp/README.md) · [中文](DomainIntelApp/README.zh-CN.md)
- [Implementation status](IMPLEMENTATION_STATUS.md)
- [Long-term design](DESIGN.md)

## Verification

```bash
python -m pytest DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests -q
npm test --prefix DomainIntelWeb
npm run build --prefix DomainIntelWeb
npm test --prefix DomainIntelDesktop
```

Local databases, generated intelligence, build outputs, runtimes, dependencies, logs, and secrets are ignored by Git. Back up the complete `DomainIntelData/` directory only after stopping active collection and scheduling.
