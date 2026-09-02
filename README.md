# IntDog Industry Intelligence Workbench

[中文](README.zh-CN.md)

IntDog is a local-first desktop application for building and continuously updating an industry knowledge system. It starts with sources and a value chain, collects news, papers, GitHub activity, funding, hiring, and leadership posts, and produces cited research artifacts with explicit status and visualizations.

> Version 4.0 is a test release. Model output is review-required draft material, not confirmed fact, legal advice, or investment advice.

## Capabilities

- Manage multiple industries and inspect knowledge, value chain, entities, sources, and documents from the overview.
- Discover and review nine source classes: government/regulatory/standards, associations, institutional blogs, professional platforms, independent publishers, news, papers, company disclosures, and financial data.
- Persist directed upstream/downstream relationships and evidence links for companies, labs, people, technologies, products, and policies.
- Search, sort, filter, bulk-select, and recoverably delete daily intelligence; stories expose first appearance, momentum, and seven-day changes.
- Generate weekly, monthly, quarterly, six-month, two-year, and five-year artifacts, plus value-chain, competition, market, and event-impact research.
- Export a self-contained HTML briefing with local search, filters, bookmarks, printing, and PDF support; no IntDog backend is required to open it.
- Use a signed-in local agent, a model API, or a generic task package. Agent results must pass evidence gates before entering the fact store.
- Optionally run local background schedules. Email delivery, cloud sync, and collaboration are disabled by default.

## Installation

An installer contains the desktop UI and local backend, but no model account, API quota, or paid third-party data.

### Windows 10/11 x64

1. Download `IntDog-<version>-windows-x64.exe` from the matching GitHub Release. Do not download “Source code.”
2. Run the installer and launch IntDog from the desktop or Start menu.
3. A test build may be unsigned. If SmartScreen warns, verify the filename and SHA-256 on the release page before deciding to continue.
4. The first launch prepares the local runtime and data directory; duration depends on disk performance.
5. If no window appears, inspect `%APPDATA%\intdog-desktop\logs\backend.log`. Remove tokens, keys, and personal paths before sharing logs.

Copying a repository `.exe`, backend file, or WSL shortcut is not a substitute for an installer. All packaged components must come from the same build revision.

### macOS Apple Silicon

1. Download `IntDog-<version>-macos-arm64.dmg`.
2. Open the DMG and drag IntDog into Applications.
3. Gatekeeper may block an unsigned test build. Verify its checksum before allowing it in Privacy & Security.

### Linux x64

1. Download `IntDog-<version>-linux-x64.AppImage`.
2. Run `chmod +x IntDog-*.AppImage`.
3. Double-click or execute the AppImage from a terminal.

The three installers are independent artifacts. Any shared code change requires the Windows, macOS, and Linux gates to run again. See the [release contract](docs/release-readiness.md).

## First run

1. Wait until the setup wizard reports a ready local runtime and data directory.
2. Select a model source:
   - **Local agent:** install and sign in to the Agent CLI under the same operating system and user account as IntDog. IntDog detects it automatically; if discovery fails, select the `codex.exe`, `codex.cmd`, `claude`, or equivalent command file with “Select installed Agent.”
   - **API:** select a provider and enter a model and key. The desktop stores the key in the operating-system credential vault.
   - **Task package:** no key is required, but the result is a task for any agent, not a finished research report.
3. Create an industry name and data folder.
4. Select “Initialize industry research.” The job enters the queue directly; the current page shows its real stage and elapsed time, while Task Center exposes logs, cancellation, and retry.
5. Review source candidates, value-chain order, entity coverage, and evidence gaps before starting daily collection or reports.

IntDog connects to local Agents in the same operating system; Windows/WSL bridging is not a default product path. A desktop process can still receive a different `PATH` from a terminal, so discovery checks a bounded list of conventional install directories without scanning the disk. Manual selection verifies executable identity, version, and public sign-in status before persisting a local binding. “Test live connection” sends one very short model request and may count against the Agent subscription. Statuses distinguish ready, sign-in required, incompatible, MCP/task-package only, and unsupported.

After onboarding, use “Connection settings” in the top bar to replace an Agent, rerun diagnosis, test the connection, or restore automatic discovery. Global defaults apply to industries that still inherit them; explicit industry overrides remain unchanged. An installed or running GUI is not necessarily callable. Agents without a stable non-interactive CLI use MCP or task-package handoff.

