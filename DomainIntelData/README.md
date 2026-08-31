# DomainIntelData

[中文文档](README.zh-CN.md)

`DomainIntelData` is IntDog's local data layer. It runs no crawler or model. It stores industry configuration, source catalogs, research state, intelligence, and reports. Stop active jobs before copying the complete directory as a backup.

## Directory contract

```text
DomainIntelData/
├── intdog.sqlite3                 # canonical facts, search, tasks, audit
├── _jobs/                         # durable application job state
├── _trash/                        # recoverable application deletions
└── <Industry>/
    ├── config.json
    ├── sources.json
    ├── one_time/
    │   ├── knowledge/             # subfields, value chain, entities, learning
    │   ├── landscape/             # tiers, Watchlist, snapshots
    │   ├── intelligence/          # evidence, sources, scenarios, agenda
    │   ├── reports/               # reports, charts, tasks
    │   ├── research/bootstrap/    # candidates, logs, stage state
    │   └── tasks/
    └── periodic/
        ├── daily/<date>/          # six daily categories
        ├── weekly/
        ├── monthly/
        └── quarterly/
```

Optional directories appear only after their feature runs. Their absence does not by itself indicate corruption. `_jobs/` is operational audit state, not report content.

Versioned analysis packages live under `one_time/intelligence/artifacts/<kind>/<artifact_id>/` with data, Markdown, optional Mermaid, and a hash manifest. `latest/<kind>.json` advances only after the complete package validates. Legacy root files are compatibility views, not the version authority.

Research agenda items have mutable audited status. Research tasks preserve queries, acceptance criteria, evidence budgets, and result links. Creating a task does not call a model or incur a fee.

## Write ownership

| Writer | Authorized content |
| --- | --- |
| Search | Bootstrap, collection, verification, knowledge, analysis, reports |
| App | Industry registry, manual sources, schedules, recoverable deletion |
| User | Prefer App actions or reviewed migration tools |

Do not hand-edit JSON while App or Search is writing the same industry. Structured mutations go through `intdog_core` repositories and application services with transactions, WAL, industry locks, migrations, and atomic compatibility writes.

SQLite is the canonical fact store. JSON is a portable, rebuildable materialized view. Transactions record dirty views; successful atomic JSON replacement clears them. `reconcile-data` rebuilds SQLite → JSON. Only explicit legacy migration imports JSON → SQLite.

## Daily item

Collectors may add fields, but the core shape is stable:

```json
{
  "title": "Event title",
  "abstract": "Factual summary",
  "url": "https://example.com/original",
  "source": "Publisher name",
  "date": "2026-08-29",
  "category": "news",
  "origin": "domestic",
  "source_tier": 1,
  "credibility": "collected",
  "source_count": 1,
  "references": ["https://example.com/original"],
  "ranking_score": 0.78,
  "classification_reason": "Matched industry terms and entities"
}
```

`origin` describes publisher origin; do not infer it casually from language or domain. References must support the item. Search result and aggregator pages do not replace primary citations.

## Data model

| Layer | Content |
| --- | --- |
| Raw | Original response, page, attachment, retrieval time, content hash |
| Normalized | Canonical document, publisher, author, language, text, URL |
| Intelligence | Entities, events, claims, evidence, relations, gaps, conflicts |
| Artifacts | Reports, charts, task packages, and exports |

Weekly, monthly, and quarterly are query/generation windows over shared facts, not separate truth stores. Large raw files and Markdown stay in the filesystem; normalized structured facts enter SQLite.

Core identifiers include `source_id`, `document_id`, `entity_id`, `event_id`, `claim_id`, `evidence_id`, `report_id`, and `run_id`. Names, titles, and URLs alone are not primary keys.

Records preserve:

- `published_at`, `observed_at`, `retrieved_at`, and `valid_from/valid_to`;
- Chinese/English names, aliases, historical names, external IDs, region, and disambiguation confidence;
- `supports`, `contradicts`, and `qualifies` evidence relationships;
- provider/model, prompt version, input document IDs, code version, parameters, and human edits;
- collection gaps and failures, because “not collected” is not “does not exist.”

## Status semantics

| Status | Meaning |
| --- | --- |
| `candidate` | Discovered but not audited |
| `collected` | Retrieved; claim not yet established |
| `verified` / `corroborated` | Primary evidence or independent corroboration |
| `draft_review_required` | Generated draft awaiting human review |
| `reviewed` / `published` | Granted only by an explicit human workflow |

Verification applies to a claim, not an entire document or entity. Preserve supporting, qualifying, and contradicting material together. Syndicated copies from one upstream source count as one evidence cluster. Source tier, reachability, corroboration, and review status remain separate fields.

## Format rules

- JSON uses UTF-8 and may retain Unicode display names.
- Folder identifiers are stable and cross-platform-safe; display names are separate.
- Dates use ISO `YYYY-MM-DD`; timestamps include a timezone.
- Money stores value, currency, accounting basis, and as-of date.
- Normalize URLs for deduplication while retaining original audit references.
- Schema changes update Search writers, App readers, migrations, and tests together.
- Readers tolerate legacy files without `schema_version`.
- Algorithmic scores retain components, version, and thresholds.

Database schema versions are ordered and registered. Current migrations include immutable analysis snapshots, research agenda/history/tasks, directed temporal value-chain edges, and calculated edge evidence. Human-readable constraints begin in [`skill/spec.md`](skill/spec.md); executable truth also includes schemas, repositories, migrations, and tests.

## Backup and recovery

1. Stop application scheduling and active Search commands.
2. Copy the complete `DomainIntelData/` tree.
3. Restore supported deletions from `_trash/`; emptying trash can make recovery impossible.
4. After restoring an older backup, run `verify`, `doctor`, and when required `reconcile-data`.

Never store API keys here. Before any public commit, inspect research logs for accidental prompts, email addresses, access tokens, or confidential material. Production databases and generated industry knowledge are ignored by Git and must not be attached to a source release.
