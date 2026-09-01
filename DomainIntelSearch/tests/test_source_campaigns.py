"""Persistence contracts for auditable source-discovery campaigns."""

from __future__ import annotations

import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from intdog_core.repository import IntelligenceRepository, SCHEMA_VERSION
from src.research_bootstrap import build_tasks
from src.source_campaign import plan_query_families, run_campaign_round
from src.source_discovery import SOURCE_CATEGORIES


def _running_campaign(repo: IntelligenceRepository, folder: str) -> tuple[dict, dict]:
    campaign = repo.create_source_campaign(folder, ["official", "news"], 24)
    repo.transition_source_campaign(campaign["id"], "running")
    query = repo.record_source_query(
        campaign["id"], round_no=1, language="zh-CN", family="authority",
        dimensions={"region": "CN", "source_type": "official"},
        query="人工智能 官方 统计", outcome={"status": "completed", "hits": 3})
    return campaign, query


def _candidate(query_id: str, **overrides: object) -> dict:
    item = {
        "name": "Reuters AI",
        "url": "https://www.reuters.com/technology/artificial-intelligence/?utm_source=test",
        "category": "news",
        "publisher_country": "GB",
        "access": "web",
        "score": 0.82,
        "selection_reason": "independent international reporting",
        "query_id": query_id,
    }
    item.update(overrides)
    return item


def _admissible_candidate(query_id: str, **overrides: object) -> dict:
    item = _candidate(query_id, **overrides)
    item.update({
        "identity_verification": {"status": "verified",
          "evidence_url": "https://registry.example/reuters", "verified_by": "analyst"},
        "ownership_verification": {"status": "verified", "owner_cluster": "reuters",
          "evidence_url": "https://registry.example/reuters/owner", "verified_by": "analyst"},
        "url_verification": {"status": "verified", "reachable": True,
          "status_code": 200, "checked_url": item["url"],
          "verification_origin": "server_guarded"},
    })
    return item


def test_schema16_migration_is_repeatable_and_preserves_existing_source_rows():
    """Catches a destructive or non-idempotent v16 migration."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        source_id = repo.upsert_source(
            "AI", "official", {"name": "NIST", "url": "https://nist.gov/ai"})
        campaign, query = _running_campaign(repo, "AI")
        candidate = repo.upsert_source_candidate(campaign["id"], _candidate(query["id"]))

        repo.migrate()
        with repo.transaction() as con:
            con.execute("DELETE FROM schema_migrations WHERE version=16")
        repo.migrate()

        with repo.connection() as con:
            versions = [row[0] for row in con.execute(
                "SELECT version FROM schema_migrations ORDER BY version")]
            tables = {row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            preserved_source = con.execute(
                "SELECT canonical_url FROM sources WHERE id=?", (source_id,)).fetchone()
            preserved_candidate = con.execute(
                "SELECT status FROM source_candidates WHERE id=?", (candidate["id"],)).fetchone()

        assert versions == list(range(1, SCHEMA_VERSION + 1))
        assert {"source_campaigns", "source_queries", "source_candidates",
                "source_candidate_queries", "source_reviews"} <= tables
        assert preserved_source[0] == "https://nist.gov/ai"
        assert preserved_candidate[0] == "candidate"


def test_canonical_url_upsert_is_unique_and_aggregates_multiple_query_provenances():
    """Catches URL tracking variants creating duplicate candidates or losing a query link."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        campaign, first_query = _running_campaign(repo, "AI")
        second_query = repo.record_source_query(
            campaign["id"], round_no=2, language="en", family="gap-expansion",
            dimensions={"region": "Global", "source_type": "news"},
            query="AI independent news publisher",
            outcome={"status": "completed", "hits": 2})

        first = repo.upsert_source_candidate(campaign["id"], _candidate(first_query["id"]))
        second = repo.upsert_source_candidate(campaign["id"], _candidate(
            second_query["id"],
            url="https://reuters.com/technology/artificial-intelligence?utm_medium=rss",
            score=0.91))

        assert second["id"] == first["id"]
        assert second["canonical_url"] == "https://reuters.com/technology/artificial-intelligence"
        assert second["score"] == pytest.approx(0.91)
        assert second["query_ids"] == sorted([first_query["id"], second_query["id"]])
        with repo.connection() as con:
            assert con.execute("SELECT COUNT(*) FROM source_candidates").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM source_candidate_queries").fetchone()[0] == 2


