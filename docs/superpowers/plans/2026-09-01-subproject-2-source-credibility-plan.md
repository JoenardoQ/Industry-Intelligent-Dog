# Subproject 2: Data Credibility and Source Coverage Engine Implementation Plan

> **Execution requirement:** Use `superpowers:subagent-driven-development` to execute tasks and perform two-stage review.

**Objective:** Establish persistent two-round source discovery, candidate selection, human review, periodic reassessment, deduplication, and open-world coverage.
**Architecture:** Source campaigns and candidates use an independent repository mixin; existing source tables continue to store the active catalog; prompts produce candidates only and do not control the state machine.
**Tech stack:** Python, SQLite, FastAPI, React, deterministic scoring, and injectable search adapters.
**Specification:** `docs/superpowers/specs/2026-09-01-subproject-2-source-credibility.md`

## Global Constraints

- Target 8–10 for each category, but prioritize the quality threshold; shortages must be explicit.
- Official primary sources may be automatically activated only when identity, ownership, and URL all pass.
- Network, rate-limit, and budget errors may only pause; they cannot be recorded as convergence.
- Do not delete historical documents or evidence; do not run production crawling or paid models.

---

### Task 1: Persist Source Campaigns, Queries, Candidates, and Reviews

**Files:**
- Create: `DomainIntelSearch/intdog_core/source_repository.py`
- Modify: `DomainIntelSearch/intdog_core/repository.py`
- Test: `DomainIntelSearch/tests/test_source_campaigns.py`

**Interfaces:**

```python
class SourceRepositoryMixin:
    def create_source_campaign(self, folder: str, targets: list[str], budget: int) -> dict: ...
    def record_source_query(self, campaign_id: str, *, round_no: int,
                            language: str, family: str, dimensions: dict,
                            query: str, outcome: dict) -> dict: ...
    def upsert_source_candidate(self, campaign_id: str, item: dict) -> dict: ...
    def review_source_candidate(self, folder: str, candidate_id: str, *,
                                decision: str, actor: str, reason: str) -> dict: ...
```

- [ ] **Step 1: Write Schema 15 RED tests**

Cover idempotent migration, canonical-URL uniqueness, provenance from multiple queries for one candidate, reuse of the same Publisher across industries with independent industry state, non-overwritable review history, and legal campaign-state transitions.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_source_campaigns.py -q`

- [ ] **Step 3: Implement Schema 15 and the repository mixin**

States: `planned→running→paused/converged/failed`; candidate states: `candidate→manual_review/active/reserve/rejected`.

- [ ] **Step 4: Run GREEN and legacy-source regression**

Run: `python -m pytest DomainIntelSearch/tests/test_source_campaigns.py DomainIntelSearch/tests/test_intdog_core.py DomainIntelSearch/tests/test_dedup_governance.py -q`

### Task 2: Implement Bilingual Query Families and the Two-Round Campaign State Machine

**Files:**
- Create: `DomainIntelSearch/src/source_campaign.py`
- Modify: `DomainIntelSearch/src/source_discovery.py`
- Modify: `DomainIntelSearch/src/coverage_execution.py`
- Modify: `DomainIntelSearch/src/research_bootstrap.py`
- Test: `DomainIntelSearch/tests/test_source_campaigns.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class CampaignOutcome:
    status: Literal["paused", "converged", "running"]
    qualified_by_category: dict[str, int]
    candidate_total: int
    stopping_reason: str

def plan_query_families(industry: dict, gaps: list[dict]) -> list[dict]: ...
def run_campaign_round(repo, campaign_id: str, *, search: SearchAdapter) -> CampaignOutcome: ...
```

- [ ] **Step 1: Write RED state and boundary tests**

Verify Chinese/English queries, nine categories, first-round authoritative baseline, second-round gap expansion, candidate pool larger than the selection target, convergence only after two consecutive rounds with zero new items, and timeout/403/429/insufficient-budget as paused.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_source_campaigns.py DomainIntelSearch/tests/test_coverage_planning.py -q`

