"""Knowledge graph agent backed by the shared IntDog repository."""

from __future__ import annotations

import hashlib
import json
import re

from intdog_core import IntDogService

from .base import BaseAgent
from ..schema import IIOSRecord


class KnowledgeGraphAgent(BaseAgent):
    name = "kg"
    agent_type = "code"
    description = "构建时态知识图谱：实体、产业链关系、事件和共现"

    def __init__(self, ctx, service: IntDogService | None = None):
        super().__init__(ctx)
        self.folder = ctx.data_folder or ctx.industry_root.name
        self.service = service or IntDogService(ctx.data_root)
        self.repo = self.service.repo
        self.repo.ensure_industry(self.folder, ctx.industry)

    @staticmethod
    def _read(path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
        except (OSError, json.JSONDecodeError):
            return default

    def _entity(self, name: str, kind: str, **metadata) -> str:
        return self.repo.upsert_entity(self.folder, {
            "name": name, "type": kind, **metadata})

    def _relation(self, src: str, predicate: str, dst: str, **metadata) -> str:
        return self.repo.upsert_relation(
            self.folder, src, predicate, dst,
            confidence=metadata.pop("confidence", None), metadata=metadata)

    def run(self, **kw) -> list[IIOSRecord]:
        stats = {"entities": 0, "relations": 0, "events": 0}
        industry_id = self._entity(self.ctx.industry, "industry", status="verified")
        stats["entities"] += 1

        tier_ids = self._load_value_chain(industry_id, stats)
        company_names = self._load_companies(tier_ids, stats)
        self._load_events(stats)
        self._load_co_mentions(company_names, stats)

        path = self.export_mermaid()
        totals = self.repo.knowledge_stats(self.folder)
        return [IIOSRecord(
            type="report", title=f"{self.ctx.industry} 知识图谱构建",
            summary=(f"实体 {totals['entities']} / 关系 {totals['relations']} / "
                     f"事件 {totals['events']}；Mermaid: {path}"),
            source="agent:kg", industry=self.ctx.industry, confidence=0.9,
            extra={"run_stats": stats, "knowledge_totals": totals},
        )]

    def _load_value_chain(self, industry_id: str, stats: dict) -> dict[str, str]:
        data = self._read(self.ctx.industry_dir / "value_chain.json", {})
        tiers = data.get("tiers", []) if isinstance(data, dict) else []
        ids, previous = {}, None
        for item in tiers:
            name = item if isinstance(item, str) else item.get("name", "")
            if not name:
                continue
            tier_id = self._entity(name, "supply_chain_activity", status="candidate")
            ids[name] = tier_id
            self._relation(tier_id, "part_of", industry_id, source="value_chain.json")
            stats["entities"] += 1; stats["relations"] += 1
            if previous:
                self._relation(previous, "supplies", tier_id, source="value_chain.json")
                stats["relations"] += 1
            previous = tier_id
        return ids

    def _load_companies(self, tiers: dict[str, str], stats: dict) -> list[str]:
        companies = self._read(self.ctx.industry_dir / "companies/companies.json", [])
        names = []
        for company in companies if isinstance(companies, list) else []:
            name = str(company.get("name") or "").strip()
            if not name:
                continue
            cid = self._entity(name, "company", name_en=company.get("name_en", ""),
                               country=company.get("region", ""), metrics=company)
            names.append(name); stats["entities"] += 1
            tier = company.get("tier", "")
            if tier in tiers:
                self._relation(cid, "participates_in", tiers[tier], source="companies.json")
                stats["relations"] += 1
            for supplier in company.get("suppliers", [])[:10]:
                sid = self._entity(str(supplier), "company")
                self._relation(sid, "supplies", cid, source="companies.json")
                stats["relations"] += 1
            for competitor in company.get("competitors", [])[:10]:
                other = self._entity(str(competitor), "company")
                self._relation(cid, "competes_with", other, source="companies.json")
                stats["relations"] += 1
        return names

    def _load_events(self, stats: dict) -> None:
        events = self._read(self.ctx.industry_dir / "timeline/events.json", [])
        for event in events if isinstance(events, list) else []:
            try:
                self.repo.upsert_event(self.folder, event); stats["events"] += 1
            except ValueError:
                continue

    def _load_co_mentions(self, known: list[str], stats: dict) -> None:
        if not known:
            known = self._known_company_names()
        if not known:
            return
        from ..industry_store import IndustryStore
        rows = IndustryStore(self.ctx.data_root, self.folder, self.ctx.industry).list_daily_range(30)
        for row in rows[:500]:
            title = str(row.get("title") or "")
            hits = [name for name in known if name and name.casefold() in title.casefold()]
            for index, first in enumerate(hits):
                src = self._entity(first, "company")
                for second in hits[index + 1:]:
                    dst = self._entity(second, "company")
                    self._relation(src, "co_mentioned_with", dst,
                                   source_document=row.get("id") or row.get("url", ""))
                    stats["relations"] += 1

    def _known_company_names(self) -> list[str]:
        iid = self.repo.industry_id(self.folder)
        with self.repo.connection() as con:
            rows = con.execute("""SELECT DISTINCT e.canonical_name FROM industry_entities x
                JOIN entities e ON e.id=x.entity_id
                WHERE x.industry_id=? AND e.kind='company' AND x.status!='deleted'""",
                (iid,)).fetchall()
        return [row[0] for row in rows]

    def export_mermaid(self, max_edges: int = 80) -> str:
        graph = self.repo.graph(self.folder, limit=max_edges)

        def node_id(name: str) -> str:
            stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", name)[:20] or "entity"
            return f"N{stem}_{hashlib.sha1(name.encode('utf-8')).hexdigest()[:6]}"

        labels = {"supplies": "供应", "competes_with": "竞争", "part_of": "属于",
                  "participates_in": "参与", "co_mentioned_with": "共现"}
        lines, declared = ["graph LR"], set()
        for edge in graph["edges"]:
            for name in (edge["src_name"], edge["dst_name"]):
                nid = node_id(name)
                if nid not in declared:
                    lines.append(f'    {nid}["{name}"]'); declared.add(nid)
            relation = labels.get(edge["predicate"], edge["predicate"])
            lines.append(f'    {node_id(edge["src_name"])} -->|{relation}| '
                         f'{node_id(edge["dst_name"])}')
        out = self.ctx.industry_dir / "knowledge_graph/graph.mmd"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        return str(out)
