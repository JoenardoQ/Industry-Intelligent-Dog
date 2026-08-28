"""Execute saved research task bundles through an explicitly configured LLM."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .llm_service import LLMService


def _load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("tasks"), list):
            return [item for item in data["tasks"] if isinstance(item, dict)]
        return [data]
    raise ValueError("任务包必须是 JSON 对象或数组")


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


def execute_bundle(config: dict, ctx, bundle_path: str | Path,
                   provider: str = None) -> dict:
    bundle = Path(bundle_path).resolve()
    if not bundle.exists() or not bundle.is_file():
        raise ValueError(f"任务包不存在: {bundle}")
    tasks = _load_tasks(bundle)
    if not tasks:
        raise ValueError("任务包中没有可执行任务")
    client = LLMService(config, provider=provider)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []
    for index, task in enumerate(tasks, 1):
        prompt = task.get("prompt") or task.get("summary")
        if not isinstance(prompt, str) or not prompt.strip():
            results.append({"index": index, "status": "skipped", "reason": "缺少 prompt"})
            continue
        fallback = f"task_{index:02d}_{run_id}"
        output = _safe_output(task, ctx.industry_root, fallback)
        result = client.complete(prompt)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.text, encoding="utf-8")
        urls = sorted(set(re.findall(r"https?://[^\s\])}>\"']+", result.text)))
        quality = {
            "citation_count": len(urls),
            "has_fact_opinion_labels": ("事实" in result.text and "研判" in result.text),
            "minimum_citations_passed": len(urls) >= 3,
        }
        results.append({
            "index": index, "title": task.get("title", fallback),
            "status": "draft", "output_file": str(output),
            "provider": result.provider, "model": result.model,
            "response_id": result.response_id, "usage": result.usage,
            "quality": quality,
        })
    run_dir = ctx.industry_root / "one_time" / "research" / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = run_dir / f"{run_id}.json"
    manifest.write_text(json.dumps({
        "run_id": run_id, "bundle": str(bundle),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "results": results,
        "review_required": True,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"manifest": str(manifest), "results": results}
