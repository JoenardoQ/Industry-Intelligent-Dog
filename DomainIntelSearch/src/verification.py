"""多源交叉验证（Source Verification）+ 可信度评分.

把同一事件在不同来源的报道归并为一个"故事"，统计**独立来源数**，
给出 0-1 的 credibility 可信度评分，并把互相印证的来源写进条目的
references[] 字段（解决此前 references 恒为空的问题）。

判定"同一故事"的线索（任一命中即归并）：
  1. 完全相同的 url
  2. 归一化标题高度相似（token Jaccard >= THRESH）
  3. 标题显著 token 序列几乎一致（去掉来源前缀、标点、停用词后）

"独立来源"按来源名 + 链接域名去重；同一家媒体的多条报道不算独立。

可信度评分（诚实封顶 0.95，永不满分）：
  独立来源 1 家 → 0.30（低，单一来源，待核实）
  独立来源 2 家 → 0.60（中，双源印证）
  独立来源 3 家 → 0.78（较高）
  独立来源 >=4 家 → 0.88（高，多源共识）
  高权威源（通讯社/官方/顶会）在场再 +0.07
标签：高(>=0.75) / 中(>=0.5) / 低(<0.5)

产出字段（写回每条 item）：
  credibility       float   可信度 0-1
  credibility_label str     高 / 中 / 低
  source_count      int     独立来源数
  verified          bool    是否被 >=2 个独立来源印证
  references        list    [{title,url,source,date}] 互相印证的来源（不含自身）
"""

from __future__ import annotations

import difflib
import re
from datetime import datetime
from pathlib import Path

from intdog_core import stable_id, tracked_function
from intdog_core.models import canonical_url
from intdog_core.source_trust import publisher_key, source_assessment

# 归一化标题时丢弃的停用词（中英文）
_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "at", "by", "with", "as", "it", "its", "be", "this", "that", "from",
    "的", "了", "和", "与", "在", "是", "将", "对", "为", "等", "于", "及",
}

# 归并阈值（经真实+对照样例标定）：
#   同一事件不同措辞 overlap≈0.47 | 相关但不同事件≈0.19 | 无关≈0.06 | 近似重复≈0.77
SIM_THRESHOLD = 0.42   # token overlap 系数阈值（|交|/min(|A|,|B|)）
MIN_INTER = 3          # 至少共享 3 个 token，防短标题误并
DUP_RATIO = 0.75       # 字符级近似重复直接归并（同稿转载/格式差异）
CLUSTERING_VERSION = "title-entity-event-time-v3"


