# Subproject 2: Data Credibility and Source Coverage Engine Specification

Status: Approved, awaiting implementation verification
Dependency: Subproject 1 Assertion/Fact states and audit interfaces

## Objective

Upgrade static seed sources and one-time model lists into a traceable system for multi-round source search, selection, review, continuous governance, and open-world coverage.

## Source Discovery Activities

Schema 15 adds:

- `source_campaigns`: industry, target categories, status, rounds, budget, and stopping or pause reason.
- `source_queries`: language, query family, coverage dimensions, query text, round, and execution result.
- `source_candidates`: canonical URL, publisher, ownership, source attributes, score, selection status, and reason.
- `source_reviews`: identity, ownership, URL, access, human actions, and periodic review records.

Each source-mapping run contains at least an authoritative baseline round and a gap-expansion round. Query dimensions are `language × region × subdomain × chain_stage × entity_type × source_type × time_horizon`; Chinese and English queries are stored separately.

## Selection and Stopping

- Each of the nine source categories targets 8–10 qualified publishers; the candidate pool must exceed the selection target.
- Scoring inputs include source identity, primary/secondary status, historical stability, update frequency, citation quality, access method, publisher duplication, new coverage, and contribution to China gaps.
- Official primary sources may be activated automatically only when identity, ownership, and URL all pass verification; media, platforms, self-media, leadership, and individual sources require human review.
- Convergence is reached only when two consecutive rounds produce no new qualified sources, or new items only repeat publishers and coverage units.
- Budget, rate limiting, login walls, paywalls, network interruptions, and unavailable Providers may enter only `paused`; they cannot be recorded as convergence.

## Four-Layer Credibility

`Source → Document → Assertion → accepted Claim(Fact)` is the only promotion path. Documents retain author, publisher, time, language, hash, and snapshot references. When duplicate content is merged, relationships to different publishers are retained. Conflicting assertions enter `disputed` and cannot be overridden by a simple majority vote.

## Cross-Day Signal Momentum and System Drift

Stories store immutable observations by local calendar day: first/last seen time, daily rank and score, independent-publisher count, evidence strength, classification result, and algorithm version. Adjacent observations deterministically produce `new / heating / tracking / cooling / unresolved` and expose day-over-day changes in rank, score, independent sources, and evidence strength plus a seven-day trend. Models cannot invent state labels, and syndicated duplicates cannot manufacture momentum.

The system also stores seven-day and thirty-day quality series for source success and latency, useful output, duplication rate, independent-publisher rate, citation failure, classifier unknown rate, human correction rate, top-ranked-item ignore rate, value-chain-node coverage change, and fixed-evaluation-set quality under the same algorithm version. Version changes create separate segments so an algorithm upgrade is not misreported as data drift; threshold alerts link to raw observations and an actionable diagnostic.

SQLite remains authoritative for canonical entities, evidence, tasks, reviews, and transactions. Parquet/DuckDB are not runtime dependencies in this round. A prototype is considered only when documents exceed 500,000, long-period query P95 exceeds one second, SQLite aggregation materially blocks writes, or raw observations make backups unacceptably large. Any columnar layer is one-way derived data; SQLite remains authoritative and there is no second writable Schema.

## Entities and Industry Value-Chain Open-World Coverage

Coverage objects include enterprises, research groups, government institutions, associations, investment institutions, people, products, technologies, standards, and policies. Each object stores a canonical name, aliases, region, type, industry value-chain stage, role, relationships, validity period, status, evidence, and confidence; relationships must point to verifiable Documents/Assertions and cannot be produced only by a model description.

The system maintains a `source_type × region × subdomain × chain_stage × entity_type` coverage matrix and generates the next-round expansion frontier from uncovered, high-importance, and low-confidence cells. Applicable cells first target at least 3 qualified representatives, then expand high-centrality, high-market-impact, or high-research-value endpoints to 8–10; when the objective is objectively insufficient, retain the gap rather than duplicate entities or lower the threshold. Identity merging combines canonical names, aliases, official website domains, registration/securities/institution identifiers, affiliations, and time; ambiguous merges require human review.

The stopping condition is not a fixed Top N. The campaign may converge only when the coverage threshold is reached and two consecutive rounds produce no new qualified entities, industry value-chain nodes, evidence-backed relationships, or important coverage units. The system always marks “known coverage/completeness not proven.”

## API and UI

- `POST /api/industries/{folder}/source-campaigns`
- `GET /api/industries/{folder}/source-campaigns`
- `GET /api/industries/{folder}/source-campaigns/{campaign_id}`
- `POST /api/industries/{folder}/source-candidates/{candidate_id}/review`
- `POST /api/industries/{folder}/sources/{source_id}/reassess`
- `GET /api/industries/{folder}/coverage-matrix`
- `POST /api/industries/{folder}/coverage-expansions`
- `POST /api/industries/{folder}/entity-candidates/{candidate_id}/review`
- `GET /api/industries/{folder}/stories/{story_id}/momentum`
- `GET /api/industries/{folder}/quality-drift`

The sources page adds candidate, active, manual, reserve, rejected, and gap views; it displays the query ledger, rounds, selection/rejection reasons, publisher identity, access status, and reassessment action. The coverage workbench displays cross-dimensional gaps by industry value-chain stage, entity category, and region, along with the expansion frontier, candidate identities, merge rationale, and relationship evidence.

## Compatibility and Governance

- Existing `sources`, `industry_sources`, `publishers`, `source_health`, and coverage tables continue as part of authoritative storage.
- The same Publisher/Source may be reused by multiple industries, sharing identity and health information; selection rationale, priority, coverage contribution, and enabled/disabled status are stored per industry, avoiding publisher duplication while allowing independent industry governance.
- Existing seed sources serve as initial active candidates and do not automatically receive trusted status.
- `TRUSTED_DOMAINS` may serve only as an identity hint audited in code; domains outside the list may be verified through persistent review records.
- Downgrading an active source does not delete historical documents, assertions, or evidence.

## Acceptance

- Every source is traceable to its discovery query, round, selection or rejection reason, and latest review.
- At least two rounds and convergence/pause semantics are enforced by the state machine, not by a prompt-text convention.
- When a category has fewer than 8 sources, the executed queries, candidate count, rejection reasons, and gaps are displayed.
- China gaps are prioritized while sharing a uniform quality threshold.
- Near-duplicates, multiple URLs, reposts, same-owner sources, and cross-language boundaries all have deterministic deduplication results.
- Categories such as enterprises, research groups, institutions, people, products, technologies, standards, and policies have explainable breadth/depth thresholds; industry value-chain relationships are traceable to evidence, and ambiguous identities are not merged automatically.
- Story momentum can be recomputed from immutable daily observations; rerunning the same inputs is idempotent, syndication does not add independent sources, and 04:00 boundaries, missing days, and algorithm-version changes have deterministic semantics.
- Seven-day/thirty-day drift metrics record denominators, baselines, thresholds, versions, and raw-observation links; fixed-evaluation-set degradation is detectable rather than showing collection counts alone.
- DuckDB/Parquet runtime dependencies are absent until a columnar trigger is met; a later prototype must still preserve SQLite as the sole write authority.
- Source discovery and review, deduplication and coverage, and data credibility P0 risks all have execution evidence.
