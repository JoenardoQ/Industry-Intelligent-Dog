"""Direct report execution for Codex subscription or explicit API providers.

Task packages remain inspectable, but this module turns them into actual Markdown
artifacts and deterministic chart data so the desktop app can generate and render
reports without a manual copy/paste loop.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from intdog_core import tracked_function

from .source_discovery import source_origin
from .services.provider_factory import create_provider


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _client(config: dict, store, provider: str):
    """Compatibility seam kept intentionally for deterministic report tests."""
    return create_provider(config, provider, store.root)


def _safe_output(store, relative: str) -> Path:
    path = (store.root / relative).resolve()
    if not path.is_relative_to(store.root.resolve()):
        raise ValueError("报告输出路径越过行业目录")
    return path


def _markdown(text: str) -> str:
    value = text.strip()
    value = re.sub(r"^```(?:markdown|md)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)
    return value.strip() + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def _context(store, days: int = 30, limit: int = 120_000,
             max_items: int = 500) -> str:
    sources = store.get_sources()
    knowledge = {
        "industry": store._read_json(store.knowledge / "industry.json", {}),
        "chains": store._read_json(store.knowledge / "chains.json", []),
        "entities": store._read_json(store.knowledge / "entities.json", []),
    }
    daily = store.list_daily_range(days=days)
    # Sample across the whole requested duration. Recent/high-credibility sorting
    # happens inside each time stratum, never across the full corpus.
    grouped = defaultdict(list)
    for item in daily:
        raw = str(item.get("published_at") or item.get("date") or "")[:10]
        try:
            moment = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            continue
        bucket = moment.strftime("%Y-%m") if days >= 1000 else (
            f"{moment.isocalendar().year}-W{moment.isocalendar().week:02d}")
        grouped[bucket].append(item)
    max_items = max(1, min(2000, int(max_items)))
    quota = max(1, max_items // max(1, len(grouped)))
    sampled, chosen = [], set()
    for bucket in sorted(grouped):
        rows = sorted(grouped[bucket], key=lambda item: (
            item.get("credibility", 0), item.get("published_at") or item.get("date", ""),
            item.get("title", "")), reverse=True)
        for item in rows[:quota]:
            key = store._key(item)
            if key and key not in chosen:
                sampled.append(item); chosen.add(key)
    if len(sampled) < max_items:
        for item in sorted(daily, key=lambda row: (
                row.get("credibility", 0), row.get("published_at") or row.get("date", "")),
                reverse=True):
            key = store._key(item)
            if key and key not in chosen:
                sampled.append(item); chosen.add(key)
            if len(sampled) >= max_items:
                break
    categories = Counter(str(item.get("category") or "unknown") for item in daily)
    publishers = {str(item.get("source_domain") or item.get("source") or "")
                  for item in daily if item.get("source_domain") or item.get("source")}
    history = {"corpus_items": len(daily), "sampled_items": len(sampled),
               "time_strata": len(grouped), "publisher_count": len(publishers),
               "categories": dict(categories), "sampling": "time_stratified"}
    payload = {"sources": sources, "knowledge": knowledge,
               "history_summary": history, "daily": sampled[:max_items]}
    return json.dumps(payload, ensure_ascii=False)[:limit]


def _visualization(store, days: int, title: str) -> dict:
    items = store.list_daily_range(days=days)
    categories = ("news", "papers", "github", "funding", "hiring", "ceo")
    counts = {key: 0 for key in categories}
    for item in items:
        category = item.get("category") or item.get("_cat")
        if category in counts:
            counts[category] += 1
    china = sum(source_origin(item) == "china" for item in items)
    foreign = sum(source_origin(item) == "foreign" for item in items)
    return {"type": "bar", "title": title,
            "labels": list(counts), "values": list(counts.values()),
            "origin_counts": {"china": china, "foreign": foreign},
            "window_days": days}


def _directed_chain(store) -> dict:
    """Deterministic upstream-to-downstream graph embedded in report metadata."""
    nodes = store.service.repo.list_chain_nodes(store.folder)
    normalized = [{
        "id": item.get("id") or f"chain-{index}",
        "label": item.get("name") or f"环节 {index + 1}",
        "order": int(item.get("order", index) or index),
        "description": item.get("description", ""),
        "entity_count": int(item.get("entity_count", 0) or 0),
        "evidence_count": int(item.get("evidence_count", 0) or 0),
        "coverage_status": item.get("coverage_status", "empty"),
    } for index, item in enumerate(nodes)]
    normalized.sort(key=lambda item: (item["order"], item["label"]))
    edges = [{
        "source": normalized[index]["id"],
        "target": normalized[index + 1]["id"],
        "relation": "upstream_to_downstream",
    } for index in range(len(normalized) - 1)]
    return {"type": "directed_chain", "direction": "LR",
            "nodes": normalized, "edges": edges}


def _provenance(result: dict) -> dict:
    return {key: result[key] for key in ("provider", "model", "generated_at", "status")
            if key in result}


def _urls(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"https?://[^\s)>，；]+", text)))


def _reference_payload(markdown: str, provenance: dict | None = None) -> dict:
    match = re.search(r"^##\s+references(?:\[\])?\s*$", markdown,
                      flags=re.I | re.M)
    section = markdown[match.end():] if match else ""
    references = []
    for line in section.splitlines():
        item = re.match(r"^\s*-?\s*\[(\d+)\]\s*(.+?)\s*$", line)
        if not item:
            continue
        references.append({"id": int(item.group(1)), "text": item.group(2),
                           "urls": _urls(item.group(2))})
    return {"references": references, **(provenance or {})}


def _table_rows(markdown: str, first_header: str) -> list[list[str]]:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0].lower() == first_header.lower():
            rows = []
            for candidate in lines[index + 2:]:
                if not candidate.strip().startswith("|"):
                    break
                values = [cell.strip() for cell in candidate.strip().strip("|").split("|")]
                if values:
                    rows.append(values)
            return rows
    return []


def _claims_payload(markdown: str, provenance: dict | None = None) -> dict:
    claims = []
    for cells in _table_rows(markdown, "claim"):
        if len(cells) < 5:
            continue
        evidence = re.findall(r"\[\d+\]", cells[1]) or _urls(cells[1])
        try:
            confidence = float(cells[3])
        except ValueError:
            confidence = None
        claims.append({"claim": cells[0], "evidence_urls": evidence,
                       "as_of": cells[2], "confidence": confidence,
                       "status": cells[4].strip("*`")})
    return {"claims": claims, **(provenance or {})}


def _write_deep_sidecars(store, task: dict, markdown: str,
                         provenance: dict | None = None) -> None:
    references_path = _safe_output(store, task["references_file"])
    claims_path = _safe_output(store, task["claims_file"])
    store._write_json(references_path, _reference_payload(markdown, provenance))
    store._write_json(claims_path, _claims_payload(markdown, provenance))


def _numbered_section(markdown: str, number: int) -> str:
    match = re.search(rf"^##\s+{number}\.\s+.*$", markdown, flags=re.M)
    if not match:
        return ""
    following = re.search(r"^##\s+", markdown[match.end():], flags=re.M)
    end = match.end() + following.start() if following else len(markdown)
    return markdown[match.end():end]


def _clean_inline(text: str) -> str:
    value = text.strip().lstrip("- ")
    value = value.replace("**", "").replace("`", "")
    return value.strip()


def _impact_payload(markdown: str) -> dict:
    overview = _numbered_section(markdown, 1)
    summary_match = re.search(r"\*\*一句话概述：\*\*\s*(.+)", overview)
    summary = _clean_inline(summary_match.group(1)) if summary_match else ""

    companies = []
    company_section = _numbered_section(markdown, 2)
    company_matches = list(re.finditer(r"^###\s+(?:\d+(?:\.\d+)*\s+)?(.+?)\s*$",
                                       company_section, flags=re.M))
    for index, match in enumerate(company_matches):
        end = company_matches[index + 1].start() if index + 1 < len(company_matches) else len(company_section)
        details = [_clean_inline(line) for line in
                   company_section[match.end():end].splitlines()
                   if line.strip().startswith("-")]
        companies.append({"name": _clean_inline(match.group(1)), "details": details})

    supply_chain = []
    for match in re.finditer(r"^\s*\d+\.\s+\*\*(.+?)\*\*\s*$",
                             _numbered_section(markdown, 3), flags=re.M):
        supply_chain.append({"stage": _clean_inline(match.group(1))})

    papers = []
    paper_section = _numbered_section(markdown, 4)
    paper_headers = []
    for line in paper_section.splitlines():
        if not line.strip().startswith("|"):
            continue
        raw_cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        cells = [_clean_inline(cell) for cell in raw_cells]
        if not paper_headers:
            paper_headers = cells
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in raw_cells):
            continue
        if len(cells) == len(paper_headers):
            papers.append(dict(zip(paper_headers, cells)))

    policies = []
    policy_section = _numbered_section(markdown, 5)
    policy_matches = list(re.finditer(r"^###\s+(.+?)\s*$", policy_section, flags=re.M))
    for index, match in enumerate(policy_matches):
        end = policy_matches[index + 1].start() if index + 1 < len(policy_matches) else len(policy_section)
        details = [_clean_inline(line) for line in
                   policy_section[match.end():end].splitlines()
                   if line.strip().startswith("-")]
        policies.append({"region": _clean_inline(match.group(1)), "details": details})

    impact_rating = {}
    for cells in _table_rows(_numbered_section(markdown, 6), "周期"):
        if len(cells) >= 3:
            impact_rating[_clean_inline(cells[0])] = {
                "rating": _clean_inline(cells[1]), "reason": _clean_inline(cells[2])}

    takeaways = [_clean_inline(line) for line in
                 _numbered_section(markdown, 7).splitlines()
                 if line.strip().startswith("-")]
    references = _reference_payload(markdown)["references"]
    return {"summary": summary, "companies": companies,
            "supply_chain": supply_chain, "papers": papers,
            "policies": policies, "impact_rating": impact_rating,
            "takeaways": takeaways, "references": references}


def _merge_impact_metadata(store, metadata_path: Path, markdown: str,
                           provenance: dict) -> None:
    payload = store._read_json(metadata_path, {})
    payload.update(_impact_payload(markdown))
    payload.update(provenance)
    store._write_json(metadata_path, payload)


def _execute(config: dict, store, task: dict, provider: str,
             context_days: int = 30) -> dict:
    context_cap = int((config.get("history", {}) or {}).get("context_item_cap", 500))
    prompt = (task["prompt"] +
              "\n\n【本次已注入的本地证据】\n" +
              _context(store, context_days, max_items=context_cap) +
              "\n\n只输出最终 Markdown 正文；不要输出代码围栏，不要声称写文件。"
              "无法核验的数据明确标注 N/A 或待核验。")
    result = _client(config, store, provider).complete(prompt)
    output = _safe_output(store, task["output_file"])
    _write_text(output, _markdown(result.text))
    return {"path": str(output), "provider": result.provider, "model": result.model,
            "generated_at": _now(), "status": "draft_review_required"}


def _ensure_history(config: dict, store, horizon: str) -> dict | None:
    history = config.get("history", {}) or {}
    if not history.get("auto_backfill", False):
        return None
    from .history_backfill import ensure_history
    return ensure_history(config, store, horizon)


@tracked_function("generate-period", store_position=1)
def generate_periodic(config: dict, store, kind: str,
                      provider: str = "codex") -> dict:
    from .scheduler import PeriodicScheduler
    if kind not in {"weekly", "monthly", "quarterly"}:
        raise ValueError("周期必须是 weekly/monthly/quarterly")
    _ensure_history(config, store, kind)
    scheduler = PeriodicScheduler(config, store)
    created = {"weekly": scheduler.run_weekly,
               "monthly": scheduler.run_monthly,
               "quarterly": scheduler.run_quarterly}[kind]()
    json_path = Path(created[kind])
    payload = store._read_json(json_path, {})
    task = payload.get("task") or {}
    if not task.get("prompt") or not task.get("output_file"):
        raise ValueError("周期任务包缺少 prompt/output_file")
    days = {"weekly": 7, "monthly": 30, "quarterly": 90}[kind]
    result = _execute(config, store, task, provider, context_days=days)
    payload.update(result)
    payload["report_file"] = result["path"]
    payload["summary"] = f"{store.name} {kind} 报告已直接生成；状态为待人工复核。"
    payload["visualization"] = _visualization(store, days, "本期情报类别分布")
    store._write_json(json_path, payload)
    return {**result, "metadata": str(json_path),
            "visualization": payload["visualization"]}


@tracked_function("generate-report", store_position=1)
def generate_industry_report(config: dict, store, report_id: str,
                             provider: str = "codex", industry_en: str = "") -> dict:
    from .report_tasks import build_report_tasks
    tasks = build_report_tasks(store, store.name, industry_en)
    task = next((item for item in tasks if item["id"] == report_id), None)
    if task is None:
        raise ValueError(f"未知行业报告：{report_id}")
    horizon = {"trend_5y": "fiveyear", "popular_2y": "biennial",
               "tech_6m": "semiannual"}.get(report_id, "semiannual")
    _ensure_history(config, store, horizon)
    days = {"trend_5y": 1826, "popular_2y": 730, "tech_6m": 183}.get(report_id, 183)
    result = _execute(config, store, task, provider, context_days=days)
    viz_path = Path(result["path"]).with_suffix(".viz.json")
    visualization = _visualization(store, days, "全周期本地证据类别分布")
    visualization["directed_graph"] = _directed_chain(store)
    visualization.update(_provenance(result))
    store._write_json(viz_path, visualization)
    return {**result, "visualization_file": str(viz_path)}


@tracked_function("generate-deep-report", store_position=1)
def generate_deep_report(config: dict, store, report_type: str,
                         provider: str = "codex", industry_en: str = "") -> dict:
    from .deep_reports import build_deep_reports
    _ensure_history(config, store, "quarterly")
    task = build_deep_reports(store, store.name, industry_en, rtype=report_type)[0]
    result = _execute(config, store, task, provider, context_days=90)
    markdown = Path(result["path"]).read_text(encoding="utf-8")
    provenance = _provenance(result)
    _write_deep_sidecars(store, task, markdown, provenance)
    viz_path = Path(result["path"]).with_suffix(".viz.json")
    visualization = _visualization(store, 90, "深度报告证据分布")
    visualization.update(provenance)
    store._write_json(viz_path, visualization)
    return {**result, "visualization_file": str(viz_path)}


@tracked_function("generate-impact", store_position=1)
def generate_impact_report(config: dict, store, profile_config: dict, event: str,
                           provider: str = "codex") -> dict:
    from .impact_engine import analyze_event
    skeleton = analyze_event(store, profile_config, event)
    task = store._read_json(Path(skeleton["task_file"]), {})
    result = _execute(config, store, task, provider, context_days=30)
    metadata_path = Path(skeleton["path"])
    markdown = Path(result["path"]).read_text(encoding="utf-8")
    _merge_impact_metadata(store, metadata_path, markdown, _provenance(result))
    return {**result, "metadata": str(metadata_path)}


def reconcile_existing_step8_artifacts(store, provider: str, model: str) -> dict:
    """Complete metadata contracts from existing Markdown without a model call."""
    provenance = {"provider": provider, "model": model,
                  "status": "draft_review_required"}
    counts = {"industry_reports": 0, "deep_reports": 0, "impact_reports": 0}

    for report_id in ("trend_5y", "popular_2y", "tech_6m"):
        markdown_path = store.reports / f"{report_id}.md"
        if not markdown_path.exists():
            continue
        viz_path = store.reports / f"{report_id}.viz.json"
        visualization = store._read_json(viz_path, {})
        visualization.update(provenance)
        store._write_json(viz_path, visualization)
        counts["industry_reports"] += 1

    deep_dir = store.reports / "deep"
    for markdown_path in sorted(deep_dir.glob("*.md")):
        report_type = markdown_path.stem
        task = {
            "references_file": f"one_time/reports/deep/{report_type}.references.json",
            "claims_file": f"one_time/reports/deep/{report_type}.claims.json",
        }
        markdown = markdown_path.read_text(encoding="utf-8")
        _write_deep_sidecars(store, task, markdown, provenance)
        viz_path = markdown_path.with_suffix(".viz.json")
        visualization = store._read_json(viz_path, {})
        visualization.update(provenance)
        store._write_json(viz_path, visualization)
        counts["deep_reports"] += 1

    impact_root = store.one_time / "impact"
    for markdown_path in sorted(impact_root.glob("*/analysis.md")):
        metadata_path = markdown_path.parent / "impact.json"
        _merge_impact_metadata(
            store, metadata_path, markdown_path.read_text(encoding="utf-8"), provenance)
        counts["impact_reports"] += 1

    return counts
