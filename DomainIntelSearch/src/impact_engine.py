"""行业事件影响引擎（Impact Engine）.

给定一个行业事件（如"美国限制 GPU 出口"），自动完成四层关联：
  1. 受影响公司   —— 知识库企业实体 + 行业档案 tracked_companies 中，
                     名称/别名出现在事件语料里，或所属产业链被命中的
  2. 关联供应链   —— 三层知识结构的产业链层级（设计/制造/封装…）被事件命中
  3. 相关论文     —— 近期 papers 类条目标题/摘要与事件主题重叠
  4. 相关政策     —— 近期 news 类条目中带政策信号且与事件主题重叠

并生成一份"影响分析"LLM 任务包（模型无关，交给任意 agent 执行回写）。

同时提供 detect_events()：从最近一天情报里自动筛出"值得做影响分析的事件"
    （可靠一手/主流来源的政策信号，或被 >=2 独立来源印证的故事）。

存储：DomainIntelData/<行业>/one_time/impact/
  events.json                 自动检测到的事件清单
  <事件slug>/impact.json      结构化关联结果 + 分析任务包
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import verification as V

# 政策/监管信号（用于"相关政策"关联 与 事件检测）
POLICY_KW = ["限制", "禁令", "出口", "管制", "制裁", "关税", "法案", "监管",
             "补贴", "许可", "审查", "实体清单", "ban", "export", "sanction",
             "tariff", "regulation", "policy", "restrict", "curb", "chips act"]
# 事件性信号（融资/人事之外的"行业级大事"）
EVENT_KW = POLICY_KW + ["发布", "突破", "量产", "收购", "合并", "宣战",
                        "launch", "release", "breakthrough", "acquire", "merger"]


def _slug(text: str, maxlen: int = 24) -> str:
    """事件名转安全目录名（保留中英文，替换非法字符）."""
    s = re.sub(r"[^\w一-鿿]+", "_", text.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:maxlen] or "event"


def _kw_hits(text: str, kws: list[str]) -> list[str]:
    low = text.lower()
    return [k for k in kws if k.lower() in low]


def _overlap(query_toks: set[str], item: dict) -> int:
    """事件 token 与条目（标题+摘要）的重叠数."""
    blob = (item.get("title", "") or "") + " " + (item.get("abstract", "") or "")
    return len(query_toks & V._tokens(blob))


# ----------------------------------------------------------------------
# 事件检测：从最近一天情报中筛出值得深挖的事件
# ----------------------------------------------------------------------
def detect_events(store, date: str = None, limit: int = 20) -> list[dict]:
    """从每日情报检测行业级事件.

    入选条件（任一）：
      a) 标题/摘要含政策/事件信号词
      b) 被 >=2 个独立来源印证（verified=True）
    按 credibility 降序返回，附命中信号说明。
    """
    items = store.list_daily(date=date)
    if not items:
        return []
    # 若条目尚无 credibility 字段，现场算一遍（不回写）
    if not any("credibility" in it for it in items):
        V.verify_items(items)

    events = []
    for it in items:
        blob = (it.get("title", "") or "") + " " + (it.get("abstract", "") or "")
        sig = _kw_hits(blob, EVENT_KW)
        verified = it.get("verified", False)
        reliable_signal = bool(sig) and it.get("credibility", 0) >= 0.70
        if not reliable_signal and not verified:
            continue
        events.append({
            "title": it.get("title", ""),
            "url": it.get("url", ""),
            "source": it.get("source", ""),
            "date": it.get("date", ""),
            "category": it.get("category", ""),
            "credibility": it.get("credibility", 0.3),
            "credibility_label": it.get("credibility_label", "低"),
            "source_count": it.get("source_count", 1),
            "signals": sig,
            "why": ("政策/监管信号: " + ",".join(sig[:4])) if sig else "多源印证",
        })
    # 可信度优先，其次独立来源数
    events.sort(key=lambda e: (-e["credibility"], -e["source_count"]))
    events = events[:limit]

    # 落盘清单
    out_path = store.one_time / "impact" / "events.json"
    _write(out_path, {
        "industry": store.name,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(events),
        "events": events,
    })
    return events


# ----------------------------------------------------------------------
# 事件影响分析：事件 → 公司/供应链/论文/政策 四层关联
# ----------------------------------------------------------------------
def analyze_event(store, pcfg: dict, event: str, date: str = None) -> dict:
    """对一个事件做四层关联分析并落盘，返回结构化结果.

    返回 {event, affected_companies[], affected_chains[], related_papers[],
          related_policies[], path, task_file}
    """
    from .knowledge_model import KnowledgeModel
    from .landscape import _names_from_profile

    q_toks = V._tokens(event)
    q_blob = event.lower()
    daily = store.list_daily(date=date)

    km = KnowledgeModel(store.knowledge)
    chains = km.get_chains()
    entities = km.get_entities()
    tracked = _names_from_profile(pcfg)

    # ---- 1) 关联产业链（第二层）：链名 token 与事件重叠，或链上实体被点名 ----
    affected_chains: list[str] = []
    chain_of_company: dict[str, str] = {}
    for e in entities:
        chain_of_company[e["name"]] = e.get("chain", "")
    for c in chains:
        cname = c.get("name", "")
        if cname and (cname in event or len(V._tokens(cname) & q_toks) >= 2):
            affected_chains.append(cname)

    # ---- 2) 受影响公司：直接点名 或 所属链被命中 或 在事件相关新闻里高频出现 ----
    affected: dict[str, str] = {}   # name -> 命中原因
    all_names = list(dict.fromkeys(tracked + [e["name"] for e in entities
                                              if e.get("type") == "company"]))
    # 别名表：中文名 + 英文名都算同一家
    en_of = {e["name"]: (e.get("name_en") or "") for e in entities}

    def _aliases(name: str) -> list[str]:
        return [a for a in (name, en_of.get(name, "")) if a]

    for name in all_names:
        if not name:
            continue
        if any(a.lower() in q_blob or a in event for a in _aliases(name)):
            affected[name] = "事件直接点名"
    # 事件相关条目（重叠 >=2 token）里被提及的公司
    related_items = [it for it in daily if _overlap(q_toks, it) >= 2]
    for name in all_names:
        if name in affected:
            continue
        hits = sum(1 for it in related_items
                   if any(a in ((it.get("title", "") or "") + (it.get("abstract", "") or ""))
                          for a in _aliases(name)))
        if hits:
            affected[name] = f"出现在 {hits} 条事件相关情报"
    # 所属链被命中的公司
    for name in all_names:
        if name in affected:
            continue
        if chain_of_company.get(name) in affected_chains and affected_chains:
            affected[name] = f"所属产业链[{chain_of_company[name]}]被命中"

    # 若产业链此前为空但命中了公司，回填公司所在链
    for name in affected:
        ch = chain_of_company.get(name)
        if ch and ch not in affected_chains:
            affected_chains.append(ch)

    # ---- 3) 相关论文：papers 类，主题重叠 >=2 ----
    related_papers = []
    for it in daily:
        if (it.get("category") or "") != "papers":
            continue
        ov = _overlap(q_toks, it)
        if ov >= 2:
            related_papers.append({
                "title": it.get("title", ""), "url": it.get("url", ""),
                "source": it.get("source", ""), "date": it.get("date", ""),
                "overlap": ov,
            })
    related_papers.sort(key=lambda p: -p["overlap"])

    # ---- 4) 相关政策：news 类带政策信号 且（主题重叠 或 事件本身即政策） ----
    related_policies = []
    for it in daily:
        if (it.get("category") or "") not in ("news", "policy"):
            continue
        blob = (it.get("title", "") or "") + " " + (it.get("abstract", "") or "")
        sig = _kw_hits(blob, POLICY_KW)
        ov = _overlap(q_toks, it)
        if sig and ov >= 2:
            related_policies.append({
                "title": it.get("title", ""), "url": it.get("url", ""),
                "source": it.get("source", ""), "date": it.get("date", ""),
                "policy_signals": sig, "overlap": ov,
                "credibility_label": it.get("credibility_label", "低"),
            })
    related_policies.sort(key=lambda p: (-p["overlap"], p["date"]))

    # ---- 5) 影响分析 LLM 任务包（模型无关） ----
    task = _build_impact_task(store.name, event, affected, affected_chains,
                              related_papers, related_policies)

    # ---- 落盘 ----
    edir = store.one_time / "impact" / _slug(event)
    result = {
        "industry": store.name,
        "event": event,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "affected_companies": list(affected.keys()),
        "affected_detail": [{"name": n, "reason": r} for n, r in affected.items()],
        "affected_chains": affected_chains,
        "related_papers": related_papers,
        "related_policies": related_policies,
        "analysis_task": task,
        "note": "代码部分给出客观关联骨架；叙事性影响分析见 analysis_task，"
                "交给任意 agent 执行后回写 analysis.md。",
    }
    _write(edir / "impact.json", result)
    _write(edir / "analysis_task.json", task)

    return {
        "event": event,
        "affected_companies": list(affected.keys()),
        "affected_chains": affected_chains,
        "related_papers": related_papers,
        "related_policies": related_policies,
        "path": str(edir / "impact.json"),
        "task_file": str(edir / "analysis_task.json"),
    }


def _build_impact_task(industry: str, event: str, affected: dict,
                       chains: list, papers: list, policies: list) -> dict:
    """生成"影响分析"叙事报告的 LLM 任务包."""
    comp = "、".join(affected.keys()) or "（代码层未命中，请自行研判）"
    chn = "、".join(chains) or "（未命中已知产业链层级）"
    ref_lines = []
    for i, p in enumerate(policies[:8] + papers[:8], 1):
        ref_lines.append(f"[{i}] {p['title']} — {p.get('source','')} {p.get('url','')}")
    refs = "\n".join(ref_lines) or "（暂无本地引用，请联网补充）"

    prompt = f"""你是"{industry}"行业的资深政策与产业分析师。请针对以下事件输出一份【影响分析】（Markdown，可直接作为研究初稿）：

