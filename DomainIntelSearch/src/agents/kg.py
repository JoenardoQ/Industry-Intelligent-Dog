"""KnowledgeGraph Agent：从归档数据构建知识图谱（entities/edges 表）+ Mermaid 导出.

数据来源（Phase 1，纯代码，无需 LLM）：
1. value_chain.json          → 行业/层级实体 + member_of 边
2. companies/companies.json  → 公司实体 + 所属层级边 + 竞争/供应边（若 LLM 已填）
3. timeline/events.json      → 事件入 events 表
4. articles 表               → 新闻提及公司 → mentioned_in 共现边

LLM 补强（Phase 2）：company deep_dive JSON 中的 customers/suppliers/competitors
字段回灌后自动生成 supplies/competes 关系。
"""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3

from .base import BaseAgent
from ..schema import IIOSRecord


class KnowledgeGraphAgent(BaseAgent):
    name = "kg"
    agent_type = "code"
    description = "构建知识图谱：实体抽取 + 关系边 + Mermaid 导出"

    def __init__(self, ctx, store=None):
        super().__init__(ctx)
        if store is None:
            from ..services.archive_store import ArchiveStore
            store = ArchiveStore(ctx.config, root=ctx.industry_root, db_only=True)
        self.store = store

    # ------------------------------------------------------------------
    def run(self, **kw) -> list[IIOSRecord]:
        c = self.ctx
        stats = {"entities": 0, "edges": 0, "events": 0}

        industry_eid = self.store.upsert_entity(
            c.industry, "org", industry=c.industry, summary="行业根节点")
        stats["entities"] += 1

        # 1. 产业链层级
        vc_file = c.industry_dir / "value_chain.json"
        tier_ids = {}
        if vc_file.exists():
            try:
                vc = json.loads(vc_file.read_text(encoding="utf-8"))
                tiers = vc.get("tiers", [])
                prev = None
                for t in tiers:
                    tname = t if isinstance(t, str) else t.get("name", "")
                    tid = self.store.upsert_entity(
                        tname, "technology", industry=c.industry, summary="产业链层级")
                    tier_ids[tname] = tid
                    self.store.upsert_edge(tid, industry_eid, "member_of", source="value_chain")
                    stats["edges"] += 1
                    if prev:
                        self.store.upsert_edge(prev, tid, "supplies", source="value_chain")
                        stats["edges"] += 1
                    prev = tid
                    stats["entities"] += 1
            except (json.JSONDecodeError, IOError):
                pass

        # 2. 公司（LLM 任务包执行后生成的 companies.json）
        companies = []
        comp_file = c.industry_dir / "companies" / "companies.json"
        if comp_file.exists():
            try:
                companies = json.loads(comp_file.read_text(encoding="utf-8"))
                self.store.save_companies(companies, industry=c.industry)
                for cpy in companies:
                    cid = self.store.upsert_entity(
                        cpy.get("name", ""), "company", industry=c.industry,
                        region=cpy.get("region", ""),
                        summary=cpy.get("overview", "")[:200])
                    stats["entities"] += 1
                    tier = cpy.get("tier", "")
                    if tier in tier_ids:
                        self.store.upsert_edge(cid, tier_ids[tier], "member_of",
                                               source="companies.json")
                        stats["edges"] += 1
                    for sup in cpy.get("suppliers", [])[:10]:
                        sid = self.store.upsert_entity(sup, "company", industry=c.industry)
                        self.store.upsert_edge(sid, cid, "supplies", source="deep_dive")
                        stats["edges"] += 1
                    for comp in cpy.get("competitors", [])[:10]:
                        pid = self.store.upsert_entity(comp, "company", industry=c.industry)
                        self.store.upsert_edge(cid, pid, "competes", source="deep_dive")
                        stats["edges"] += 1
            except (json.JSONDecodeError, IOError):
                pass

        # 3. 时间轴事件
        evt_file = c.industry_dir / "timeline" / "events.json"
        if evt_file.exists():
            try:
                events = json.loads(evt_file.read_text(encoding="utf-8"))
                stats["events"] = self.store.save_events(events)
            except (json.JSONDecodeError, IOError):
                pass

        # 4. 新闻共现：新版行业 JSON 中标题提及已知公司 → co_mentioned
        known = self._known_company_names()
        if known:
            from ..industry_store import IndustryStore
            folder = self.ctx.data_folder or self.ctx.industry_root.name
            daily_store = IndustryStore(self.ctx.data_root, folder, self.ctx.industry)
            rows = daily_store.list_daily_range(days=30)[:500]
            for row in rows:
                uid = row.get("content_hash") or row.get("url", "")
                title = row.get("title", "")
                if not title:
                    continue
                hits = [n for n in known if n and n.lower() in title.lower()]
                for i, a in enumerate(hits):
                    aid = self.store.upsert_entity(a, "company", industry=c.industry)
                    for b in hits[i + 1:]:
                        bid = self.store.upsert_entity(b, "company", industry=c.industry)
                        self.store.upsert_edge(aid, bid, "co_mentioned",
                                               weight=0.5, source=f"article:{uid}")
                        stats["edges"] += 1

        mmd_path = self.export_mermaid()
        return [IIOSRecord(
            type="report", title=f"{c.industry} 知识图谱构建",
            summary=f"实体 {stats['entities']}+ / 边 {stats['edges']}+ / 事件 {stats['events']}，"
                    f"Mermaid: {mmd_path}",
            source="agent:kg", industry=c.industry, confidence=0.9,
            extra={"stats": stats, "kg_totals": self.store.kg_stats()},
        )]

    # ------------------------------------------------------------------
    def _known_company_names(self) -> list[str]:
        con = sqlite3.connect(self.store.db_path)
        names = [r[0] for r in con.execute(
            "SELECT name FROM entities WHERE etype='company'").fetchall()]
        con.close()
        return names

    def export_mermaid(self, max_edges: int = 60) -> str:
        """导出核心子图为 Mermaid（industry/<industry>/knowledge_graph/graph.mmd）."""
        con = sqlite3.connect(self.store.db_path)
        con.row_factory = sqlite3.Row
        edges = con.execute("""
            SELECT e.relation, e.weight, s.name AS sname, d.name AS dname
            FROM edges e JOIN entities s ON e.src_id=s.id
                         JOIN entities d ON e.dst_id=d.id
            ORDER BY e.weight DESC LIMIT ?""", (max_edges,)).fetchall()
        con.close()

        def nid(name):
            stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", name)[:20] or "entity"
            suffix = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
            return f"N{stem}_{suffix}"

        lines, declared = ["graph LR"], set()
        rel_label = {"supplies": "供应", "competes": "竞争", "member_of": "属于",
                     "co_mentioned": "共现", "develops": "研发", "invests": "投资",
                     "uses": "使用", "regulates": "监管"}
        for e in edges:
            for n in (e["sname"], e["dname"]):
                k = nid(n)
                if k not in declared:
                    lines.append(f'    {k}["{n}"]')
                    declared.add(k)
            lines.append(f'    {nid(e["sname"])} -->|{rel_label.get(e["relation"], e["relation"])}| '
                         f'{nid(e["dname"])}')
        out_dir = self.ctx.industry_dir / "knowledge_graph"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "graph.mmd"
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)
