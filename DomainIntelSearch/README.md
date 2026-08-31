# DomainIntelSearch

[中文文档](README.zh-CN.md)

`DomainIntelSearch` is IntDog's research and collection engine. It is the only layer that directly calls websites, models, and external APIs. Crawlers, providers, and report generators write through the shared `intdog_core`; they do not depend on the desktop shell.

## Install

```bash
cd DomainIntelSearch
python -m pip install -e .
python -m src.main --help
```

The default data root is `../DomainIntelData`. Use `--industry` for a name or alias and `--folder AI` or `--folder Chips` for an exact folder.

## Execution modes

| Mode | Authentication | Behavior |
| --- | --- | --- |
| Codex subscription | Local ChatGPT/Codex login | Search and generate review-required drafts |
| Provider API | Provider API key | Generate drafts; charges may apply |
| Task package | None | Write prompt/task JSON without calling a model |

Codex mode does not read `OPENAI_API_KEY`. A Codex `401` means the login is absent from the environment running IntDog. Provider keys are environment variables and must not be committed.

## Recommended workflow

```bash
# Create folders, seed sources, and task skeletons without network/model calls.
python -m src.main init-industry --industry "artificial intelligence"

# Discover and audit sources, then build value-chain and entity coverage.
python -m src.main bootstrap-industry --industry "artificial intelligence" --provider codex

# Resume a persisted failed stage.
python -m src.main resume-bootstrap --industry "artificial intelligence" --provider codex

# Collect the daily six categories.
python -m src.main crawl-daily --industry "artificial intelligence"

# Diagnose quality and coverage.
python -m src.main doctor --industry "artificial intelligence"
python -m src.main verify --industry "artificial intelligence"
```

Bootstrap order is source gate → value-chain gate → entity-coverage gate. Candidate output and stage status are persisted under `one_time/research/bootstrap/`; a failed upstream gate cannot be presented as downstream success.

Long-duration reports first require time-stratified evidence. Backfill is resumable, deduplicated, and evaluated by record count, time-bucket coverage, and publisher diversity:

```bash
python -m src.main backfill-history --folder AI --kind biennial
python -m src.main backfill-history --folder AI --kind fiveyear
```

GDELT and dated Google News RSS are built-in historical providers. OpenAlex enrichment is optional and reads `OPENALEX_API_KEY`. See [history collection](../docs/history-collection-method.md).

## Research method

```text
industry → subfields → value-chain activities → products and technologies
         → companies, labs, and people → standards and policy
         → market and capital activity → events → claims and evidence
```

Discovery uses an open-world assumption. Each pass preserves verified entities, unresolved candidates, explicit exclusions, and uncovered nodes. Coverage is measured across region × subfield × value-chain node × entity type × source type × event type × time. Search stops by marginal yield, coverage, and diversity—not an arbitrary Top 10.

The coverage planner persists cells and attempts. Proposed URLs and counts remain `planned` until retrieval, normalization, and verification establish actual yield. Smaller companies, startups, university labs, independent institutes, standards groups, and key people are explicit discovery targets.

## Command map

| Goal | Commands |
| --- | --- |
| Initialize | `init-industry`, `bootstrap-industry`, `resume-bootstrap` |
| Sources | `refresh-sources`, `discover-sources`, `enrich-sources` |
| Collect | `crawl-daily`, `crawl-weekly`, `crawl-monthly`, `crawl-quarterly` |
| Generate | `generate-period`, `report-tasks`, `generate-report`, `generate-deep-report` |
| Impact and landscape | `impact`, `generate-impact`, `landscape` |
| Knowledge | `knowledge`, `kg`, `modules`, `query` |
| History | `backfill-history` |
| Quality | `verify`, `doctor`, `evaluate-quality` |
| Intelligence Lab | `compile-evidence`, `observe-sources`, `simulate-chain`, `plan-boundaries`, `run-lab` |
| Data maintenance | `migrate-data`, `reconcile-data` |
| Agent access | `mcp-serve` |

`crawl-daily` returns `completed` only when all six categories succeed, `partial` when some succeed, and `failed` when none succeed. Partial and failed runs use nonzero exit codes and do not advance the scheduler checkpoint. The default Web workflow disables email.

CLI commands use real subparsers:

```bash
python -m src.main generate-period --help
python -m src.main simulate-chain --folder Chips --event "advanced packaging capacity constrained"
python -m src.main create-research-task --folder AI --agenda-id <id> --budget 20
python -m src.main audit-artifacts --folder AI --repair-latest
```

## Source policy

Sources use nine categories: `official`, `associations`, `blogs`, `platforms`, `self_media`, `news`, `journals`, `financials`, and `finance`.

- Prefer government, regulatory, statistical, standards, corporate disclosure, and peer-reviewed primary material.
- Use media for corroboration; social and self-media posts are leads.
- Domestic/foreign balance is a coverage objective, not a fabricated quota.
- Preserve valuable non-crawlable or paywalled sources as `recommended_manual`.
- Preserve manual additions and allow cross-industry source reuse.

Source quality and claim corroboration are separate. Syndicated copies of one announcement count as one evidence cluster. Adapters record explicit capability and `fresh`, `stale`, `degraded`, `failed`, `manual`, or `unconfigured` state with bounded retry.

## Algorithm direction

1. Expand bilingual aliases, technologies, products, nodes, entities, and event queries per source class.
2. Combine canonical URL, content hash, persistent Story, and audited merge/split deduplication.
3. Resolve canonical entities with aliases, historical names, external identifiers, and temporal roles.
4. Store `supports`, `contradicts`, and `qualifies` claim–evidence relationships.
5. Rank relevance, source quality, recency, importance, evidence, novelty, and diversity separately.
6. Evaluate relevance, recall, duplication, entity linking, citation validity, chain classification, and numeric traceability.

Scores retain components, algorithm version, and thresholds. Conflicting evidence keeps its date, scope, and provenance instead of being forced into one answer.

## Troubleshooting

- Planning does not finish: inspect `bootstrap_status.json`, then resume the saved stage.
- Codex `401`: authenticate in the same host environment.
- Provider key: use the provider variable or `INTDOG_LLM_API_KEY`; remote API bases require HTTPS.
- Collection keys: `NEWSAPI_KEY`, `GNEWS_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`; email compatibility uses `INTDOG_SMTP_PASSWORD`.
- `403`, `429`, timeout: keep the failed observation, apply bounded retry, and continue other sources.
- Task exists but report does not: collection/task metadata is not prose; run a generation command.
- Low domestic recall: inspect reachability, enrich authoritative domestic sources, then run `doctor`.

All output enters `DomainIntelData/<Industry>/`. See the [Data contract](../DomainIntelData/README.md), [Chinese Data contract](../DomainIntelData/README.zh-CN.md), and [Intelligence Lab contract](INTELLIGENCE_LAB.md).

## Verification

```bash
python -m pytest tests -q
python scripts/check_repo.py
```

Model output remains `draft_review_required`. Market capitalization, imports/exports, policy, and investment-sensitive claims require date, currency, primary-disclosure, and citation checks.
