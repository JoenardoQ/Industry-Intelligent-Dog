from src.crawlers.academic_crawler import select_paper_portfolio
from src.crawlers.periodic_crawlers import _search_terms


def test_paper_portfolio_reserves_half_for_frontier_discovery():
    papers = [
        {"title": "core-1", "matched": True},
        {"title": "core-2", "matched": True},
        {"title": "core-3", "matched": True},
        {"title": "frontier-1", "matched": False},
        {"title": "frontier-2", "matched": False},
        {"title": "frontier-3", "matched": False},
    ]

    selected = select_paper_portfolio(
        papers, limit=4, matches=lambda item: item["matched"])

    assert [item["title"] for item in selected] == [
        "core-1", "core-2", "frontier-1", "frontier-2"]
    assert selected[2]["discovery_mode"] == "frontier_candidate"
    assert selected[2]["fact_status"] == "candidate"


def test_search_term_budget_accepts_twelve_distinct_terms_by_default():
    terms = [f"technical-term-{index}" for index in range(20)]
    assert len(_search_terms(terms)) == 12