def test_same_publisher_is_shared_but_candidate_state_is_independent_by_industry():
    """Catches publisher duplication or one industry's decision leaking into another."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        repo.ensure_industry("Chips")
        ai_campaign, ai_query = _running_campaign(repo, "AI")
        chip_campaign, chip_query = _running_campaign(repo, "Chips")
        ai_candidate = repo.upsert_source_candidate(
            ai_campaign["id"], _admissible_candidate(ai_query["id"]))
        chip_candidate = repo.upsert_source_candidate(
            chip_campaign["id"], _candidate(
                chip_query["id"],
                url="https://www.reuters.com/technology/chips/",
                name="Reuters Chips"))

        repo.review_source_candidate(
            "AI", ai_candidate["id"], decision="active", actor="analyst-a",
            reason="representative international source")
        repo.review_source_candidate(
            "Chips", chip_candidate["id"], decision="rejected", actor="analyst-b",
            reason="insufficient incremental chip coverage")

        assert repo.get_source_candidate("AI", ai_candidate["id"])["status"] == "active"
        assert repo.get_source_candidate("Chips", chip_candidate["id"])["status"] == "rejected"
        with repo.connection() as con:
            publishers = con.execute(
                "SELECT id,owner_cluster FROM publishers WHERE owner_cluster='reuters'").fetchall()
            candidate_publishers = con.execute(
                "SELECT DISTINCT publisher_id FROM source_candidates").fetchall()
        assert len(publishers) == 1
        assert len(candidate_publishers) == 1


def test_source_review_history_is_append_only_and_cannot_be_overwritten_directly():
    """Catches review mutation/deletion that would erase the decision trail."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        campaign, query = _running_campaign(repo, "AI")
        candidate = repo.upsert_source_candidate(
            campaign["id"], _admissible_candidate(query["id"]))

        repo.review_source_candidate(
            "AI", candidate["id"], decision="manual_review", actor="system",
            reason="media sources require human review")
        repo.review_source_candidate(
            "AI", candidate["id"], decision="active", actor="human-reviewer",
            reason="publisher and editorial ownership verified")

        with repo.connection() as con:
            rows = [dict(row) for row in con.execute(
                "SELECT id,from_status,to_status,actor,reason FROM source_reviews ORDER BY id")]
        assert [(row["from_status"], row["to_status"], row["actor"]) for row in rows] == [
            ("candidate", "manual_review", "system"),
            ("manual_review", "active", "human-reviewer"),
        ]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            with repo.transaction() as con:
                con.execute("UPDATE source_reviews SET reason='rewritten' WHERE id=?", (rows[0]["id"],))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            with repo.transaction() as con:
                con.execute("DELETE FROM source_reviews WHERE id=?", (rows[0]["id"],))
        with repo.connection() as con:
            assert con.execute("SELECT COUNT(*) FROM source_reviews").fetchone()[0] == 2


def test_campaign_state_machine_accepts_pause_resume_and_terminal_convergence():
    """Catches a campaign state machine that cannot pause safely or terminates ambiguously."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        campaign = repo.create_source_campaign("AI", ["official"], 8)

        assert repo.transition_source_campaign(campaign["id"], "running")["status"] == "running"
        paused = repo.transition_source_campaign(
            campaign["id"], "paused", reason="provider rate limited")
        assert (paused["status"], paused["stopping_reason"]) == (
            "paused", "provider rate limited")
        resumed = repo.transition_source_campaign(campaign["id"], "running")
        assert (resumed["status"], resumed["stopping_reason"]) == ("running", "")
        converged = repo.transition_source_campaign(
            campaign["id"], "converged", reason="two zero-yield rounds")
        assert converged["status"] == "converged"


def test_invalid_campaign_transition_rolls_back_status_and_audit():
    """Catches partial writes when a forbidden campaign transition is requested."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        campaign = repo.create_source_campaign("AI", ["official"], 8)

        with pytest.raises(ValueError, match="planned.*converged"):
            repo.transition_source_campaign(
                campaign["id"], "converged", reason="not actually searched")

        assert repo.get_source_campaign(campaign["id"])["status"] == "planned"
        with repo.connection() as con:
            transitions = con.execute("""SELECT COUNT(*) FROM audit_log
                WHERE object_type='source_campaign' AND object_id=?
                AND action='source_campaign_transition'""", (campaign["id"],)).fetchone()[0]
        assert transitions == 0


