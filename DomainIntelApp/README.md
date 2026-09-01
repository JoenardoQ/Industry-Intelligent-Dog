# DomainIntelApp

[中文文档](README.zh-CN.md)

`DomainIntelApp` owns source/development startup, isolated runtimes, persistent jobs, and Windows + WSL shortcuts. The product UI is the React/FastAPI workbench; the retired Tk workbench is not a second application implementation. Native Electron packaging lives in `DomainIntelDesktop`.

End users should install the platform-native Beta (`.exe`, `.dmg`, or `.AppImage`).
The source launcher below is a retained developer compatibility path and is excluded
from release resources.

## Start

From the repository root:

```bash
cd "/home/joenardo/My Projects/IntDog"
./run_intdog.sh
```

First launch prepares `.intdog-runtime/`, installs the locked Web dependencies, creates a production build, starts the localhost API, and opens a dedicated app-mode window. Linux and Windows runtimes are kept separate. Override the data location with `DOMAIN_INTEL_DATA_ROOT` before launch.

### Windows entry points

For the current WSL-home deployment, use the generated Windows desktop shortcut. Recreate it from PowerShell when needed:

```powershell
powershell -ExecutionPolicy Bypass -File .\create_shortcut.ps1
```

Only a native Windows checkout should run `run_app.bat`. The WSL launcher resolves the `/home` repository, records logs under the user's local application data, and does not depend on the retired `/mnt/d` copy.

## First use

1. Create or select an industry.
2. Open industry initialization and select Codex subscription, provider API, or task-package mode.
3. Allow source, value-chain, and entity gates to complete in order.
4. Collect daily intelligence and generate periodic, industry, or deep reports as required.

Codex subscription mode uses the login visible in the same Windows/WSL environment and does not require an API key. Task-package mode creates a prompt package, not a completed report.

No-model live collection is separate from a task package and remains subject to the
`NOM-01` external oracle. Agent/API generation is never treated as reviewed fact.
Background scheduling is opt-in; users can revoke it from System Status. OS secure storage
holds provider credentials; a one-shot pipe transfers them to the sidecar without
environment disclosure. Windows, macOS, and Linux uninstallers retain the user data
directory; disable the background service before uninstalling the current Beta.

## Workbench

| Page | Responsibility |
| --- | --- |
| Overview | Linked counts, knowledge structure, directed value chain, key entities |
| Daily Intelligence | Server search, sort, pagination, page selection, recoverable deletion |
| Research Products | Weekly/monthly/quarterly, industry, deep, and impact reports |
| Sources | Categories, governance role, health, timestamps, and manual sources |
| Research Assistant | Agenda, evidence, scenarios, history coverage, Intelligence Lab |
| Task Center | Durable states, progress, representative logs, retry and cancellation |
| System Status | API/database state, automation, industry management, recovery, shutdown |

The global industry selector is the only workbench context. Large lists are searchable, sortable, bounded, and paginated. Missing measurements render as unknown rather than fabricated zeroes. Source cards preserve canonical name, category, region, tier, access, reachability, monitoring, and publisher fields.

Industry management supports create, rename, recoverable archive, and restore. Manual sources survive automated refreshes and may be reused across industries. Valuable paywalled or non-crawlable sources may be manual recommendations; they are not reported as successful collection.

## Knowledge exploration

The interface supports movement from industry to subfield, value-chain node, product, technology, company, research group, person, policy, event, claim, and evidence. It shows leaders, long-tail entities, candidates, coverage gaps, temporal roles, citations, and conflicting evidence. Beginner/intermediate/expert changes explanation depth, not the underlying knowledge universe.

Directed value-chain views expose ordering, entity counts, evidence coverage, and uncovered nodes. Intelligence Lab scenarios are explainable heuristics and never become facts automatically.

## Generation and scheduling

- Daily collection writes news, papers, GitHub, funding, hiring, and leadership items.
- Weekly/monthly/quarterly collection aggregates evidence and task metadata.
- Explicit generation actions create Markdown and chart JSON.
- The default Web scheduler is the only schedule owner and always sets `INTDOG_DISABLE_EMAIL=1`.
- Restart catch-up uses leases and period keys to avoid duplicate enqueue.

Every task has a `run_id` and durable `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`, or `interrupted` state. Logs are bounded and credential-redacted. Cancellation applies to the process tree; non-success states do not advance schedule checkpoints.

## Deletion and recovery

Bulk deletion displays the selected count. Industries and supported daily batches move to `DomainIntelData/_trash/`; permanent deletion is outside the normal UI. Same-name restoration is rejected rather than overwritten. Do not delete or manually edit an industry while its collection or report task is running.

## Desktop trust boundary

The launcher generates an ephemeral session capability. The API listens only on `127.0.0.1`, validates Host and Origin, and requires the session capability for mutations. External navigation is restricted to HTTPS. Closing IntDog requests graceful API shutdown and then applies a bounded process fallback.

The native distribution uses one Electron shell and one PyInstaller sidecar for both FastAPI and research CLI commands. Mutable data is stored under the operating system's user-data directory, never inside the installed application. Windows, macOS, and Linux packages contain only their native runtime.

## Troubleshooting

- Blurred text: use the system-recommended scale and confirm the shortcut targets the current `/home` launcher.
- Stuck on Planning: inspect the current bootstrap stage and resume it; do not repeatedly erase the industry.
- `401 Unauthorized`: renew Codex login in the same environment, or inject the provider key into the app process.
- Missing report: task JSON and collection metadata are not reports; run the corresponding generation action.
- Empty GitHub category: no project may have passed relevance, deduplication, and quality gates for that window.
- Low domestic coverage: check reachability, add authoritative domestic sources, and run coverage diagnostics.

See the [Search guide](../DomainIntelSearch/README.md), [Chinese Search guide](../DomainIntelSearch/README.zh-CN.md), and [Data contract](../DomainIntelData/README.md).

## Verification

```bash
python -m pytest DomainIntelApp/tests DomainIntelWeb/tests -q
npm test --prefix DomainIntelWeb
npm run build --prefix DomainIntelWeb
npm test --prefix DomainIntelDesktop
```

Tests use isolated temporary data. They must not mutate the production database or send email.