- [ ] **Step 3: Implement a pure state machine and make prompts return candidates only**

Remove the “accessible means active” behavior; `execute_coverage()` writes only candidates and query results.

- [ ] **Step 4: Run GREEN and bootstrap regression**

Run: `python -m pytest DomainIntelSearch/tests/test_source_campaigns.py DomainIntelSearch/tests/test_coverage_planning.py DomainIntelSearch/tests/test_core.py -q`

### Task 3: Implement Identity, Representativeness, Composition, and Periodic Review

**Files:**
- Modify: `DomainIntelSearch/intdog_core/source_trust.py`
- Modify: `DomainIntelSearch/src/source_governance.py`
- Create: `DomainIntelSearch/src/source_review.py`
- Test: `DomainIntelSearch/tests/test_dedup_governance.py`

- [ ] **Step 1: Write RED decision-table tests**

Cover official automatic activation, mandatory human review for media/self-media, same-owner duplication, source ownership changes, content farms, long-term zero marginal value, manual addition, 7/8/10/11-source boundaries for each category, and China-gap prioritization.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_dedup_governance.py -q`

- [ ] **Step 3: Implement explainable scoring and review results**

Every result must output `score_components`, `decision`, `reason`, and `review_due_at`; hard-coded domains are identity hints, not the sole verification path.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest DomainIntelSearch/tests/test_dedup_governance.py DomainIntelSearch/tests/test_source_campaigns.py -q`

### Task 4: Complete Document/Assertion Deduplication and Conflict Gates

**Files:**
- Modify: `DomainIntelSearch/src/deduplication.py`
- Modify: `DomainIntelSearch/src/verification.py`
- Modify: `DomainIntelSearch/intdog_core/evidence_repository.py`
- Test: `DomainIntelSearch/tests/test_dedup_governance.py`
- Test: `DomainIntelSearch/tests/test_agent_evidence.py`

- [ ] **Step 1: Write RED property and metamorphic tests**

The same URL with tracking parameters, identical content at different URLs, reposts, the same event across languages, multiple same-owner sites, and independent publishers must produce distinct and stable merge results; changing input order must not change output.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_dedup_governance.py DomainIntelSearch/tests/test_agent_evidence.py -q`

- [ ] **Step 3: Implement relationship retention and `disputed` state**

Merging a Document does not delete source/document relationships; contrary assertions are written into a conflict group and cannot be overridden by `accepted`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest DomainIntelSearch/tests/test_dedup_governance.py DomainIntelSearch/tests/test_agent_evidence.py -q`

### Task 5: Build the Entity and Industry Value-Chain Open-World Coverage Loop

**Files:**
- Create: `DomainIntelSearch/src/entity_coverage.py`
- Modify: `DomainIntelSearch/src/knowledge_model.py`
- Modify: `DomainIntelSearch/intdog_core/chain_repository.py`
- Modify: `DomainIntelSearch/src/coverage_execution.py`
- Test: `DomainIntelSearch/tests/test_entity_coverage.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class CoverageFrontier:
    cells: list[dict]
    entity_queries: list[dict]
    relation_queries: list[dict]
    stopping_reason: str | None

def build_coverage_matrix(repo, folder: str) -> dict: ...
def plan_entity_frontier(matrix: dict, *, round_no: int) -> CoverageFrontier: ...
def resolve_entity_candidate(repo, folder: str, candidate: dict) -> dict: ...
```

- [ ] **Step 1: Write RED coverage, disambiguation, and convergence tests**

