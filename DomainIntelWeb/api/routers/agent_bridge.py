"""Review-gated task-package exchange for arbitrary local agents."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from ..schemas import AgentResultImport, AgentResultReview, CustomAgentProfile

MAX_RESULT_BYTES = 512_000
COMMAND = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
ARG = re.compile(r"^[A-Za-z0-9._:=@+{},-]{1,160}$")


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
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
    return profile.model_dump()


def _result_path(data_root: Path, folder: str, result_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", result_id):
        raise HTTPException(422, "结果 ID 无效")
    base = data_root / folder / "one_time" / "agent_results"
    matches = list(base.glob(f"*/{result_id}.json")) if base.is_dir() else []
    if len(matches) != 1:
        raise HTTPException(404, "Agent 结果不存在")
    return matches[0]


def build_agent_bridge_router(*, data_root: Path, dataio,
                              resolve_folder: Callable[[str], str], service) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["agent-bridge"])

    @router.get("/agent-bridge/profiles")
    def profiles() -> dict:
        path = data_root / "_settings" / "agent_profiles.json"
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        except (OSError, json.JSONDecodeError):
            rows = []
        return {"items": rows}

    @router.post("/agent-bridge/profiles", status_code=201)
    def save_profile(payload: CustomAgentProfile) -> dict:
        row = _validate_profile(payload)
        path = data_root / "_settings" / "agent_profiles.json"
        current = profiles()["items"]
        current = [item for item in current if item.get("id") != row["id"]]
        current.append(row)
        _atomic_json(path, current)
        service.repo.audit("save_agent_profile", "agent_profile",
                           object_id=row["id"], details={"command": row["command"]})
        return row

    @router.delete("/agent-bridge/profiles/{profile_id}")
    def delete_profile(profile_id: str) -> dict:
        if not COMMAND.fullmatch(profile_id):
            raise HTTPException(422, "Profile ID 无效")
        path = data_root / "_settings" / "agent_profiles.json"
        current = profiles()["items"]
        remaining = [item for item in current if item.get("id") != profile_id]
        removed = len(remaining) != len(current)
        if removed:
            _atomic_json(path, remaining)
            service.repo.audit("delete_agent_profile", "agent_profile",
                               object_id=profile_id)
        return {"removed": removed}

    @router.get("/industries/{folder}/agent-bridge/tasks")
    def tasks(folder: str) -> dict:
        folder = resolve_folder(folder)
        rows = dataio.list_research_tasks(data_root, folder)
        return {"industry": folder, "items": rows, "total": len(rows)}

    @router.get("/industries/{folder}/agent-bridge/tasks/{task_id}")
    def export_task(folder: str, task_id: str) -> dict:
        folder = resolve_folder(folder)
        task = next((item for item in dataio.list_research_tasks(data_root, folder)
                     if item.get("id") == task_id), None)
        if not task:
            raise HTTPException(404, "研究任务不存在")
        return {"schema_version": 1, "industry": folder, "task": task,
                "result_contract": {"status": "draft_review_required",
                                    "summary": "string",
                                    "assertions": [{"text": "string", "citations": ["https://..."]}]}}

    @router.get("/industries/{folder}/agent-bridge/results")
    def results(folder: str, limit: int = Query(50, ge=1, le=100),
                offset: int = Query(0, ge=0)) -> dict:
        folder = resolve_folder(folder)
        base = data_root / folder / "one_time" / "agent_results"
        rows = []
        paths = sorted(base.glob("*/*.json"), reverse=True) if base.is_dir() else []
        for path in paths[offset:offset + limit]:
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        next_offset = offset + limit if offset + limit < len(paths) else None
        return {"industry": folder, "items": rows, "total": len(paths),
                "offset": offset, "limit": limit, "next_offset": next_offset}

    @router.get("/industries/{folder}/agent-bridge/results/{result_id}")
    def result_detail(folder: str, result_id: str) -> dict:
        folder = resolve_folder(folder)
        path = _result_path(data_root, folder, result_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(409, "Agent 结果文件损坏") from exc

    @router.post("/industries/{folder}/agent-bridge/results/{result_id}/review")
    def review_result(folder: str, result_id: str, payload: AgentResultReview) -> dict:
        folder = resolve_folder(folder)
        path = _result_path(data_root, folder, result_id)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(409, "Agent 结果文件损坏") from exc
        previous = str(record.get("status") or "draft_review_required")
        record["status"] = payload.decision
        record["review"] = {"decision": payload.decision, "note": payload.note,
                            "reviewed_at": datetime.now(timezone.utc).isoformat(),
                            "actor": "local-user"}
        _atomic_json(path, record)
        service.repo.audit("review_agent_result", "agent_result", object_id=result_id,
                           details={"industry": folder, "from": previous,
                                    "status": payload.decision, "note": payload.note})
        return record

    @router.post("/industries/{folder}/agent-bridge/results", status_code=201)
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
        target = (data_root / folder / "one_time" / "agent_results" /
                  payload.task_id / f"{digest}.json")
        duplicate = target.exists()
        if not duplicate:
            _atomic_json(target, record)
            service.repo.audit("import_agent_result", "agent_result",
                               object_id=digest, details={"industry": folder,
                               "task_id": payload.task_id, "agent_id": payload.agent_id,
                               "status": "draft_review_required"})
        else:
            try:
                record = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise HTTPException(409, "已有 Agent 结果文件损坏") from exc
        return {**record, "path": str(target), "duplicate": duplicate}

    return router
