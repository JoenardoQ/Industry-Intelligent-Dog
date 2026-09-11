"""Execute saved research task bundles through an explicitly configured LLM."""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from .provider_factory import create_provider
from ..artifact_quality import evaluate_artifact


def _load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        tasks = data
    elif isinstance(data, dict):
        if isinstance(data.get("tasks"), list):
            tasks = data["tasks"]
        else:
            tasks = [data]
    else:
        raise ValueError("任务包必须是 JSON 对象或数组")
    if any(not isinstance(item, dict) for item in tasks):
        raise ValueError("任务包中的每项必须是 JSON 对象")
    return tasks


def _safe_output(task: dict, industry_root: Path, fallback_name: str) -> Path:
    extra = task.get("extra", {}) or {}
    raw = extra.get("output_file") or task.get("output_file") or \
        f"one_time/research/api_runs/{fallback_name}.md"
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = industry_root / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(industry_root.resolve()):
        raise ValueError(f"任务输出路径越界: {raw}")
    return candidate


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".intdog-write-", dir=path.parent) as directory:
        temporary = Path(directory) / "content"
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)


def execute_bundle(config: dict, ctx, bundle_path: str | Path,
                   provider: str = None) -> dict:
    bundle = Path(bundle_path).resolve()
    if not bundle.exists() or not bundle.is_file():
        raise ValueError(f"任务包不存在: {bundle}")
    tasks = _load_tasks(bundle)
    if not tasks:
        raise ValueError("任务包中没有可执行任务")
    run_base = ctx.industry_root / "one_time" / "research" / "runs"
    run_base.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(
        prefix=datetime.now().strftime("%Y%m%d_%H%M%S_"), dir=run_base))
    run_id = run_dir.name
    manifest = run_base / f"{run_id}.json"
    results = []
    created_at = datetime.now().isoformat(timespec="seconds")

    def checkpoint(status: str) -> dict:
        state = {
            "run_id": run_id, "bundle": str(bundle), "created_at": created_at,
            "results": results, "status": status,
            "counts": dict(Counter(item["status"] for item in results)),
            "review_required": True,
        }
        _write_text(manifest, json.dumps(state, ensure_ascii=False, indent=2))
        return {**state, "manifest": str(manifest)}

    checkpoint("running")
    client = None
    for index, task in enumerate(tasks, 1):
        item = {"index": index, "title": task.get("title") or f"task_{index:02d}",
                "status": "running"}
        results.append(item)
        prompt = task.get("prompt") or task.get("summary")
        if not isinstance(prompt, str) or not prompt.strip():
            item.update(status="skipped", reason="缺少 prompt")
            checkpoint("running")
            continue
        try:
            snapshot = run_dir / f"task_{index:02d}.md"
            destination = task.get("output_file") or (task.get("extra") or {}).get("output_file")
            output = (_safe_output(task, ctx.industry_root, f"task_{index:02d}_{run_id}")
                      if destination else snapshot)
            item.update(output_file=str(output), snapshot_file=str(snapshot))
            checkpoint("running")
            if client is None:
                client = create_provider(config, provider, ctx.industry_root)
            result = client.complete(prompt)
            _write_text(snapshot, result.text)
            if output != snapshot:
                _write_text(output, result.text)
            quality = evaluate_artifact(result.text, {
                "status": "draft", "generated_at": created_at,
                "artifact_type": task.get("artifact_type", "research"),
            })
            item.update(status=quality["artifact_status"], provider=result.provider,
                        model=result.model, response_id=result.response_id,
                        usage=result.usage, quality=quality)
        except Exception as exc:
            # This is the durable task boundary: retain progress, not provider secrets.
            item.update(status="failed", error_type=type(exc).__name__,
                        reason=f"任务执行失败（{type(exc).__name__}）")
            results.extend({"index": pending_index, "title": pending.get("title") or
                            f"task_{pending_index:02d}", "status": "not_started"}
                           for pending_index, pending in enumerate(tasks[index:], index + 1))
            return checkpoint("partial")
        checkpoint("running")
    return checkpoint("draft" if all(item["status"] == "draft" for item in results) else "partial")