Cover ten object categories, applicable industry value-chain stages, Chinese/foreign regions, empty cells, 2/3/8/10-per-cell boundaries, deepening high-centrality endpoints, aliases, same-name different entities, institution renaming, before/after acquisition, official-site/registration-identifier conflicts, relationships without evidence, and two consecutive rounds with zero marginal gain.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_entity_coverage.py DomainIntelSearch/tests/test_coverage_planning.py -q`

- [ ] **Step 3: Implement the coverage matrix, expansion frontier, and human-merge boundary**

Use 3 qualified representatives as the initial breadth threshold for applicable cells and 8–10 as the depth target for high-value endpoints; retain a gap when insufficient. Relationships must reference Documents/Assertions; return `manual_review` for uncertain identity and never merge automatically.

- [ ] **Step 4: Run GREEN and knowledge-graph regression**

Run: `python -m pytest DomainIntelSearch/tests/test_entity_coverage.py DomainIntelSearch/tests/test_coverage_planning.py DomainIntelSearch/tests/test_intdog_core.py -q`

### Task 6: Source, Coverage Campaign API, and Review Workbench

**Files:**
- Modify: `DomainIntelWeb/api/schemas.py`
- Modify: `DomainIntelWeb/api/routers/sources.py`
- Modify: `DomainIntelWeb/api/routers/intelligence.py`
- Modify: `DomainIntelWeb/src/features/SourcesPage.tsx`
- Create: `DomainIntelWeb/src/features/sources/SourceCampaignPanel.tsx`
- Modify: `DomainIntelWeb/src/test/workflows.test.tsx`

- [ ] **Step 1: Write RED API/DOM tests**

Cover campaign creation, paginated candidates, query ledger, source gaps, coverage matrix, entity expansion frontier, identity review, reassessment, and complete explanations when fewer than 8 sources or when entity cells are below threshold.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelWeb/tests/test_api.py -q && npm test --prefix DomainIntelWeb`

- [ ] **Step 3: Implement the strongly typed API and UI**

UI states include candidate, active, manual, reserve, rejected, paused, and converged; the coverage view also displays industry value-chain stage, entity category, region, current depth, target, gap, and relationship evidence. All actions retain review explanations.

- [ ] **Step 4: Generate the contract and run the subproject gate**

Run: `python DomainIntelWeb/scripts/export_openapi.py && python DomainIntelWeb/scripts/generate_contract.py`
Run: `python -m pytest -q DomainIntelSearch/tests DomainIntelApp/tests DomainIntelWeb/tests`
Run: `npm test --prefix DomainIntelWeb && npm run build --prefix DomainIntelWeb`
Run: `python DomainIntelSearch/scripts/check_repo.py && git diff --check`

### Task 7: Cross-Day Signal Momentum, Self-Drift, and Columnar-Layer Triggers

**Files:**
- Create: `DomainIntelSearch/intdog_core/observability_repository.py`
- Create: `DomainIntelSearch/src/signal_momentum.py`
- Create: `DomainIntelSearch/src/quality_drift.py`
- Modify: `DomainIntelWeb/api/routers/intelligence.py`
- Test: `DomainIntelSearch/tests/test_signal_observability.py`

- [ ] **Step 1: Write RED time-series and drift tests**

Cover first appearance, sustained heating/tracking/cooling, missing days, long-unresolved status, crossing 04:00, rank ties, independent-source growth, syndicated duplicates, identical-input reruns, algorithm-version changes, seven/thirty-day windows, zero denominators, and fixed-evaluation-set degradation. Use benchmark fixtures to check all four Parquet/DuckDB triggers.

- [ ] **Step 2: Run RED**

Run: `python -m pytest DomainIntelSearch/tests/test_signal_observability.py -q`

- [ ] **Step 3: Implement immutable observations, deterministic momentum, and drift diagnostics**

Daily observations store rank/score/independent publishers/evidence strength/classification/algorithm version. The API returns day-over-day deltas, seven-day trends, metric denominators/baselines/thresholds, and raw-observation links. Record only columnar-prototype trigger state; do not add DuckDB/Parquet dependencies or a second write path.

- [ ] **Step 4: Run GREEN and the performance gate**

Run: `python -m pytest DomainIntelSearch/tests/test_signal_observability.py DomainIntelWeb/tests/test_api.py -q`
