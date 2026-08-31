"""Human-readable renderers kept separate from analysis algorithms."""

from __future__ import annotations


def evidence_markdown(payload: dict) -> str:
    metrics = payload["metrics"]
    lines = ["# Evidence Graph", "", f"- 当前主张：{metrics['claims']}",
             f"- 无支持证据：{metrics['unsupported']}",
             f"- 单一来源：{metrics['single_source']}",
             f"- 存在反驳：{metrics['contested']}",
             f"- 多发布者簇印证：{metrics['corroborated']}",
             f"- 产业链覆盖缺口：{metrics['chain_gaps']}", "", "## 优先证据缺口", ""]
    for item in payload["claims"]:
        if item["evidence_state"] != "corroborated":
            lines.append(f"- `{item['evidence_state']}` {item['subject'] or '未绑定实体'} · "
                         f"{item['predicate']} · claim `{item['id']}`")
    if not payload["claims"]:
        lines.append("- 尚无结构化主张；应先从高质量文档抽取 Claim–Evidence。")
    return "\n".join(lines)


def sources_markdown(payload: dict) -> str:
    metrics = payload["metrics"]
    lines = ["# Source Observatory", "", f"- 来源链接：{metrics['source_links']}",
             f"- 独立发布者簇：{metrics['publisher_clusters']}",
             f"- 唯一来源：{metrics['unique_sources']}",
             f"- 来源链接 HHI：{metrics['source_link_hhi']}",
             f"- 文档产出 HHI：{metrics['document_hhi']}", f"- 活跃：{metrics['active']}",
             f"- 未认证：{metrics['unverified']}", f"- 陈旧：{metrics['stale']}",
             f"- 尚未产出文档：{metrics['unused']}", f"- 人工关注：{metrics['manual_watch']}",
             f"- 缺失类别：{', '.join(payload['missing_categories']) or '无'}", "", "## 需要关注", ""]
    lines.extend(f"- `{item['health_status']}` {item['name']} · {item['category']} · {item['url']}"
                 for item in payload["sources"] if item["health_status"] != "active")
    return "\n".join(lines)


def scenario_markdown(payload: dict) -> str:
    lines = [f"# 产业链情景：{payload['event']}", "", f"状态：`{payload['status']}`",
             f"拓扑：`{payload['topology']}`",
             f"直接命中：{', '.join(payload['direct_nodes']) or '无'}", "", "## 传播结果", ""]
    lines.extend(f"- {item['node']} · {item['direction']} · 距离 {item['distance']} · "
                 f"启发式暴露 {item['heuristic_exposure_score']} · "
                 f"效应 {item['effect']} · 滞后 {item['cumulative_lag_days']} 天 · "
                 f"{' → '.join(item['path'])}"
                 for item in payload["impacts"])
    return "\n".join(lines)


def agenda_markdown(active: list[dict]) -> str:
    lines = ["# Knowledge Boundary Research Agenda", "", f"可行动议程：{len(active)}", ""]
    for item in active:
        lines.extend([f"## P{item['priority']} · {item['title']} · `{item['status']}`", "",
                      item["rationale"], "", "建议检索："])
        lines.extend(f"- {query}" for query in item["queries"])
        lines.append("")
    return "\n".join(lines)