def _norm_title(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[\|｜\-—_·:：,，.。!！?？()（）\[\]【】\"'“”‘’]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _tokens(title: str) -> set[str]:
    t = _norm_title(title)
    out = set()
    for w in re.split(r"\s+", t):
        if not w or w in _STOP:
            continue
        # 中文按 2-gram 切，英文按词
        if re.search(r"[一-鿿]", w):
            for i in range(len(w) - 1):
                out.add(w[i:i + 2])
            if len(w) <= 3:
                out.add(w)
        else:
            out.add(w)
    return out


def _source_key(item: dict) -> str:
    """Independent publisher key; a domain is one publisher, not one URL."""
    return publisher_key(item)


def source_quality(item: dict) -> tuple[float, str]:
    """Return an explicit source-quality prior and evidence type."""
    return source_assessment(item)


def _story_family(item: dict) -> str:
    category = item.get("category", "")
    return "event" if category in {"news", "funding", "hiring", "ceo", "policy"} \
        else category


def _entity_keys(item: dict) -> set[str]:
    """Return canonical entity identifiers supplied by extraction/resolution."""
    values = item.get("entity_ids") or item.get("entities") or []
    if isinstance(values, (str, dict)):
        values = [values]
    keys = set()
    for value in values:
        if isinstance(value, dict):
            value = value.get("id") or value.get("canonical_id")
        normalized = str(value or "").strip().casefold()
        if normalized:
            keys.add(normalized)
    return keys


def _event_keys(item: dict) -> set[str]:
    """Return reviewed/extracted event identifiers, never title guesses."""
    values = item.get("event_keys") or item.get("event_key") or []
    if isinstance(values, (str, dict)):
        values = [values]
    keys = set()
    for value in values:
        if isinstance(value, dict):
            value = value.get("id") or value.get("canonical_id")
        normalized = str(value or "").strip().casefold()
        if normalized:
            keys.add(normalized)
    return keys


def _event_time(item: dict) -> datetime | None:
    value = item.get("published_at") or item.get("date") or item.get("published")
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _same_entity_window(a: dict, b: dict, max_days: int = 2) -> bool:
    if not (_entity_keys(a) & _entity_keys(b)):
        return False
    # Entity + time alone is not an event identity: one company can launch a
    # product, file results and face a policy action on the same day.
    if not (_event_keys(a) & _event_keys(b)):
        return False
    a_time, b_time = _event_time(a), _event_time(b)
    if a_time is None or b_time is None:
        return False
    if a_time.tzinfo is None:
        a_time = a_time.replace(tzinfo=b_time.tzinfo)
    if b_time.tzinfo is None:
        b_time = b_time.replace(tzinfo=a_time.tzinfo)
    return abs((a_time - b_time).total_seconds()) <= max_days * 86400


def _same_story(a_str: str, b_str: str, a_tok: set[str], b_tok: set[str]) -> bool:
    """判同一事件：近似重复（字符比率）或 token 重叠足够（overlap 系数 + 最小交集）."""
    if a_tok and b_tok:
        inter = len(a_tok & b_tok)
        ov = inter / float(min(len(a_tok), len(b_tok)))
        if inter >= MIN_INTER and ov >= SIM_THRESHOLD:
            return True
    if difflib.SequenceMatcher(None, a_str, b_str).ratio() >= DUP_RATIO:
        return True
    return False


def group_stories(items: list[dict]) -> list[list[int]]:
    """把条目索引按"同一故事"分组（贪心并查）.

    归并条件（任一）：完全相同 url；或 _same_story 判定为同一事件。
    """
    n = len(items)
    norms = [_norm_title(it.get("title", "")) for it in items]
    toks = [_tokens(it.get("title", "")) for it in items]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    seen_url: dict[str, int] = {}
    for i, it in enumerate(items):
        u = (it.get("url") or "").strip()
        if u:
            if u in seen_url:
                union(i, seen_url[u])
            else:
                seen_url[u] = i
    inverted: dict[str, set[int]] = {}
    entity_inverted: dict[str, set[int]] = {}
    prefixes: dict[str, set[int]] = {}
    for index, token_set in enumerate(toks):
        for token in token_set:
            inverted.setdefault(token, set()).add(index)
        for entity in _entity_keys(items[index]):
            entity_inverted.setdefault(entity, set()).add(index)
        prefixes.setdefault(norms[index][:12], set()).add(index)
    for i in range(n):
        candidates = set()
        for token in toks[i]:
            candidates.update(inverted[token])
        for entity in _entity_keys(items[i]):
            candidates.update(entity_inverted[entity])
        candidates.update(prefixes.get(norms[i][:12], set()))
        for j in sorted(index for index in candidates if index > i):
            if find(i) == find(j):
                continue
            if (_story_family(items[i]) == _story_family(items[j]) and (
                    _same_story(norms[i], norms[j], toks[i], toks[j]) or
                    _same_entity_window(items[i], items[j]))):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def score_group(members: list[dict]) -> dict:
    """Score source reliability separately from corroboration."""
    srcs = {_source_key(m) for m in members}
    n = len(srcs)
    qualities = [source_quality(member) for member in members]
    quality = max(q[0] for q in qualities)
    corroboration = {1: 0.0, 2: 0.08, 3: 0.14}.get(n, 0.18)
    cred = min(round(quality + corroboration, 2), 0.95)
    label = "高" if cred >= 0.75 else ("中" if cred >= 0.5 else "低")
    return {"credibility": cred, "source_count": n,
            "source_quality": quality,
            "evidence_type": max(qualities, key=lambda q: q[0])[1],
            "corroborated": n >= 2,
            "credibility_label": label, "verified": n >= 2}


def verify_items(items: list[dict]) -> list[dict]:
    """对一批条目做交叉验证，原地补充 credibility/source_count/references 等字段."""
    groups = group_stories(items)
    for idxs in groups:
        members = [items[i] for i in idxs]
        sc = score_group(members)
        for i in idxs:
            it = items[i]
            # references：组内其它来源（按 url 去重，排除自身）
            refs = []
            self_url = (it.get("url") or "").strip()
            seen = {self_url}
            own_publisher = _source_key(it)
            for j in idxs:
                if j == i:
                    continue
                m = items[j]
                mu = (m.get("url") or "").strip()
                if mu in seen or _source_key(m) == own_publisher:
                    continue
                seen.add(mu)
                refs.append({
                    "title": m.get("title", ""),
                    "url": mu,
                    "source": m.get("source", ""),
                    "date": m.get("date", ""),
                })
            it.update(sc)
            it["credibility_score"] = sc["credibility"]
            it["evidence_status"] = "corroborated" if sc["corroborated"] else (
                "verified" if sc["evidence_type"] in {"official_primary", "primary_record"}
                else "collected")
            type_evidence = 1.0 if it.get("classification_reason") else 0.6
            it["ranking_score"] = round(
                sc["credibility"] * 0.7 + min(sc["source_count"], 4) / 4 * 0.2
                + type_evidence * 0.1, 3)
            it["references"] = refs
    return items


@tracked_function("verify")
def verify_store_daily(store, date: str = None, days: int = 1) -> dict:
    """对某行业每日情报做交叉验证并回写.

    days=1：只验指定日/最近一天（旧行为）；
    days=N（>1）：把最近 N 天的全部条目**跨天统一归并**——同一事件即使隔天才被
    第二家媒体报道，也能正确累计独立来源数（解决单日验证可信度全低的问题）。

    跨类别归并（同一故事可能同时出现在 news 与 funding），再按来源文件写回。
    返回统计 {stories, verified_items, high, medium, low, days}.
    """
    items: list[dict] = []
    if days > 1:
        items = store.list_daily_range(days=days, end_date=date)
    else:
        items = store.list_daily(date=date)
    if not items:
        return {"stories": 0, "verified_items": 0, "high": 0, "medium": 0,
                "low": 0, "days": days}
    verify_items(items)

    # Persist claim-level provenance.  The legacy numeric ``credibility`` field
    # remains for UI compatibility; evidence_status is the lifecycle state.
    claim_bundles = []
    story_bundles = []
    groups = group_stories(items)
    for indexes in groups:
        members = [items[index] for index in indexes]
        representative = max(members, key=lambda item: item.get("ranking_score", 0))
        score = score_group(members)
        status = "corroborated" if score["corroborated"] else (
            "verified" if score["evidence_type"] in {"official_primary", "primary_record"}
            else "collected")
        evidence = []
        for member in members:
            url = canonical_url(member.get("url", ""))
            if not url:
                continue
            evidence.append({
                "relation": "supports", "document_id": stable_id("doc", url),
                "excerpt": member.get("abstract") or member.get("summary", ""),
                "publisher_cluster": _source_key(member),
                "extraction_method": "story_cluster",
                "confidence": member.get("credibility_score")})
        claim_bundles.append({
            "predicate": "reports_event",
            "object": {"title": representative.get("title", ""),
                       "category": representative.get("category", "news")},
            "qualifiers": {"independent_publishers": score["source_count"],
                           "source_quality": score["source_quality"],
                           "evidence_type": score["evidence_type"]},
            "valid_from": representative.get("date", ""), "status": status,
            "evidence": evidence})
        story_bundles.append({
            "title": representative.get("title", ""),
            "story_family": _story_family(representative),
            "status": status,
            "metadata": {
                "independent_publishers": score["source_count"],
                "source_quality": score["source_quality"],
            },
            "documents": [{
                "document_id": stable_id("doc", canonical_url(member.get("url", ""))),
                "publisher_cluster": _source_key(member),
                "observed_at": member.get("date") or member.get("published_at"),
            } for member in members if canonical_url(member.get("url", ""))],
        })
    # A rolling verification window is an observation window, not the lifetime
    # of a historical event.  Upsert matching claims without superseding every
    # older event that simply fell outside the current window.
    store.service.repo.save_claim_bundles(store.folder, claim_bundles)
    store.service.repo.save_story_groups(
        store.folder, story_bundles, CLUSTERING_VERSION)

    # 按来源文件回写（保留全部原有 + 新增字段）
    by_file: dict[str, list[dict]] = {}
    for it in items:
        f = it.pop("_file", None)
        if f:
            by_file.setdefault(f, []).append(it)
    for f, arr in by_file.items():
        store._write_json(Path(f), arr)
        path = Path(f)
        store.service.import_daily(store.folder, path.stem, path.parent.name, arr)

    stats = {"stories": len(groups), "verified_items": 0,
             "high": 0, "medium": 0, "low": 0, "days": days}
    for it in items:
        if it.get("verified"):
            stats["verified_items"] += 1
        lbl = it.get("credibility_label", "低")
        stats[{"高": "high", "中": "medium", "低": "low"}[lbl]] += 1
    return stats
