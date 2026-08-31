"""Transactional orchestration for the deterministic Intelligence Lab."""

from __future__ import annotations

from pathlib import Path

from intdog_core import IntDogService
from intdog_core.models import utc_now
from src.lab import (ALGORITHM_VERSION, LIMITATION, build_agenda_items,
                     build_chain_scenario, build_evidence_graph,
                     build_source_observatory, content_hash, mermaid_for_scenario,
                     safe_slug)
from src.lab.rendering import (agenda_markdown, evidence_markdown,
                               scenario_markdown, sources_markdown)
from src.lab.artifacts import write_bundle


class IntelligenceLab:
    SNAPSHOT_KEEP = 365

    def __init__(self, data_root: str | Path, folder: str):
        self.service = IntDogService(data_root)
        self.repo = self.service.repo
        self.folder = folder
        self.output = Path(data_root) / folder / "one_time" / "intelligence"
        self.repo.industry_id(folder)

    def _save(self, kind: str, payload: dict, relative: str, markdown: str, *,
              input_value, metrics: dict | None = None,
              extras: dict[str, str] | None = None) -> dict:
        payload.update({"generated_at": utc_now(), "algorithm_version": ALGORITHM_VERSION,
                        "limitation": LIMITATION})
        input_hash = content_hash(input_value)
        payload["input_hash"] = input_hash
        status = payload.get("status", "completed")
        snapshot = self.repo.save_analysis_artifact(
            self.folder, kind, payload, input_hash=input_hash,
            algorithm_version=ALGORITHM_VERSION, metrics=metrics or {}, status=status)
        payload.update({"artifact_id": snapshot["id"],
                        "snapshot_created": snapshot["created"]})
        if not snapshot["created"]:
            payload["generated_at"] = snapshot["created_at"]
        rendered_markdown = markdown.rstrip() + f"\n\n> 限制：{LIMITATION}\n"
        bundle = write_bundle(self.service, self.output, kind, snapshot["id"],
                              payload, rendered_markdown, extras)
        path = self.output / relative
        self.service.write_json(path, payload)
        md_path = path.with_suffix(".md")
        self.service.write_text(md_path, rendered_markdown)
        if snapshot["created"]:
            self.repo.prune_analysis_artifacts(self.folder, kind, self.SNAPSHOT_KEEP)
        return {**payload, "path": str(path), "markdown_path": str(md_path),
                "bundle_path": str(bundle)}

    def _compile_evidence(self) -> dict:
        raw_claims = self.repo.list_claim_evidence(self.folder)
        chains = self.repo.list_chain_nodes(self.folder)
        payload = build_evidence_graph(raw_claims, chains)
        return self._save("evidence_graph", payload, "evidence_graph.json",
                          evidence_markdown(payload),
                          input_value={"claims": raw_claims, "chains": chains},
                          metrics=payload["metrics"])

    def compile_evidence(self) -> dict:
        with self.service.run(self.folder, "compile-evidence", "compile") as run_id:
            result = self._compile_evidence()
            self.repo.update_run(run_id, metrics=result["metrics"])
            return result

    def _observe_sources(self, stale_days: int) -> dict:
        observations = self.repo.source_observations(self.folder)
        overlap = self.repo.source_overlap_stats(self.folder)
        inventory = self.repo.source_observatory_stats(self.folder)
        previous = self.repo.latest_analysis_artifact(self.folder, "source_observatory")
        previous_content = previous.get("content", {}) if previous else {}
        payload = build_source_observatory(
            observations, overlap, inventory, stale_days, previous=previous_content)
        payload["history"] = self.repo.list_analysis_artifacts(
            self.folder, "source_observatory", limit=30)
        return self._save("source_observatory", payload, "source_observatory.json",
                          sources_markdown(payload),
                          input_value={"sources": observations, "overlap": overlap,
                                       "inventory": inventory,
                                       "stale_days": stale_days}, metrics=payload["metrics"])

    def observe_sources(self, stale_days: int = 30) -> dict:
        with self.service.run(self.folder, "observe-sources", "observe") as run_id:
            result = self._observe_sources(max(1, stale_days))
            self.repo.update_run(run_id, metrics=result["metrics"])
            return result

    def _simulate_chain(self, event: str, chain: str, max_hops: int) -> dict:
        event = event.strip()
        if not event:
            raise ValueError("情景事件不能为空")
        nodes = self.repo.list_chain_nodes(self.folder)
        roles = self.repo.list_chain_roles(self.folder)
        all_edges = self.repo.list_chain_edges(self.folder)
        edges = [edge for edge in all_edges
                 if edge.get("evidence_count", 0) > 0 and
                 edge.get("status") in {"collected", "verified", "corroborated"}]
        payload = build_chain_scenario(event, chain, max_hops, nodes, roles, edges)
        payload["candidate_edges_excluded"] = len(all_edges) - len(edges)
        slug = safe_slug(event)
        mermaid = mermaid_for_scenario(
            nodes, edges, {item["node_id"] for item in payload["impacts"]
                           if item["distance"] == 0})
        result = self._save("chain_scenario", payload, f"scenarios/{slug}.json",
                            scenario_markdown(payload),
                            input_value={"event": event, "chain": chain,
                                         "max_hops": max_hops, "nodes": nodes,
                                         "roles": roles, "edges": edges,
                                         "candidate_edges_excluded":
                                             payload["candidate_edges_excluded"]},
                            metrics={"direct_nodes": len(payload["direct_nodes"]),
                                     "impacted_nodes": len(payload["impacts"]),
                                     "topology": payload["topology"]},
                            extras={"graph.mmd": mermaid})
        mmd_path = self.output / "scenarios" / f"{slug}.mmd"
        self.service.write_text(mmd_path, mermaid)
        result["mermaid_path"] = str(mmd_path)
        return result

    def simulate_chain(self, event: str, chain: str = "", max_hops: int = 3) -> dict:
        with self.service.run(self.folder, "simulate-chain", "propagate") as run_id:
            result = self._simulate_chain(event, chain, max(0, max_hops))
            terminal = "unresolved" if result["status"] == "unresolved" else None
            self.repo.update_run(run_id, status=terminal,
                                 metrics={"impacted_nodes": len(result["impacts"])})
            return result

    def _plan_boundaries(self, evidence: dict | None = None,
                         sources: dict | None = None) -> dict:
        evidence = evidence or self._compile_evidence()
        sources = sources or self._observe_sources(30)
        items = build_agenda_items(self.folder, evidence, sources)
        ids = self.repo.upsert_research_agenda(self.folder, items)
        resolved = self.repo.reconcile_research_agenda(self.folder, ids)
        active = self.repo.list_research_agenda(self.folder)
        # Persistence timestamps are operational metadata, not research input.
        # Including updated_at made an identical second plan look like a new
        # knowledge snapshot and defeated artifact deduplication.
        stable_active = [{key: value for key, value in item.items()
                          if key not in {"created_at", "updated_at"}}
                         for item in active]
        payload = {"kind": "research_agenda", "generated_items": len(items),
                   "resolved_candidates": resolved, "active_items": active}
        return self._save("research_agenda", payload, "research_agenda.json",
                          agenda_markdown(active),
                          input_value={"evidence": evidence.get("input_hash"),
                                       "sources": sources.get("input_hash"), "items": items,
                                       "active": stable_active},
                          metrics={"generated": len(ids), "active": len(active),
                                   "resolved_candidates": resolved})

    def plan_boundaries(self) -> dict:
        with self.service.run(self.folder, "plan-boundaries", "plan") as run_id:
            result = self._plan_boundaries()
            self.repo.update_run(run_id, metrics={"active": len(result["active_items"])})
            return result

    def run_all(self, *, event: str = "", chain: str = "", stale_days: int = 30,
                max_hops: int = 3) -> dict:
        with self.service.run(self.folder, "run-lab", "evidence") as run_id:
            evidence = self._compile_evidence()
            self.repo.update_run(run_id, stage="sources")
            sources = self._observe_sources(max(1, stale_days))
            result = {"evidence": evidence, "sources": sources}
            if event:
                self.repo.update_run(run_id, stage="scenario")
                result["scenario"] = self._simulate_chain(event, chain, max(0, max_hops))
            self.repo.update_run(run_id, stage="agenda")
            result["agenda"] = self._plan_boundaries(evidence=evidence, sources=sources)
            metrics = {"claims": evidence["metrics"]["claims"],
                       "source_links": sources["metrics"]["source_links"],
                       "agenda": len(result["agenda"]["active_items"])}
            if result.get("scenario", {}).get("status") == "unresolved":
                self.repo.update_run(run_id, status="partial", metrics=metrics)
                result["status"] = "partial"
            else:
                self.repo.update_run(run_id, metrics=metrics)
                result["status"] = "completed"
            return result
