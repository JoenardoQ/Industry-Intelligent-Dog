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
| Local agent | Signed-in Codex CLI or Claude Code; other agents use MCP/task packages | Direct output or handoff |
| Provider API | OpenAI, DeepSeek, Qwen, or Azure OpenAI key; API charges may apply | Draft output |
| Task package | No model call | JSON prompt/task, not a report |

Secrets must be supplied through environment variables or system credential storage. They must not be committed to YAML or the data directory. Remote model endpoints must use HTTPS.

## User installation and first run

> Known issue: `4.0.0-test.1` does not satisfy this onboarding and provider-connectivity
> contract and is not recommended for non-developer installation. A replacement ships
> only after the install → onboarding → provider → first-job gates pass.

The IntDog installer contains the app and local backend, but **no model account or
quota**. Existing-data browsing, industry management, and task packages need no
model. Research generation requires one separately configured provider.

### Windows 10/11 x64

1. Download `IntDog-<version>-windows-x64.exe` from GitHub Releases, not a Source code archive.
2. Run the installer, select the destination, and use the desktop or Start-menu shortcut.
3. The test build is unsigned. If SmartScreen warns, verify the release filename and SHA-256 before deciding whether to run it.
4. On first launch, wait for Local runtime and Data directory to become ready.
5. Choose one provider:
   - **Local agent:** Codex CLI and Claude Code can execute directly. DeepSeek Harness,
     Work Buddy, Qwen Code, CodeBuddy, Kimi, Gemini CLI, and OpenCode use MCP/task-package handoff;
   - **API:** choose OpenAI, DeepSeek, Qwen, or Azure OpenAI and enter a key and model; the key uses operating-system encrypted storage;
   - **Task package:** no key, but produces a prompt rather than a completed report.
6. Create an industry, run Initialize industry research, and inspect stage, logs, and result in Task center.
7. For any other agent, copy its MCP configuration in Connection settings or export a task from Research Studio; imported results remain review-required.

If no window appears, inspect `%APPDATA%/intdog-desktop/logs/backend.log`. Do not
publicly upload logs containing API keys, tokens, or personal paths.

### macOS and Linux

- The macOS test build supports Apple Silicon arm64 only. Drag IntDog from the DMG
  into Applications; an unsigned test build may trigger Gatekeeper.
- On Linux x64, make the AppImage executable: `chmod +x IntDog-*.AppImage`.
- Local-agent mode still requires the corresponding CLI and its public sign-in flow.
  API and task-package modes are alternatives.

See the complete [installation and agent-connection guide](docs/onboarding-and-installation.md).

### Start from source (developers)

```bash
cd "/home/joenardo/My Projects/IntDog"
./run_intdog.sh
```

The source launcher prepares an isolated Python/Web runtime. The repository can move
and does not depend on a fixed drive path.

### Command line

```bash
cd DomainIntelSearch
python -m pip install -e .
python -m src.main init-industry --industry semiconductor
python -m src.main bootstrap-industry --industry semiconductor --provider codex
python -m src.main crawl-daily --industry semiconductor
python -m src.main run-lab --industry semiconductor
```

Use `--industry` for a name or alias and `--folder` for an exact data folder.

## Native distribution boundary

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
- [Current architecture](DESIGN.md)

## Verification

```bash
python -m pytest DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests -q
npm test --prefix DomainIntelWeb
npm run build --prefix DomainIntelWeb
npm test --prefix DomainIntelDesktop
```

Local databases, generated intelligence, build outputs, runtimes, dependencies, logs, and secrets are ignored by Git. Back up the complete `DomainIntelData/` directory only after stopping active collection and scheduling.
