# Open-source architecture survey

Date checked: 2026-08-30

## Decision

No mature project is a clean drop-in replacement for IntDog. The strongest path is
a staged web-workbench migration: keep the tested Python intelligence/domain layer
behind explicit APIs initially, replace the Tk presentation layer with a React
workbench, and then replace backend internals only where measured weaknesses
justify it. This is a strangler migration, not a permanent promise to retain the
current backend.

The first runnable target should be a local web/PWA application launched by the
existing shortcut. Tauri is a later packaging option, not the first milestone:
the current machine has Node 24 and Python 3.12 but no Rust toolchain, so choosing
Tauri now adds a large environment and packaging dependency before product parity.

## Whole-product references

| Project | What IntDog should learn | Why it is not the base |
| --- | --- | --- |
| [WorldMonitor](https://github.com/koala73/worldmonitor) | dense monitoring layout; stale-on-error; in-flight deduplication; circuit breakers; adaptive polling; source corroboration; visible system health | AGPL-3.0 platform code; map/geopolitical event model conflicts with cross-industry knowledge and learning; branding is separately protected |
| [OpenCTI](https://github.com/OpenCTI-Platform/opencti) | evidence-bearing entities and relationships; confidence and first/last-seen time; connector model; analyst-facing graph workflows | cyber/STIX ontology is too specialized; full deployment is operationally heavy; adopting its whole platform would replace one domain mismatch with another |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | local-first document ingestion, workspace-scoped research, provider abstraction, usable agent conversation | research chat is only one IntDog surface; it lacks industry-chain monitoring and evidence-quality gates; wholesale adoption would subordinate the knowledge system to chat |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | provider/fetcher contracts and `connect once, consume everywhere` data access | finance-first and AGPL; its open platform is useful as an optional financial provider, not the general industry ontology or UI |
| [Apache Superset](https://github.com/apache/superset) | mature analytic dashboards and chart composition | BI over structured tables does not supply collection, provenance, entity graphs, research agents, or the domain lifecycle; embedding it would be heavier than focused charts |

Young demonstration repositories such as Lynx, PaperMind, and IntellyWeave are
useful idea sources but are not accepted as foundations without stronger release,
maintenance, security, and migration evidence.

## Recommended component stack

| Concern | Candidate | License | Decision |
| --- | --- | --- | --- |
| UI shell | React + TypeScript + Vite | permissive | recommended for the new workbench; broad ecosystem and fast local builds |
| accessible components | [shadcn/ui](https://github.com/shadcn-ui/ui) primitives and patterns | MIT | recommended; copy only selected components and establish IntDog tokens instead of copying a demo theme |
| tables | [TanStack Table](https://github.com/TanStack/table) plus virtualization | MIT | recommended for Daily, Sources, Entities, Tasks; native sort/filter/select behavior replaces bespoke widgets |
| directed graphs | [React Flow](https://github.com/xyflow/xyflow) | MIT | recommended for value-chain and entity relation navigation |
| analytical charts | [Apache ECharts](https://github.com/apache/echarts) | Apache-2.0 | recommended for time series, category/source mix, coverage, and report visuals |
| Markdown | [react-markdown](https://github.com/remarkjs/react-markdown), `remark-gfm`, `rehype-sanitize` | MIT ecosystem | recommended safe reader; supports CommonMark/GFM without raw HTML execution |
| API | FastAPI + Pydantic | MIT | recommended migration boundary around Python domain services; generated OpenAPI becomes the UI/backend contract |
| local storage | SQLite + FTS5 initially | public domain | retain initially because it is already canonical, transactional, portable, and tested; reconsider DuckDB only for measured analytical workloads |
| desktop delivery | local PWA first; [Tauri](https://github.com/tauri-apps/tauri) later | MIT/Apache-2.0 | PWA first for fastest reliable launch; Tauri only after parity and explicit Rust/toolchain approval |

## Target topology

```text
Shortcut / PWA
      |
React workbench  -- typed HTTP/SSE -->  Local API + job supervisor
      |                                      |
Tables / graphs / Markdown             Domain services
                                             |
                              collectors -> normalize -> resolve
                                             |
                              evidence-aware canonical store
                                             |
                                reports / exports / email
```

Key rules:

- UI reads typed view models; it never opens SQLite or artifact files directly.
- Collectors return normalized records and explicit failures. They cannot write
  around the domain service.
- Jobs expose queued/running/progress/partial/failed/completed states and stream
  representative events over SSE; polling is a fallback.
- All time ranges use one timezone-aware window policy and all derived facts carry
  an as-of timestamp.
- Cached/stale data is labelled; failure never silently becomes empty data.
- The product is useful without an LLM. Models enrich or synthesize after factual
  retrieval, and their output remains draft until evidence gates pass.

## Migration slices

1. Contract slice: read-only API for industries, overview, daily, sources, entities,
   reports, jobs, and status; shared window/source-attribution tests.
2. Workbench slice: new responsive shell, Overview+Knowledge, Daily table, three
   period buttons, safe Markdown, and directed graphs.
3. Operations slice: generation actions, Research/Lab parity, SSE logs, scheduler
   recovery, stale/error states, and shortcut-managed lifecycle.
4. Cutover slice: visual/full-flow parity verification; only then retire Tk routes.
5. Later evidence-based changes: replace storage, scheduler, or collector internals
   only if profiling or reliability tests demonstrate a concrete need.

## Explicit non-decisions

- Do not fork or copy WorldMonitor/OpenCTI/OpenBB platform code.
- Do not introduce Airbyte, Superset, Neo4j, Redis, Celery, Electron, or Tauri merely
  because they are mature. Each adds an operational system and must solve a measured
  bottleneck first.
- Do not delete the Tk client until the web workbench passes parity and startup tests.
- Do not install the proposed npm/Python dependencies until the dependency and
  framework-migration gate is approved.