def test_invalid_candidate_transition_and_wrong_folder_are_atomic():
    """Catches an invalid/folder-confused review updating status without valid history."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        repo.ensure_industry("Chips")
        campaign, query = _running_campaign(repo, "AI")
        candidate = repo.upsert_source_candidate(
            campaign["id"], _admissible_candidate(query["id"]))
        repo.review_source_candidate(
            "AI", candidate["id"], decision="active", actor="reviewer",
            reason="review complete")

        with pytest.raises(ValueError, match="active.*candidate"):
            repo.review_source_candidate(
                "AI", candidate["id"], decision="candidate", actor="reviewer",
                reason="attempted reset")
        with pytest.raises(FileNotFoundError):
            repo.review_source_candidate(
                "Chips", candidate["id"], decision="rejected", actor="reviewer",
                reason="wrong industry")

        assert repo.get_source_candidate("AI", candidate["id"])["status"] == "active"
        with repo.connection() as con:
            assert con.execute(
                "SELECT COUNT(*) FROM source_reviews WHERE candidate_id=?",
                (candidate["id"],)).fetchone()[0] == 1


def test_candidate_requires_query_provenance_from_the_same_campaign():
    """Catches untraceable candidates and cross-campaign provenance injection."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        first_campaign, first_query = _running_campaign(repo, "AI")
        second_campaign, second_query = _running_campaign(repo, "AI")

        with pytest.raises(ValueError, match="query_id"):
            repo.upsert_source_candidate(
                first_campaign["id"], {key: value for key, value in
                                       _candidate(first_query["id"]).items()
                                       if key != "query_id"})
        with pytest.raises(ValueError, match="campaign"):
            repo.upsert_source_candidate(
                first_campaign["id"], _candidate(second_query["id"]))

        assert repo.list_source_candidates(first_campaign["id"]) == []
        assert repo.list_source_candidates(second_campaign["id"]) == []


def test_concurrent_candidate_upserts_are_idempotent():
    """Catches race-created duplicate candidate or publisher/provenance rows."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        campaign, query = _running_campaign(repo, "AI")

        def upsert(_: int) -> str:
            return repo.upsert_source_candidate(
                campaign["id"], _candidate(query["id"]))["id"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(upsert, range(24)))

        assert len(set(ids)) == 1
        with repo.connection() as con:
            assert con.execute("SELECT COUNT(*) FROM source_candidates").fetchone()[0] == 1
            assert con.execute("SELECT COUNT(*) FROM source_candidate_queries").fetchone()[0] == 1
            assert con.execute(
                "SELECT COUNT(*) FROM publishers WHERE owner_cluster='reuters'").fetchone()[0] == 1


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda repo, campaign: repo.create_source_campaign("AI", [], 8), "targets"),
        (lambda repo, campaign: repo.create_source_campaign("AI", ["news"], 0), "budget"),
        (lambda repo, campaign: repo.record_source_query(
            campaign["id"], round_no=0, language="en", family="baseline",
            dimensions={}, query="AI sources", outcome={}), "round_no"),
    ],
)
def test_invalid_campaign_inputs_do_not_leave_partial_rows(operation, message):
    """Catches validation performed after a partial campaign/query write."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI")
        campaign = repo.create_source_campaign("AI", ["news"], 8)
        repo.transition_source_campaign(campaign["id"], "running")
        with pytest.raises(ValueError, match=message):
            operation(repo, campaign)
        with repo.connection() as con:
            assert con.execute("SELECT COUNT(*) FROM source_queries").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM source_candidates").fetchone()[0] == 0


class _CampaignSearch:
    def __init__(self, *, productive_families: set[str] | None = None,
                 failure: object | None = None):
        self.productive_families = productive_families or set()
        self.failure = failure
        self.calls: list[dict] = []

    def search(self, query: str, *, language: str, family: str,
               dimensions: dict, limit: int):
        self.calls.append({"query": query, "language": language, "family": family,
                           "dimensions": dimensions, "limit": limit})
        if self.failure is not None:
            if isinstance(self.failure, BaseException):
                raise self.failure
            return self.failure
        if family not in self.productive_families:
            return []
        category = dimensions["source_type"]
        return [{
            "name": f"{category}-{language}",
            "url": f"https://{category}-{language}.example/source",
            "category": category,
            "publisher_country": "中国" if language == "zh" else "US",
            "language": language,
            "score": 0.7,
            "selection_reason": "structurally valid discovery candidate",
        }]


