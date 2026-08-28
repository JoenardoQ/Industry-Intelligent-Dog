"""竞争格局分析（Competitive Landscape）.

自动维护四类玩家并跟踪变化：
  Leader      领导者   —— 仅接受有市场份额/规模证据的知识库标注（默认不自动认定）
  Challenger  挑战者   —— 知识库企业实体中、近期被新闻/融资频繁提及者
  Emerging    新兴公司 —— 出现在融资新闻里的公司（拿新钱=扩张信号）
  Declining   衰退公司 —— 出现在裁员/亏损/下滑信号新闻里的公司

代码部分给出**基于提及量与信号**的客观骨架；定性的市场份额与格局研判
以 LLM 任务包（模型无关）产出，交给任意 agent 执行后回写。

存储：DomainIntelData/<行业>/one_time/landscape/
  landscape.json      最新格局（四类 + 提及量 + 信号）
  history/<YYYY-MM-DD>.json   每日快照（用于跟踪份额/地位变化）
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

TIER_LABELS = {
    "leader": "领导者 Leader",
    "challenger": "挑战者 Challenger",
    "emerging": "新兴 Emerging",
    "declining": "衰退 Declining",
}

# 衰退信号关键词
DECLINE_KW = ["裁员", "亏损", "下滑", "倒闭", "破产", "退市", "layoff",
              "loss", "decline", "bankrupt", "downgrade", "砍单", "去库存"]
# 融资/扩张信号（判定 emerging 用，配合 funding 类别）
EMERGE_KW = ["融资", "轮", "估值", "募资", "IPO", "raised", "funding",
             "series", "venture", "seed"]


def _names_from_profile(pcfg: dict) -> list[str]:
    out = []
    for c in (pcfg.get("domain", {}) or {}).get("tracked_companies", []) or []:
        n = c.get("name") if isinstance(c, dict) else str(c)
        if n:
            out.append(n)
    return out


def _mention_count(name: str, items: list[dict]) -> int:
    if not name:
        return 0
    cnt = 0
    for it in items:
        blob = (it.get("title", "") + " " + it.get("abstract", ""))
        if name in blob:
            cnt += 1
    return cnt


def _hits_kw(name: str, items: list[dict], kws: list[str]) -> int:
    cnt = 0
    for it in items:
        blob = (it.get("title", "") + " " + it.get("abstract", "")).lower()
        if name and name.lower() in blob and any(k.lower() in blob for k in kws):
            cnt += 1
    return cnt


def build_landscape(store, pcfg: dict) -> dict:
    """计算并保存某行业的竞争格局，返回结构化结果（含写盘路径）."""
    from .knowledge_model import KnowledgeModel

    now = datetime.now()
    # 语料：近 30 天全部六类 + 单独取融资类
    daily = store.list_daily_range(days=30)
    funding = [it for it in daily if (it.get("category") == "funding"
                                       or it.get("_cat") == "funding")]

    leaders = _names_from_profile(pcfg)
    km = KnowledgeModel(store.knowledge)
    entity_companies = [e["name"] for e in km.get_entities(etype="company")]
    tiers = {"leader": [], "challenger": [], "emerging": [], "declining": []}

    # tracked_companies 只是观察名单，不等于市场领导者。没有份额证据时放入
    # challenger 候选，等待 market_share_task 校正。
    for name in leaders:
        tiers["challenger"].append({
            "name": name,
            "mentions": _mention_count(name, daily),
            "signal": "tracked_candidate",
            "reason": "重点观察名单；尚无市场份额证据，不自动认定为 Leader",
        })

    for name in entity_companies:
        if name in leaders:
            continue
        m = _mention_count(name, daily)
        if _hits_kw(name, daily, DECLINE_KW):
            tiers["declining"].append({"name": name, "mentions": m,
                                       "signal": "decline_news",
                                       "reason": "出现裁员/亏损/下滑信号"})
        elif _hits_kw(name, funding, EMERGE_KW):
            tiers["emerging"].append({"name": name, "mentions": m,
                                       "signal": "recent_funding",
                                       "reason": "近期获得融资；仍需核验轮次与金额"})
        elif m >= 2:
            tiers["challenger"].append({"name": name, "mentions": m,
                                        "signal": "rising_mentions",
                                        "reason": "近期被新闻/融资频繁提及"})
        else:
            tiers["challenger"].append({"name": name, "mentions": m,
                                        "signal": "known_entity",
                                        "reason": "知识库收录企业"})

    # 各档按提及量降序
    for t in tiers.values():
        t.sort(key=lambda e: -e["mentions"])

    task = _build_task(store.name, tiers)
    payload = {
        "industry": store.name,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "tiers": tiers,
        "labels": TIER_LABELS,
        "market_share_task": task,
        "note": "这是候选骨架，不是公司排名。Leader 默认留空；只有经市场份额/规模证据核验后才能进入。",
    }

    # 写最新 + 历史快照
    ldir = store.one_time / "landscape"
    hdir = ldir / "history"
    hdir.mkdir(parents=True, exist_ok=True)
    latest = ldir / "landscape.json"
    snap = hdir / f"{now.strftime('%Y-%m-%d')}.json"
    for p in (latest, snap):
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)

    return {"path": str(latest), "tiers": tiers, "labels": TIER_LABELS,
            "history": str(snap)}


def share_trend(store, company: str) -> list[dict]:
    """读取某公司历史快照中的提及量序列（份额/地位变化的代理指标）."""
    hdir = store.one_time / "landscape" / "history"
    if not hdir.exists():
        return []
    out = []
    for f in sorted(hdir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        mentions = 0
        for tier in data.get("tiers", {}).values():
            for e in tier:
                if e.get("name") == company:
                    mentions = e.get("mentions", 0)
        out.append({"date": f.stem, "mentions": mentions})
    return out


def _build_task(industry: str, tiers: dict) -> dict:
    """市场份额与格局研判的 LLM 任务包（模型无关）."""
    def names(t):
        return "、".join(e["name"] for e in tiers.get(t, [])) or "（待补）"
    prompt = f"""你是"{industry}"行业的资深竞争格局分析师。已知四类玩家骨架：
- 领导者 Leader：{names('leader')}
- 挑战者 Challenger：{names('challenger')}
- 新兴 Emerging：{names('emerging')}
- 衰退 Declining：{names('declining')}

请输出一份【竞争格局分析】（Markdown）：
1. 按"市场份额/技术领先度/增长势能"校正上述四类归属（可移动、可增删，给出理由）
2. 估算主要玩家的市场份额（%），并标注估算依据与数据来源 [n]
3. 指出近一年格局的关键变化（谁升谁降、为什么）
4. 每个论断附来源 [n]，文末 references[]（含 url 与日期）。
输出 JSON：{{"leader":[...],"challenger":[...],"emerging":[...],"declining":[...],
  "market_share":[{{"name","share_pct","basis","refs":[url]}}]}}"""
    return {"type": "competitive_landscape", "industry": industry,
            "prompt": prompt,
            "output_file": "one_time/landscape/landscape.md"}
