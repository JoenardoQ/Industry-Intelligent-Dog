"""三层知识结构模型：行业 → 完整产业链 → 企业/机构/人物/技术等实体.

例：
  行业      芯片
  产业链    设计验证 / 制造 / 封装
  实体      设计验证-英伟达(企业) / 设计验证-港科广吕杨迪组(高校研究组)

存储于 DomainIntelData/<行业>/one_time/knowledge/：
  industry.json   行业本体
  chains.json     产业链层级列表
  entities.json   实体列表（归属某个产业链层级）

实体类型覆盖 company / research_group / regulator / association / person /
technology / product / facility。
"""

from __future__ import annotations

import json
from pathlib import Path

from intdog_core import IntDogService, stable_id

ENTITY_TYPES = ("company", "research_group", "regulator", "association",
                "person", "technology", "product", "facility")


class KnowledgeModel:
    """三层知识结构的读写（挂在某个 IndustryStore 的 knowledge/ 目录）."""

    def __init__(self, knowledge_dir: str | Path):
        self.dir = Path(knowledge_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.industry_path = self.dir / "industry.json"
        self.chains_path = self.dir / "chains.json"
        self.entities_path = self.dir / "entities.json"
        self.folder = self.dir.parents[1].name
        self.service = IntDogService(self.dir.parents[2])

    # ------------------------------------------------------------------
    # 行业（第一层）
    # ------------------------------------------------------------------
    def set_industry(self, name: str, name_en: str = "", description: str = "",
                     references: list = None) -> dict:
        ind = {
            "id": self.service.repo.ensure_industry(self.folder, name),
            "name": name,
            "name_en": name_en,
            "description": description,
            "references": references or [],
        }
        self._write(self.industry_path, ind)
        return ind

    def get_industry(self) -> dict:
        return self._read(self.industry_path, {})

    # ------------------------------------------------------------------
    # 产业链层级（第二层）
    # ------------------------------------------------------------------
    def add_chain(self, name: str, description: str = "", order: int = 0,
                  references: list = None, **extra) -> dict:
        chains = self.get_chains()
        for c in chains:
            if c.get("name") == name:
                return c
        chain = {
            "name": name, "description": description,
            "order": order, "references": references or [],
        }
        chain.update({key: value for key, value in extra.items() if key not in chain})
        chain["id"] = self.service.repo.upsert_chain_node(self.folder, chain)
        activity_id = self.service.repo.upsert_entity(self.folder, {
            "name": name, "type": "supply_chain_activity",
            "description": description, "references": references or [],
            "status": "candidate", **extra})
        chain["activity_entity_id"] = activity_id
        chains.append(chain)
        chains.sort(key=lambda c: c.get("order", 0))
        self._write(self.chains_path, chains)
        self.service.repo.mark_compat_clean(self.folder, "chains")
        return chain

    def get_chains(self) -> list[dict]:
        rows = self.service.repo.list_chain_nodes(self.folder)
        return rows if rows else self._read(self.chains_path, [])

    def add_chain_edge(self, src_name: str, dst_name: str, relation: str = "supplies",
                       **metadata) -> str:
        chains = {item["name"]: item for item in self.get_chains()}
        if src_name not in chains or dst_name not in chains:
            raise ValueError("产业链边引用了未知节点")
        references = metadata.pop("references", []) or []
        edge_id = self.service.repo.upsert_chain_edge(self.folder, {
            "src_node_id": chains[src_name]["id"], "dst_node_id": chains[dst_name]["id"],
            "relation": relation, **metadata})
        for reference in references:
            if isinstance(reference, str):
                reference = {"url": reference}
            if isinstance(reference, dict) and reference.get("url"):
                self.service.repo.add_chain_edge_evidence(
                    edge_id, reference.get("relation", "supports"), url=reference["url"],
                    excerpt=reference.get("title", ""),
                    publisher_cluster=reference.get("publisher_cluster", ""),
                    confidence=reference.get("confidence"))
        return edge_id

    # ------------------------------------------------------------------
    # 实体（第三层）
    # ------------------------------------------------------------------
    def add_entity(self, name: str, etype: str, chain: str, name_en: str = "",
                   country: str = "", description: str = "",
                   url: str = "", references: list = None, **extra) -> dict:
        """新增实体。chain 为产业链层级名（自动按名建档）."""
        if etype not in ENTITY_TYPES:
            etype = "company"
        entities = self.get_entities()
        eid = stable_id("ent", etype, name, country)
        for e in entities:
            if e["id"] == eid and e.get("chain") == chain:
                return e
        ent = {
            "id": eid, "name": name, "name_en": name_en, "type": etype,
            "chain": chain, "country": country, "description": description,
            "url": url, "references": references or [],
        }
        ent.update({key: value for key, value in extra.items() if key not in ent})
        entities.append(ent)
        canonical_entity_id = self.service.repo.upsert_entity(self.folder, ent, chain)
        # 确保所属 chain 存在
        chain_entity = self.add_chain(chain)
        activity_id = chain_entity.get("activity_entity_id") or self.service.repo.upsert_entity(
            self.folder, {"name": chain, "type": "supply_chain_activity",
                          "status": "candidate"})
        self.service.repo.upsert_relation(
            self.folder, canonical_entity_id, "participates_in",
            activity_id,
            confidence=extra.get("confidence"),
            metadata={"references": references or [], "role": etype})
        self._write(self.entities_path, entities)
        self.service.repo.mark_compat_clean(self.folder, "entities")
        return ent

    def get_entities(self, chain: str = None, etype: str = None) -> list[dict]:
        ents = self._read(self.entities_path, [])
        if chain:
            ents = [e for e in ents if e.get("chain") == chain]
        if etype:
            ents = [e for e in ents if e.get("type") == etype]
        return ents

    def delete_entity(self, entity_id: str) -> bool:
        return self.service.delete_entity(self.folder, entity_id)

    def reset_generated(self) -> None:
        """Clear generated chains/entities before an authoritative bootstrap replace."""
        self.service.repo.clear_industry_entities(self.folder)
        self.service.repo.clear_chain_nodes(self.folder)
        self._write(self.chains_path, [])
        self._write(self.entities_path, [])
        self.service.repo.mark_compat_clean(self.folder, "entities")
        self.service.repo.mark_compat_clean(self.folder, "chains")

    # ------------------------------------------------------------------
    # 汇总视图（三层树）
    # ------------------------------------------------------------------
    def tree(self) -> dict:
        """返回 {industry, chains:[{...,entities:[...]}]} 三层树."""
        ind = self.get_industry()
        chains = self.get_chains()
        ents = self.get_entities()
        for c in chains:
            c["entities"] = [e for e in ents if e.get("chain") == c["name"]]
        return {"industry": ind, "chains": chains}

    # ------------------------------------------------------------------
    @staticmethod
    def _read(path: Path, default):
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        return default

    @staticmethod
    def _write(path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(path)