事件：{event}

代码层已自动关联（供参考，可校正增删）：
- 受影响公司：{comp}
- 关联产业链环节：{chn}

本地语料中的相关条目（引用编号）：
{refs}

请输出：
1. 事件概述（一句话 + 关键事实，引用 [n]）
2. 受影响公司清单：逐家说明 受影响方式/程度（直接受限/供应链传导/需求变化/利好替代），引用 [n]
3. 供应链传导分析：从上游到下游逐环节说明冲击路径
4. 相关技术与论文：该事件涉及的技术方向，关联论文 [n]
5. 相关政策脉络：与既有政策的关系、后续政策预判 [n]
6. 影响等级评估：短期(3个月)/中期(1年)/长期(3年) 各给 高/中/低 与理由
7. 投资/产业启示（3-5 条要点）
要求：每个论断附来源 [n]；文末 references[]（含 url 与日期）；区分"事实"与"研判"。
输出 JSON：{{"summary": "...", "companies": [...], "supply_chain": [...],
  "papers": [...], "policies": [...], "impact_rating": {{...}}, "takeaways": [...],
  "references": [...]}}，并把 Markdown 正文写入 analysis.md。"""
    return {
        "type": "impact_analysis",
        "industry": industry,
        "event": event,
        "prompt": prompt,
        "output_file": f"one_time/impact/{_slug(event)}/analysis.md",
    }


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)
