"""Review-gated task-package exchange for arbitrary local agents."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Callable

from fastapi import APIRouter, HTTPException, Query
from src.agent_evidence import AssertionVerifier, probe_agent_evidence
from src.services.agent_registry import diagnose_agent, discover_local_agents
from src.services.capability_manifest import CAPABILITY_MANIFEST

from ..schemas import (
    AgentProfileDeleteState,
    AgentProfilePage,
    AgentProbeState,
    AgentCapabilityPage,
    AgentDiagnosticState,
    AgentDiscoveryPage,
    AgentDiscoveryRequest,
    AgentResultImport,
    AgentResultPage,
    AgentResultState,
    AgentReviewRequest,
    AgentTaskExport,
    AgentTaskPage,
    AgentVerificationState,
    CustomAgentProfile,
)

MAX_RESULT_BYTES = 512_000
MAX_PROFILE_BYTES = 256 * 1024
MAX_VERIFY_RESPONSE_BYTES = 256 * 1024
MAX_PROFILES = 100
COMMAND = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
ARG = re.compile(r"^[A-Za-z0-9._:=@+{},-]{1,160}$")
RESULT_ID = re.compile(r"^agr_[0-9a-f]{24}$")
LEGACY_RESULT_ID = re.compile(r"^[0-9a-f]{64}$")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8")


def _verification_state_bytes(value: dict) -> int:
    state = AgentVerificationState.model_validate(value)
    return len(state.model_dump_json().encode("utf-8"))


def _bounded_verification_state(value: dict) -> dict:
    original_bytes = _verification_state_bytes(value)
    if original_bytes <= MAX_VERIFY_RESPONSE_BYTES:
        return AgentVerificationState.model_validate(value).model_dump(mode="json")
    decisions = []
    for decision in value["decisions"]:
        summarized_checks = {}
        for name, check in decision["checks"].items():
            summary = {
                "status": check.get("status", "failed"),
                "reason": str(check.get("reason") or "aggregate detail omitted")[:256],
                "evidence_ids": [],
                "locators": [],
            }
            if name == "semantic_support":
                summary["decision"] = check.get("decision", "unknown")
                summary["retryable"] = bool(check.get("retryable", False))
            if name == "resource_budget":
                for field_name in (
                        "citation_count", "fetched_bytes", "excerpt_bytes",
                        "approximate_provider_tokens", "limits", "budget_truncation"):
                    if field_name in check:
                        summary[field_name] = check[field_name]
            summarized_checks[name] = summary
        decisions.append({
            "assertion_id": decision["assertion_id"],
            "disposition": decision["disposition"],
            "claim_id": decision.get("claim_id"),
            "checks": summarized_checks,
        })
    bounded = {**value, "decisions": decisions,
               "response_truncation": {
                   "original_bytes": original_bytes, "final_bytes": 0,
                   "decision_count": len(decisions)}}
    for _ in range(3):
        bounded["response_truncation"]["final_bytes"] = \
            _verification_state_bytes(bounded)
    if _verification_state_bytes(bounded) > MAX_VERIFY_RESPONSE_BYTES:
        raise HTTPException(500, "Bounded verification response could not be serialized")
    return AgentVerificationState.model_validate(bounded).model_dump(mode="json")


def _read_json_bounded(path: Path, max_bytes: int, oversized_detail: str):
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(413, oversized_detail)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON") from exc


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        try:
            Path(name).unlink(missing_ok=True)
        except OSError:
            pass


def _validate_profile(profile: CustomAgentProfile) -> dict:
    if not COMMAND.fullmatch(profile.command):
        raise HTTPException(422, "命令必须是 PATH 中的命令名，不能包含路径或 shell 语法")
    if any(not ARG.fullmatch(arg) for arg in profile.args):
        raise HTTPException(422, "参数只能包含公开 argv 字符和 {task_file}/{result_file} 占位符")
    if profile.executable_path is not None:
        selected = Path(profile.executable_path)
        if ("\x00" in profile.executable_path or not selected.is_absolute()
                or not selected.is_file()):
            raise HTTPException(422, "用户选择的可执行文件必须是现有绝对路径")
    return profile.model_dump()


def _read_profiles(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        if path.stat().st_size > MAX_PROFILE_BYTES:
            raise HTTPException(413, "Agent Profile 文件超过 256 KiB 上限")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list) or len(value) > MAX_PROFILES:
            raise ValueError("invalid Agent Profile collection")
        return [CustomAgentProfile.model_validate(item).model_dump() for item in value]
    except HTTPException:
        raise
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(409, "Agent Profile 文件损坏") from exc


def build_agent_bridge_router(*, data_root: Path, dataio,
                              resolve_folder: Callable[[str], str], service,
                              verifier: AssertionVerifier | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["agent-bridge"])
    profiles_path = data_root / "_settings" / "agent_profiles.json"
    profiles_lock = threading.RLock()
    result_import_lock = threading.RLock()
    assertion_verifier = verifier or AssertionVerifier(fetch=probe_agent_evidence)

    @router.get("/agent-bridge/capabilities", response_model=AgentCapabilityPage)
    def capabilities() -> dict:
        items = []
        for spec in CAPABILITY_MANIFEST:
            public = spec.public()
            items.append({key: public[key] for key in (
                "id", "name", "kind", "region", "connection", "execution_level",
                "auth", "web_access", "structured_output", "schedulable",
                "docs_url", "note", "commands",
            )})
        return {"items": items, "total": len(items)}

    @router.post("/agent-bridge/discover", response_model=AgentDiscoveryPage)
    def discover(payload: AgentDiscoveryRequest) -> dict:
        rows = discover_local_agents(
            path=payload.path or os.environ.get("PATH", ""),
            selected_executables=payload.selected_executables,
        )
        items = []
        for row in rows:
            items.append({key: row[key] for key in (
                "id", "name", "kind", "region", "connection", "execution_level",
                "auth", "web_access", "structured_output", "schedulable",
                "docs_url", "note", "commands", "installed", "authenticated",
                "version_verified", "ready", "executable", "status", "failure_code",
                "version", "detail",
            )})
        return {"items": items, "total": len(items)}

    def _store_and_index_result(folder: str, record: dict, target: Path) -> tuple[dict, bool]:
        duplicate = target.exists()
        if not duplicate:
            _atomic_json(target, record)
        else:
            try:
                record = _read_json_bounded(
                    target, MAX_RESULT_BYTES, "已有 Agent 结果超过 500 KiB 上限")
                if not isinstance(record, dict):
                    raise ValueError("Agent result must be an object")
            except HTTPException:
                raise
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(409, "已有 Agent 结果文件损坏") from exc
        try:
            return service.repo.index_agent_result(folder, record, str(target)), duplicate
        except Exception as exc:
            if not duplicate:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            if isinstance(exc, ValueError):
                raise HTTPException(409, str(exc)) from exc
            raise

    def _repository_result_for_path(folder: str, path: Path) -> dict | None:
        offset = 0
        while True:
            page = service.repo.list_agent_results(folder, limit=100, offset=offset)
            for item in page["items"]:
                if str(item["original_file"]) == str(path):
                    return item
            if page["next_offset"] is None:
                return None
            offset = page["next_offset"]

    def _index_result_path(folder: str, path: Path) -> dict:
        try:
            resolved = path.resolve(strict=True)
            try:
                resolved.relative_to((data_root / folder).resolve())
            except ValueError as exc:
                raise ValueError("Agent result artifact escaped the managed industry") from exc
            current = _repository_result_for_path(folder, resolved)
            if current is not None:
                return current
            record = _read_json_bounded(
                resolved, MAX_RESULT_BYTES, "Agent 结果超过 500 KiB 上限")
            if not isinstance(record, dict):
                raise ValueError("Agent result must be an object")
            known_tasks = {str(item.get("id")) for item in
                           dataio.list_research_tasks(data_root, folder)}
            if str(record.get("task_id") or "") not in known_tasks:
                raise ValueError("unknown Agent task")
            return service.repo.index_agent_result(folder, record, str(resolved))
        except HTTPException:
            raise
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(409, "Agent 结果文件损坏") from exc

    def _repository_result(folder: str, result_id: str) -> dict:
        if RESULT_ID.fullmatch(result_id):
            try:
                return service.repo.get_agent_result(folder, result_id)
            except FileNotFoundError as exc:
                raise HTTPException(404, "Agent 结果不存在") from exc
        if not LEGACY_RESULT_ID.fullmatch(result_id):
            raise HTTPException(422, "结果 ID 无效")
        base = data_root / folder / "one_time" / "agent_results"
        matches = list(base.glob(f"*/{result_id}.json")) if base.is_dir() else []
        if not matches:
            raise HTTPException(404, "Agent 结果不存在")
        if len(matches) != 1:
            raise HTTPException(409, "Agent 结果 ID 对应多个原始文件")
        return _index_result_path(folder, matches[0])

    def _index_legacy_results(folder: str) -> None:
        known_paths: set[str] = set()
        offset = 0
        while True:
            page = service.repo.list_agent_results(folder, limit=100, offset=offset)
            known_paths.update(str(item["original_file"]) for item in page["items"])
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        base = data_root / folder / "one_time" / "agent_results"
        paths = sorted(base.glob("*/*.json")) if base.is_dir() else []
        for path in paths:
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise HTTPException(409, "Agent 结果文件损坏") from exc
            if str(resolved) in known_paths:
                continue
            _index_result_path(folder, resolved)

    @router.get("/agent-bridge/profiles", response_model=AgentProfilePage)
    def profiles() -> dict:
        with profiles_lock:
            rows = _read_profiles(profiles_path)
            return {"items": rows, "total": len(rows), "limit": MAX_PROFILES}

    @router.post("/agent-bridge/profiles", status_code=201,
                 response_model=CustomAgentProfile)
    def save_profile(payload: CustomAgentProfile) -> dict:
        row = _validate_profile(payload)
        with profiles_lock:
            current = profiles()["items"]
            is_new = not any(item.get("id") == row["id"] for item in current)
            if is_new and len(current) >= MAX_PROFILES:
                raise HTTPException(409, "Agent Profile 数量达到 100 个上限")
            current = [item for item in current if item.get("id") != row["id"]]
            current.append(row)
            encoded = _json_bytes(current)
            if len(encoded) > MAX_PROFILE_BYTES:
                raise HTTPException(413, "Agent Profile 文件超过 256 KiB 上限")
            _atomic_json(profiles_path, current)
            service.repo.audit("save_agent_profile", "agent_profile",
                               object_id=row["id"], details={"command": row["command"]})
        return row

    @router.delete("/agent-bridge/profiles/{profile_id}",
                   response_model=AgentProfileDeleteState)
    def delete_profile(profile_id: str) -> dict:
        if not COMMAND.fullmatch(profile_id):
            raise HTTPException(422, "Profile ID 无效")
        with profiles_lock:
            current = profiles()["items"]
            remaining = [item for item in current if item.get("id") != profile_id]
            removed = len(remaining) != len(current)
            if removed:
                _atomic_json(profiles_path, remaining)
                service.repo.audit("delete_agent_profile", "agent_profile",
                                   object_id=profile_id)
        return {"removed": removed}

    @router.post("/agent-bridge/profiles/{profile_id}/diagnose",
                 response_model=AgentDiagnosticState)
    def diagnose_profile(
            profile_id: str,
            timeout_seconds: Annotated[int, Query(ge=1, le=30)] = 10) -> dict:
        if not COMMAND.fullmatch(profile_id):
            raise HTTPException(422, "Profile ID 无效")
        with profiles_lock:
            profile = next((item for item in profiles()["items"]
                            if item.get("id") == profile_id), None)
        if profile is None:
            raise HTTPException(404, "Agent Profile 不存在")
        return diagnose_agent(profile, timeout_seconds=timeout_seconds)

    @router.post("/agent-bridge/profiles/{profile_id}/probe",
                 response_model=AgentProbeState)
    def probe_profile(
            profile_id: str,
            timeout_seconds: Annotated[int, Query(ge=5, le=180)] = 90) -> dict:
        if not COMMAND.fullmatch(profile_id):
            raise HTTPException(422, "Profile ID 无效")
        with profiles_lock:
            profile = next((item for item in profiles()["items"]
                            if item.get("id") == profile_id), None)
        if profile is None:
            raise HTTPException(404, "Agent Profile 不存在")
        from src.services.agent_connection import probe_agent_connection
        return probe_agent_connection(
            profile, data_root, timeout_seconds=timeout_seconds)

    @router.get("/industries/{folder}/agent-bridge/tasks", response_model=AgentTaskPage)
    def tasks(folder: str, limit: int = Query(50, ge=1, le=100),
              offset: int = Query(0, ge=0)) -> dict:
        folder = resolve_folder(folder)
        rows = dataio.list_research_tasks(data_root, folder)
        next_offset = offset + limit if offset + limit < len(rows) else None
        return {"industry": folder, "items": rows[offset:offset + limit],
                "total": len(rows), "offset": offset, "limit": limit,
                "next_offset": next_offset}

    @router.get("/industries/{folder}/agent-bridge/tasks/{task_id}",
                response_model=AgentTaskExport)
    def export_task(folder: str, task_id: str) -> dict:
        folder = resolve_folder(folder)
        task = next((item for item in dataio.list_research_tasks(data_root, folder)
                     if item.get("id") == task_id), None)
        if not task:
            raise HTTPException(404, "研究任务不存在")
        return {"schema_version": 1, "industry": folder, "task": task,
                "result_contract": {"status": "draft_review_required",
                                    "summary": "string",
                                    "generation_call_id": "unique-generation-call-id",
                                    "assertions": [{
                                        "text": "string",
                                        "type": "identity|event|market_size|financial|technical_performance|causal|forecast|opinion",
                                        "atomic": {
                                            "subject": "string",
                                            "subject_id": "canonical-entity-id",
                                            "predicate": "string",
                                            "object": "value",
                                            "time": "ISO-8601 or explicit period",
                                            "region": "string", "value": "number|null",
                                            "unit": "string|null", "currency": "ISO-4217|null",
                                            "period": "string|null",
                                            "statistical_definition": "string|null",
                                            "qualifiers": {},
                                        },
                                        "citations": [{
                                            "url": "https://...",
                                            "role": "support|conversion_benchmark",
                                            "content_hash": "sha256-hex",
                                            "locator": {
                                                "type": "text_offset",
                                                "start": 0, "end": 1,
                                            },
                                        }],
                                    }]}}

    @router.get("/industries/{folder}/agent-bridge/results",
                response_model=AgentResultPage)
    def results(folder: str, limit: int = Query(50, ge=1, le=100),
                offset: int = Query(0, ge=0)) -> dict:
        folder = resolve_folder(folder)
        _index_legacy_results(folder)
        return service.repo.list_agent_results(folder, limit=limit, offset=offset)

    @router.get("/industries/{folder}/agent-bridge/results/{result_id}",
                response_model=AgentResultState)
    def result_detail(folder: str, result_id: str) -> dict:
        folder = resolve_folder(folder)
        return _repository_result(folder, result_id)

    @router.post("/industries/{folder}/agent-bridge/results/{result_id}/review",
                 response_model=AgentResultState)
    def review_result(folder: str, result_id: str, payload: AgentReviewRequest) -> dict:
        folder = resolve_folder(folder)
        current = _repository_result(folder, result_id)
        if payload.assertion_id not in {item["id"] for item in current["assertions"]}:
            raise HTTPException(404, "Agent 断言不存在")
        try:
            service.repo.review_agent_assertion(
                folder, payload.assertion_id, decision=payload.decision,
                actor="local-user", note=payload.note)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Agent 断言不存在") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return service.repo.get_agent_result(folder, current["result_id"])

    @router.post("/industries/{folder}/agent-bridge/results", status_code=201,
                 response_model=AgentResultState)
    def import_result(folder: str, payload: AgentResultImport) -> dict:
        folder = resolve_folder(folder)
        tasks = dataio.list_research_tasks(data_root, folder)
        if not any(item.get("id") == payload.task_id for item in tasks):
            raise HTTPException(404, "研究任务不存在")
        raw = payload.model_dump_json().encode("utf-8")
        if len(raw) > MAX_RESULT_BYTES:
            raise HTTPException(413, "Agent 结果超过 500 KiB 上限")
        if any(not assertion.citations for assertion in payload.assertions):
            raise HTTPException(422, "每条断言必须至少包含一个 HTTP(S) 引用")
        digest = hashlib.sha256(raw).hexdigest()
        record = {**payload.model_dump(mode="json"), "industry": folder,
                  "status": "draft_review_required", "content_sha256": digest,
                  "result_id": digest,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        if len(_json_bytes(record)) > MAX_RESULT_BYTES:
            raise HTTPException(413, "Agent 结果超过 500 KiB 上限")
        target = (data_root / folder / "one_time" / "agent_results" /
                  payload.task_id / f"{digest}.json")
        with result_import_lock:
            indexed, duplicate = _store_and_index_result(folder, record, target)
        return {**indexed, "path": str(target), "duplicate": duplicate}

    @router.post("/industries/{folder}/agent-bridge/results/{result_id}/verify",
                 response_model=AgentVerificationState)
    def verify_result(
            folder: str, result_id: str,
            limit: Annotated[int, Query(ge=1, le=10)] = 10,
            offset: Annotated[int, Query(ge=0)] = 0) -> dict:
        folder = resolve_folder(folder)
        result = _repository_result(folder, result_id)
        eligible = [item for item in result["assertions"]
                    if item["status"] in {
                        "submitted_for_verification", "candidate", "disputed",
                        "accepted", "rejected"} and
                    (item["status"] == "submitted_for_verification" or
                     bool(item.get("verification")))]
        if not eligible:
            return _bounded_verification_state({
                "result_id": result["result_id"],
                "status": "no_submitted_assertions",
                "detail": "No submitted assertion is ready for verification",
                "decisions": [], "total": 0, "offset": offset, "limit": limit,
                "next_offset": None})
        total = len(eligible)
        page = eligible[offset:offset + limit]
        decisions = []
        for assertion in page:
            try:
                decision = assertion_verifier.verify(
                    service.repo, folder, assertion["id"])
            except FileNotFoundError as exc:
                raise HTTPException(404, "Agent 断言不存在") from exc
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            decisions.append({
                "assertion_id": assertion["id"],
                "disposition": decision.disposition,
                "claim_id": decision.claim_id,
                "checks": decision.checks,
            })
        fully_accepted = bool(decisions) and all(
            item["disposition"] == "accepted" for item in decisions)
        retryable = any(item["checks"].get("semantic_support", {}).get("retryable")
                        for item in decisions)
        next_offset = offset + len(page) if offset + len(page) < total else None
        return _bounded_verification_state({
            "result_id": result["result_id"],
            "status": ("verified" if fully_accepted else
                       "retryable" if retryable else "partial"),
            "detail": ("Semantic verifier is not configured; retry after configuration"
                       if retryable else "Assertion verification completed"),
            "decisions": decisions, "total": total, "offset": offset,
            "limit": limit, "next_offset": next_offset})

    return router
