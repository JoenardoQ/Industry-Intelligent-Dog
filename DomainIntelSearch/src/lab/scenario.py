"""Evidence-aware value-chain scenario propagation."""

from __future__ import annotations

import heapq
import itertools

from .contracts import mermaid_text


RELATION_DECAY = {"supplies": 0.72, "depends_on": 0.70, "enables": 0.62,
                  "substitutes": 0.48, "competes_capacity": 0.42,
                  "ordered_fallback": 0.65}


def _edge_factor(edge: dict, semantic_factor: float = 1.0) -> float:
    base = RELATION_DECAY.get(edge["relation"], 0.5)
    confidence = edge.get("confidence")
    confidence = 0.5 if confidence is None else max(0.0, min(1.0, float(confidence)))
    evidence = max(0, int(edge.get("evidence_count", 0) or 0))
    return round(base * semantic_factor * (0.5 + confidence * 0.5) *
                 (0.75 + min(5, evidence) * 0.05), 4)


def _traversals(edge: dict) -> tuple[tuple[str, str, float, str], ...]:
    """Return (from, to, semantic multiplier, default effect) traversals."""
    relation = edge.get("relation", "supplies")
    semantics = {
        "supplies": (("src", "dst", 1.0, "same"),
                     ("dst", "src", 0.68, "mixed")),
        "depends_on": (("dst", "src", 1.0, "same"),
                       ("src", "dst", 0.55, "mixed")),
        "enables": (("src", "dst", 0.92, "same"),
                    ("dst", "src", 0.45, "mixed")),
        "substitutes": (("src", "dst", 0.72, "inverse"),
                        ("dst", "src", 0.72, "inverse")),
        "competes_capacity": (("src", "dst", 0.62, "inverse"),
                              ("dst", "src", 0.62, "inverse")),
    }
    return semantics.get(relation, semantics["supplies"])


def build_chain_scenario(event: str, requested_chain: str, max_hops: int,
                         nodes: list[dict], roles: list[dict], edges: list[dict]) -> dict:
    node_index = {node["id"]: i for i, node in enumerate(nodes)}
    direct, needle = set(), (requested_chain or event).casefold()
    for index, node in enumerate(nodes):
        if node["name"].casefold() in needle or needle in node["name"].casefold():
            direct.add(index)
    if not requested_chain:
        for role in roles:
            names = (role.get("canonical_name") or "", role.get("name_en") or "")
            if any(name and name.casefold() in needle for name in names):
                index = node_index.get(role["chain_node_id"])
                if index is not None:
                    direct.add(index)

    graph: dict[int, list[tuple[int, dict, str, float, str]]] = {
        i: [] for i in range(len(nodes))}
    topology = "evidence_edges" if edges else "ordered_fallback"
    if edges:
        for edge in edges:
            src, dst = node_index.get(edge["src_node_id"]), node_index.get(edge["dst_node_id"])
            if src is None or dst is None:
                continue
            endpoints = {"src": src, "dst": dst}
            for start, finish, multiplier, effect in _traversals(edge):
                direction = "downstream" if start == "src" else "upstream"
                graph[endpoints[start]].append(
                    (endpoints[finish], edge, direction, multiplier, effect))
    else:
        for index in range(len(nodes) - 1):
            forward = {"id": f"fallback:{index}", "relation": "ordered_fallback",
                       "confidence": 0.5, "evidence_count": 0}
            graph[index].append((index + 1, forward, "downstream", 1.0, "same"))
            graph[index + 1].append((index, forward, "upstream", 0.7, "mixed"))

    sequence = itertools.count()
    queue = [(-1.0, 0, index, next(sequence), index, [index], [])
             for index in sorted(direct)]
    heapq.heapify(queue)
    best: dict[int, tuple[float, int, int, list[int], list[dict]]] = {}
    while queue:
        negative, distance, index, _, origin, path, path_edges = heapq.heappop(queue)
        score = -negative
        if distance > max(0, max_hops) or (index in best and best[index][0] >= score):
            continue
        best[index] = (score, distance, origin, path, path_edges)
        for nxt, edge, direction, semantic_factor, default_effect in graph[index]:
            if nxt in path:
                continue
            effect = edge.get("effect") or default_effect
            step = {"edge_id": edge["id"], "relation": edge["relation"],
                    "direction": direction,
                    "factor": _edge_factor(edge, semantic_factor),
                    "effect": effect,
                    "lag_days": max(0, int(edge.get("lag_days", 0) or 0)),
                    "confidence": edge.get("confidence"),
                    "evidence_count": edge.get("evidence_count", 0)}
            heapq.heappush(queue, (-score * step["factor"], distance + 1, nxt,
                                  next(sequence), origin, [*path, nxt],
                                  [*path_edges, step]))
    impacts = []
    for index, (score, distance, origin, path, path_edges) in sorted(best.items()):
        direction = ("direct" if distance == 0 else
                     path_edges[-1]["direction"] if path_edges else "direct")
        exposure = round(score, 4)
        cumulative_lag = sum(step["lag_days"] for step in path_edges)
        path_effects = [step["effect"] for step in path_edges]
        if not path_effects:
            aggregate_effect = "direct"
        elif any(effect in {"mixed", "uncertain"} for effect in path_effects):
            aggregate_effect = "mixed"
        else:
            inverse_count = sum(effect in {"inverse", "negative"}
                                for effect in path_effects)
            aggregate_effect = "negative" if inverse_count % 2 else "positive"
        impacts.append({"node_id": nodes[index]["id"], "node": nodes[index]["name"],
                        "direction": direction, "distance": distance,
                        "score": exposure,
                        "heuristic_exposure_score": exposure,
                        "sensitivity_interval": [round(exposure * 0.75, 4),
                                                 round(min(1.0, exposure * 1.25), 4)],
                        "effect": aggregate_effect,
                        "cumulative_lag_days": cumulative_lag,
                        "path": [nodes[position]["name"] for position in path],
                        "path_edges": path_edges,
                        "basis": "explicit_or_name_match" if not path_edges else topology})
    status = "completed" if direct else "unresolved"
    return {"kind": "chain_scenario", "status": status, "event": event,
            "requested_chain": requested_chain, "max_hops": max_hops,
            "topology": topology, "direct_nodes": [nodes[i]["name"] for i in sorted(direct)],
            "impacts": impacts,
            "score_semantics": "heuristic_exposure_not_probability",
            "interpretation": ("从直接命中节点沿可检查产业链边衰减传播。" if direct else
                               "事件未命中已知节点；请显式提供产业链节点。")}


def mermaid_for_scenario(nodes: list[dict], edges: list[dict], direct_ids: set[str]) -> str:
    ids = {node["id"]: f"N{index}" for index, node in enumerate(nodes)}
    lines = ["graph LR"]
    for node in nodes:
        lines.append(f'  {ids[node["id"]]}["{mermaid_text(node["name"])}"]')
    render_edges = edges
    if not render_edges:
        render_edges = [
            {"src_node_id": nodes[index]["id"],
             "dst_node_id": nodes[index + 1]["id"], "relation": "ordered_fallback"}
            for index in range(max(0, len(nodes) - 1))]
    for edge in render_edges:
        if edge["src_node_id"] in ids and edge["dst_node_id"] in ids:
            label = mermaid_text(edge["relation"])
            lines.append(f'  {ids[edge["src_node_id"]]} -->|{label}| '
                         f'{ids[edge["dst_node_id"]]}')
    for node_id in direct_ids:
        if node_id in ids:
            lines.append(f"  style {ids[node_id]} fill:#6f6aa8,color:#fff")
    return "\n".join(lines) + "\n"
