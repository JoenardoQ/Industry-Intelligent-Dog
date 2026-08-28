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

import hashlib
import json
from pathlib import Path

ENTITY_TYPES = ("company", "research_group", "regulator", "association",
                "person", "technology", "product", "facility")


def _id(*parts: str) -> str:
    raw = "|".join(p.lower() for p in parts if p)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


class KnowledgeModel:
    """三层知识结构的读写（挂在某个 IndustryStore 的 knowledge/ 目录）."""

    def __init__(self, knowledge_dir: str | Path):
        self.dir = Path(knowledge_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.industry_path = self.dir / "industry.json"
        self.chains_path = self.dir / "chains.json"
        self.entities_path = self.dir / "entities.json"

    # ------------------------------------------------------------------
    # 行业（第一层）
    # ------------------------------------------------------------------
    def set_industry(self, name: str, name_en: str = "", description: str = "",
                     references: list = None) -> dict:
        ind = {
            "id": _id("industry", name),
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
        cid = _id("chain", name)
        for c in chains:
            if c["id"] == cid:
                return c
        chain = {
            "id": cid, "name": name, "description": description,
            "order": order, "references": references or [],
        }
        chain.update({key: value for key, value in extra.items() if key not in chain})
        chains.append(chain)
        chains.sort(key=lambda c: c.get("order", 0))
        self._write(self.chains_path, chains)
        return chain

    def get_chains(self) -> list[dict]:
        return self._read(self.chains_path, [])

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
        eid = _id("entity", chain, name)
        for e in entities:
            if e["id"] == eid:
                return e
        ent = {
            "id": eid, "name": name, "name_en": name_en, "type": etype,
            "chain": chain, "country": country, "description": description,
            "url": url, "references": references or [],
        }
        ent.update({key: value for key, value in extra.items() if key not in ent})
        entities.append(ent)
        self._write(self.entities_path, entities)
        # 确保所属 chain 存在
        self.add_chain(chain)
        return ent

    def get_entities(self, chain: str = None, etype: str = None) -> list[dict]:
        ents = self._read(self.entities_path, [])
        if chain:
            ents = [e for e in ents if e.get("chain") == chain]
        if etype:
            ents = [e for e in ents if e.get("type") == etype]
        return ents

    def delete_entity(self, entity_id: str) -> bool:
        ents = self.get_entities()
        new = [e for e in ents if e.get("id") != entity_id]
        if len(new) == len(ents):
            return False
        self._write(self.entities_path, new)
        return True

    def reset_generated(self) -> None:
        """Clear generated chains/entities before an authoritative bootstrap replace."""
        self._write(self.chains_path, [])
        self._write(self.entities_path, [])

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
