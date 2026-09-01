"""Structured value-chain persistence mixed into the main repository."""

from __future__ import annotations

from .models import json_text, json_value, stable_id, utc_now


class ChainRepositoryMixin:
    EDGE_RELATIONS = {"supplies", "depends_on", "enables", "substitutes",
                      "competes_capacity"}

    def list_entity_coverage_records(self, folder: str) -> list[dict]:
        """Return normalized role observations used by the coverage matrix."""
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT e.id AS entity_id,e.kind AS entity_type,
                e.canonical_name,e.country,e.metadata_json AS entity_metadata_json,
                r.role,r.status,r.confidence,r.evidence_count,r.valid_from,r.valid_to,
                r.metadata_json AS role_metadata_json,n.name AS chain_stage
                FROM entity_chain_roles r JOIN entities e ON e.id=r.entity_id
                JOIN value_chain_nodes n ON n.id=r.chain_node_id
                WHERE r.industry_id=? AND r.valid_to IS NULL""", (iid,)).fetchall()
        records = []
        for row in rows:
            entity_metadata = json_value(row["entity_metadata_json"], {})
            role_metadata = json_value(row["role_metadata_json"], {})
            records.append({
                "entity_id": row["entity_id"], "entity_type": row["entity_type"],
                "canonical_name": row["canonical_name"], "country": row["country"] or "",
                "region": role_metadata.get("region") or entity_metadata.get("region") or "",
                "chain_stage": row["chain_stage"], "role": row["role"],
                "status": row["status"], "confidence": row["confidence"],
                "evidence_count": int(row["evidence_count"] or 0),
                "valid_from": row["valid_from"], "valid_to": row["valid_to"],
            })
        return records

    def upsert_chain_node(self, folder: str, item: dict) -> str:
        iid = self.industry_id(folder)
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError("产业链节点名不能为空")
        node_id = stable_id("chn", iid, name)
        now = utc_now()
        with self.transaction() as con:
            con.execute("""INSERT INTO value_chain_nodes
                (id,industry_id,parent_id,name,position,description,status,coverage_status,
                 evidence_count,metadata_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(industry_id,name) DO UPDATE SET
                parent_id=excluded.parent_id,position=excluded.position,
                description=excluded.description,status=excluded.status,
                coverage_status=excluded.coverage_status,evidence_count=excluded.evidence_count,
                metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
                (node_id, iid, item.get("parent_id"), name,
                 int(item.get("order", item.get("position", 0)) or 0),
                 item.get("description", ""), item.get("status", "candidate"),
                 item.get("coverage_status", "empty"), int(item.get("evidence_count", 0) or 0),
                 json_text(item), now, now))
            self._mark_compat_dirty(con, iid, "chains")
        return node_id

    def list_chain_nodes(self, folder: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT n.*,
                COUNT(DISTINCT r.entity_id) AS entity_count,
                COALESCE(SUM(CASE WHEN r.evidence_count>0 THEN 1 ELSE 0 END),0) AS evidenced_entities
                FROM value_chain_nodes n LEFT JOIN entity_chain_roles r
                ON r.chain_node_id=n.id AND r.valid_to IS NULL
                WHERE n.industry_id=? GROUP BY n.id ORDER BY n.position,n.name""", (iid,)).fetchall()
        out = []
        for row in rows:
            item = json_value(row["metadata_json"], {})
            entity_count = int(row["entity_count"] or 0)
            evidenced = int(row["evidenced_entities"] or 0)
            coverage = ("empty" if entity_count == 0 else "thin" if evidenced == 0 else
                        "covered" if evidenced == entity_count else "partial")
            item.update({"id": row["id"], "name": row["name"],
                         "description": row["description"] or "", "order": row["position"],
                         "status": row["status"], "coverage_status": coverage,
                         "evidence_count": row["evidence_count"],
                         "entity_count": entity_count, "evidenced_entities": evidenced})
            out.append(item)
        return out

    def clear_chain_nodes(self, folder: str) -> int:
        iid = self.industry_id(folder)
        with self.transaction() as con:
            cur = con.execute("DELETE FROM value_chain_nodes WHERE industry_id=?", (iid,))
            self._mark_compat_dirty(con, iid, "chains")
        return cur.rowcount

    def upsert_chain_edge(self, folder: str, item: dict) -> str:
        iid = self.industry_id(folder)
        relation = str(item.get("relation") or "").strip()
        if relation not in self.EDGE_RELATIONS:
            raise ValueError(f"未知产业链关系：{relation}")
        src_id = str(item.get("src_node_id") or "")
        dst_id = str(item.get("dst_node_id") or "")
        if not src_id or not dst_id or src_id == dst_id:
            raise ValueError("产业链边必须连接两个不同节点")
        valid_from = str(item.get("valid_from") or "")
        edge_id = stable_id("ced", iid, src_id, relation, dst_id, valid_from)
        confidence = item.get("confidence")
        if confidence is not None and not 0 <= float(confidence) <= 1:
            raise ValueError("产业链边 confidence 必须在 0 到 1")
        now = utc_now()
        requested_status = str(item.get("status") or "candidate")
        status = requested_status if requested_status in {"candidate", "rejected"} \
            else "candidate"
        with self.transaction() as con:
            known = con.execute("""SELECT COUNT(*) FROM value_chain_nodes
                WHERE industry_id=? AND id IN (?,?)""", (iid, src_id, dst_id)).fetchone()[0]
            if known != 2:
                raise ValueError("产业链边节点不存在或不属于该行业")
            con.execute("""INSERT INTO value_chain_edges
                (id,industry_id,src_node_id,dst_node_id,relation,valid_from,valid_to,
                 confidence,evidence_count,metadata_json,created_at,updated_at,status,effect,lag_days)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET valid_to=excluded.valid_to,
                confidence=excluded.confidence,metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at,status=CASE
                    WHEN value_chain_edges.status IN ('collected','accepted')
                    THEN value_chain_edges.status ELSE excluded.status END,
                effect=excluded.effect,lag_days=excluded.lag_days""",
                (edge_id, iid, src_id, dst_id, relation, valid_from or None,
                 item.get("valid_to") or None, confidence,
                 0, json_text({**item, "requested_status": requested_status}),
                 now, now, status,
                 item.get("effect", "uncertain"), item.get("lag_days")))
        return edge_id

    def add_chain_edge_evidence(self, edge_id: str, relation: str, *,
                                document_id: str | None = None,
                                claim_id: str | None = None, url: str = "",
                                assertion_id: str | None = None,
                                excerpt: str = "", publisher_cluster: str = "",
                                confidence: float | None = None) -> str:
        if relation not in {"supports", "contradicts", "qualifies"}:
            raise ValueError("边证据关系必须是 supports/contradicts/qualifies")
        if not document_id and not claim_id and not assertion_id:
            raise ValueError("chain relationship evidence requires a Document or Assertion")
        with self.transaction() as con:
            edge = con.execute("SELECT industry_id FROM value_chain_edges WHERE id=?",
                               (edge_id,)).fetchone()
            if not edge:
                raise ValueError("产业链边不存在")
            industry_id = edge["industry_id"]
            if assertion_id:
                assertion = con.execute("""SELECT a.claim_id,a.status,c.status AS claim_status
                    FROM agent_assertions a
                    JOIN agent_results r ON r.id=a.result_id
                    LEFT JOIN claims c ON c.id=a.claim_id
                    WHERE a.id=? AND r.industry_id=? AND c.industry_id=?""",
                    (assertion_id, industry_id, industry_id)).fetchone()
                if (not assertion or assertion["status"] != "accepted"
                        or assertion["claim_status"] != "accepted"
                        or not assertion["claim_id"]):
                    raise ValueError("Assertion must be accepted before supporting a relationship")
                if claim_id and claim_id != assertion["claim_id"]:
                    raise ValueError("Assertion and Claim evidence identifiers conflict")
                claim_id = assertion["claim_id"]
            if document_id and con.execute("""SELECT 1 FROM industry_documents
                    WHERE industry_id=? AND document_id=? AND deleted_at IS NULL""",
                    (industry_id, document_id)).fetchone() is None:
                raise ValueError("relationship evidence Document is not in the current industry")
            if claim_id and con.execute("""SELECT 1 FROM claims
                    WHERE id=? AND industry_id=? AND status='accepted'""",
                    (claim_id, industry_id)).fetchone() is None:
                raise ValueError("relationship evidence Claim must be accepted in the current industry")
            evidence_id = stable_id(
                "cev", edge_id, document_id, claim_id, assertion_id, url, relation)
            con.execute("""INSERT INTO chain_edge_evidence
                (id,edge_id,document_id,claim_id,relation,url,excerpt,publisher_cluster,
                 confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET excerpt=excluded.excerpt,
                publisher_cluster=excluded.publisher_cluster,confidence=excluded.confidence""",
                (evidence_id, edge_id, document_id, claim_id, relation, url.strip() or None,
                 excerpt, publisher_cluster, confidence, utc_now()))
            supporting = con.execute("""SELECT COUNT(*) FROM chain_edge_evidence
                WHERE edge_id=? AND relation IN ('supports','qualifies')""", (edge_id,)).fetchone()[0]
            con.execute("""UPDATE value_chain_edges SET evidence_count=?,
                status=CASE WHEN status='accepted' THEN status
                    WHEN ?>0 THEN 'collected' ELSE status END,updated_at=? WHERE id=?""",
                (supporting, supporting, utc_now(), edge_id))
        return evidence_id

    def list_chain_edge_evidence(self, edge_id: str) -> list[dict]:
        with self.connection() as con:
            rows = con.execute("""SELECT v.*,d.title AS document_title,
                d.canonical_url AS document_url FROM chain_edge_evidence v
                LEFT JOIN documents d ON d.id=v.document_id
                WHERE v.edge_id=? ORDER BY v.created_at,v.id""", (edge_id,)).fetchall()
        return [dict(row) for row in rows]

    def list_chain_edges(self, folder: str, *, active_only: bool = True) -> list[dict]:
        iid = self.industry_id(folder)
        sql = """SELECT e.*,s.name AS src_name,d.name AS dst_name,
            (SELECT COUNT(*) FROM chain_edge_evidence v WHERE v.edge_id=e.id
             AND v.relation IN ('supports','qualifies')) AS linked_evidence_count
            FROM value_chain_edges e JOIN value_chain_nodes s ON s.id=e.src_node_id
            JOIN value_chain_nodes d ON d.id=e.dst_node_id WHERE e.industry_id=?"""
        if active_only:
            sql += " AND e.valid_to IS NULL"
        sql += " ORDER BY s.position,d.position,e.relation"
        with self.connection() as con:
            rows = con.execute(sql, (iid,)).fetchall()
            evidence_rows = con.execute("""SELECT v.*,d.title AS document_title,
                d.canonical_url AS document_url FROM chain_edge_evidence v
                JOIN value_chain_edges e ON e.id=v.edge_id
                LEFT JOIN documents d ON d.id=v.document_id
                WHERE e.industry_id=? ORDER BY v.created_at,v.id""", (iid,)).fetchall()
        evidence_by_edge: dict[str, list[dict]] = {}
        for evidence in evidence_rows:
            evidence_by_edge.setdefault(evidence["edge_id"], []).append(dict(evidence))
        out = []
        for row in rows:
            item = json_value(row["metadata_json"], {})
            item.update({key: row[key] for key in
                         ("id", "src_node_id", "dst_node_id", "src_name", "dst_name",
                          "relation", "valid_from", "valid_to", "confidence", "status",
                          "effect", "lag_days")})
            item["evidence_count"] = int(row["linked_evidence_count"] or 0)
            item["evidence"] = evidence_by_edge.get(row["id"], [])
            out.append(item)
        return out