## Supported agents

| Agent | Current support tier | Available capabilities |
| --- | --- | --- |
| Codex CLI | Native direct | Automatic discovery, explicit selection, sign-in diagnosis, live probe, direct generation, schedules |
| Claude Code | Native direct | Automatic discovery, explicit selection, sign-in diagnosis, live probe, direct generation, schedules |
| DeepSeek Harness | Experimental handoff | Command discovery, MCP, task packages, and result import; no direct-generation claim |
| Work Buddy | MCP / task package | Command discovery, MCP, task packages, and result import |
| Qwen Code, CodeBuddy Code, Kimi CLI | MCP / task package | Command discovery, task handoff, and result import |
| Gemini CLI, OpenCode | MCP / task package | Command discovery, task handoff, and result import |
| Other agents | Generic handoff | Generic MCP, or exported task JSON followed by review-required result import |

“Supported” does not mean that every Agent can be launched directly by IntDog. Native direct execution is limited to Agents with a stable, verifiable non-interactive CLI contract. Other integrations remain explicit handoffs so that executable discovery is never misreported as a connected model.

## Daily workflow

1. **Overview:** inspect the knowledge structure, directed value chain, and linked counts.
2. **Daily Intelligence:** collect from 04:00 on the previous day to the current system time; sort by title, category, or source and review evidence.
3. **Sources:** retain the complete directory. Stable sources enter automatic monitoring; login-walled, paywalled, or anti-bot sources remain recommended for manual reading.
4. **Research Products:** continue from the previous successful window. With no full prior period, backfill one complete period from the current time. Long horizons sample across time buckets instead of overloading recent news.
5. **Research Assistant:** run a documented default in one click, or change task, horizon, event, or one-run agent.
6. **System Status:** set shared agent and workflow defaults. Industry overrides take precedence and are not overwritten by later global changes.

Relative to the previous baseline, default source discovery and general collection budgets are 1.5× and paper collection is 2×. Papers cover both established topics and frontier candidates that may become new industry directions. Frontier candidates remain `candidate` until industry and evidence checks succeed.

## Data, privacy, and states

- SQLite is authoritative for entities, evidence, sources, jobs, reviews, and schedules. Raw material, Markdown, HTML, and charts remain in the local data directory.
- Industry data, generated artifacts, logs, credentials, build output, and runtime caches are ignored by Git and must not be committed.
- Deleted industries and daily items first enter recoverable trash. Stop active jobs and back up the complete data directory before permanent deletion.
- `candidate` is unverified; `collected` means retrieved; `verified/corroborated` has passed the applicable evidence policy; `draft_review_required` is model-written but still needs human review.
- A reachable URL is not sufficient evidence. Accepted assertions also require semantic support, reproducible locators, numeric/unit consistency, claim-type policy, required independent corroboration, and conflict checks.
- “Not observed” does not mean “does not exist.” Coverage gaps, failed sources, and uncertainty remain visible. A first run with no stable baseline reports insufficient data, not false drift.

## Run from source (developers)

Git, Python 3.11+, Node.js 20+, and npm are required:

```bash
git clone https://github.com/JoenardoQ/Industry-Intelligent-Dog.git
cd Industry-Intelligent-Dog
./run_intdog.sh
```

The launcher prepares an isolated runtime in an ignored local location. Do not use a read-only source directory. Windows developers may run the script through WSL; end users should use the Windows installer.

Common verification commands:

```bash
.venv/bin/python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests
npm test --prefix DomainIntelWeb
npm run build --prefix DomainIntelWeb
npm test --prefix DomainIntelDesktop
```

## Repository layout

| Directory | Responsibility |
| --- | --- |
| `DomainIntelSearch` | Search, collection, deduplication, evidence/knowledge algorithms, reports |
| `DomainIntelWeb` | React workbench and local FastAPI |
| `DomainIntelApp` | Startup, job runtime, and environment management |
| `DomainIntelDesktop` | Electron shell and three-platform packaging |
| `DomainIntelData` | Local-data templates; generated industry data stays out of Git |

Further reading: [architecture](DESIGN.md) · [installation and agent connections](docs/onboarding-and-installation.md) · [source policy](docs/source-governance.md) · [release gates](docs/release-readiness.md).