def _all_category_campaign(repo: IntelligenceRepository, budget: int = 100) -> dict:
    return repo.create_source_campaign(
        "AI", [category for category, _ in SOURCE_CATEGORIES], budget)


def test_query_plan_is_bilingual_covers_nine_categories_and_oversamples_selection():
    """Catches a monolingual, incomplete, or selection-sized candidate search plan."""
    baseline = plan_query_families(
        {"name": "人工智能", "name_en": "Artificial Intelligence"}, [])
    assert len(baseline) == 18
    assert {item["language"] for item in baseline} == {"zh", "en"}
    assert {item["dimensions"]["source_type"] for item in baseline} == {
        category for category, _ in SOURCE_CATEGORIES}
    assert {item["family"] for item in baseline} == {"authoritative_baseline"}
    assert all(item["candidate_pool_target"] > item["selection_target"]
               for item in baseline)

    expanded = plan_query_families(
        {"name": "人工智能", "name_en": "Artificial Intelligence",
         "targets": ["official"]},
        [{"category": "official", "missing": 6,
          "dimensions": {"chain_stage": "算力", "subdomain": "AI 芯片"}}])
    assert len(expanded) == 2
    assert {item["family"] for item in expanded} == {"gap_expansion"}
    assert all(item["dimensions"]["chain_stage"] == "算力" for item in expanded)

    multi_gap = plan_query_families(
        {"name": "人工智能", "targets": ["official"]}, [{
            "category": "official", "dimensions": {"chain_stage": "算力"}}, {
            "category": "official", "dimensions": {"chain_stage": "模型"}}])
    assert len(multi_gap) == 4
    assert {item["dimensions"]["chain_stage"] for item in multi_gap} == {"算力", "模型"}


def test_logical_query_budget_is_idempotent_and_round_lease_is_cas_guarded():
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp); repo.ensure_industry("AI")
        campaign = repo.create_source_campaign("AI", ["official"], 8)
        repo.transition_source_campaign(campaign["id"], "running")
        first = repo.record_source_query(
            campaign["id"], round_no=1, language="zh", family="authority",
            dimensions={"source_type": "official"}, query="AI 官方",
            outcome={"status": "paused"})
        rerun = repo.record_source_query(
            campaign["id"], round_no=1, language="zh", family="authority",
            dimensions={"source_type": "official"}, query="AI 官方",
            outcome={"status": "completed"})
        assert first["id"] == rerun["id"] and rerun["outcome"]["status"] == "completed"
        round_state = repo.begin_source_campaign_round(
            campaign["id"], plan=[], frontier=[])
        with pytest.raises(RuntimeError, match="already running"):
            repo.begin_source_campaign_round(campaign["id"], plan=[], frontier=[])
        with pytest.raises(RuntimeError, match="lease"):
            repo.finish_source_campaign_round(round_state["id"], "wrong", {})
        with repo.connection() as con:
            assert con.execute("SELECT COUNT(*) FROM source_queries").fetchone()[0] == 1


def test_first_round_is_authoritative_baseline_and_persists_candidates_not_sources():
    """Catches a baseline round that activates model/search output as a source."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI", "人工智能")
        campaign = _all_category_campaign(repo)
        search = _CampaignSearch(productive_families={"authoritative_baseline"})

        outcome = run_campaign_round(repo, campaign["id"], search=search)

        assert outcome.status == "running"
        assert outcome.candidate_total == 18
        assert outcome.qualified_by_category == {
            category: 0 for category, _ in SOURCE_CATEGORIES}
        assert {call["family"] for call in search.calls} == {"authoritative_baseline"}
        assert repo.get_source_campaign(campaign["id"])["rounds"] == 1
        assert repo.list_sources("AI") == []


def test_two_consecutive_zero_yield_rounds_are_required_for_convergence():
    """Catches first-zero convergence or prompt-controlled stopping semantics."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI", "人工智能")
        campaign = _all_category_campaign(repo, budget=40)
        search = _CampaignSearch()

        first = run_campaign_round(repo, campaign["id"], search=search)
        second = run_campaign_round(repo, campaign["id"], search=search)

        assert first.status == "running"
        assert second.status == "converged"
        assert second.candidate_total == 0
        assert repo.get_source_campaign(campaign["id"])["rounds"] == 2
        assert {call["family"] for call in search.calls[:18]} == {
            "authoritative_baseline"}
        assert {call["family"] for call in search.calls[18:]} == {"gap_expansion"}


def test_candidates_remain_distinct_from_qualified_convergence_gain():
    """Catches unreviewed candidates being mislabeled as qualified publishers."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI", "人工智能")
        campaign = _all_category_campaign(repo, budget=60)
        search = _CampaignSearch(productive_families={"authoritative_baseline"})

        first = run_campaign_round(repo, campaign["id"], search=search)
        second = run_campaign_round(repo, campaign["id"], search=search)
        assert first.qualified_by_category == {
            category: 0 for category, _ in SOURCE_CATEGORIES}
        assert second.status == "converged"


@pytest.mark.parametrize(
    ("failure", "budget", "reason"),
    [
        (TimeoutError("search timed out"), 100, "timeout"),
        (SimpleNamespace(status_code=403, status="error"), 100, "403"),
        (SimpleNamespace(status_code=429, status="error"), 100, "429"),
        (None, 17, "insufficient_budget"),
    ],
)
def test_timeout_forbidden_rate_limit_and_insufficient_budget_pause(
        failure, budget, reason):
    """Catches operational failures being mislabeled as convergence."""
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp)
        repo.ensure_industry("AI", "人工智能")
        campaign = _all_category_campaign(repo, budget=budget)
        search = _CampaignSearch(failure=failure)

        outcome = run_campaign_round(repo, campaign["id"], search=search)

        assert outcome.status == "paused"
        assert reason in outcome.stopping_reason.casefold()
        assert repo.get_source_campaign(campaign["id"])["status"] == "paused"
        assert repo.get_source_campaign(campaign["id"])["rounds"] == 0


def test_bootstrap_source_task_declares_candidate_only_output():
    """Catches a provider prompt contract that can directly mark sources active."""
    source_task = build_tasks("人工智能", "Artificial Intelligence")[0]
    assert source_task["admission"] == "candidate_only"
    assert source_task["allowed_statuses"] == ["candidate"]


def test_active_admission_is_gated_atomic_and_materializes_source_once():
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp); repo.ensure_industry("AI")
        campaign, query = _running_campaign(repo, "AI")
        weak = repo.upsert_source_candidate(campaign["id"], _candidate(query["id"]))
        with pytest.raises(ValueError, match="admission gates"):
            repo.review_source_candidate("AI", weak["id"], decision="active",
                                         actor="analyst", reason="looks useful")
        assert repo.list_sources("AI") == []
        assert repo.get_source_candidate("AI", weak["id"])["status"] == "candidate"

        strong = repo.upsert_source_candidate(campaign["id"], _admissible_candidate(
            query["id"], url="https://verified.example/feed", category="official",
            name="Verified Authority"))
        active = repo.review_source_candidate(
            "AI", strong["id"], decision="active", actor="analyst",
            reason="identity ownership and guarded URL verified")
        assert active["status"] == "active" and active["source_id"]
        assert repo.list_sources("AI")[0]["monitoring_status"] == "active"


def test_reviewed_candidate_payload_cannot_be_silently_rewritten():
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp); repo.ensure_industry("AI")
        campaign, query = _running_campaign(repo, "AI")
        candidate = repo.upsert_source_candidate(campaign["id"], _candidate(query["id"]))
        repo.review_source_candidate("AI", candidate["id"], decision="reserve",
                                     actor="analyst", reason="overlap")
        with pytest.raises(ValueError, match="reviewed candidate"):
            repo.upsert_source_candidate(campaign["id"], _candidate(
                query["id"], name="Silently replaced", score=99))
        persisted = repo.get_source_candidate("AI", candidate["id"])
        assert persisted["name"] == candidate["name"]
        assert persisted["score"] == candidate["score"]


def test_manual_source_and_reassessment_share_non_bypassable_admission_gate():
    with tempfile.TemporaryDirectory() as temp:
        repo = IntelligenceRepository(temp); repo.ensure_industry("AI")
        source_id = repo.upsert_source("AI", "official", {
            "name": "Manual NIST", "url": "https://nist.gov/ai",
            "monitoring_status": "active", "added_manually": True})
        assert repo.list_sources("AI")[0]["monitoring_status"] == "recommended_manual"
        with pytest.raises(ValueError, match="admission gates"):
            repo.reassess_source("AI", source_id, decision="active", actor="analyst",
                                 reason="trusted domain alone")
        assert repo.list_sources("AI")[0]["monitoring_status"] == "recommended_manual"
