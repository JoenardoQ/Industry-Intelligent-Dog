"""Crash-safe, hash-verifiable Intelligence Lab artifact bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_bundle(path: Path) -> dict:
    """Validate a bundle manifest and return its artifact, or raise ValueError."""
    manifest_path = path / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无效产物清单：{path}") from exc
    for name, expected in manifest.get("sha256", {}).items():
        candidate = path / name
        if not candidate.is_file() or _digest(candidate) != expected:
            raise ValueError(f"产物校验失败：{candidate}")
    return json.loads((path / "artifact.json").read_text(encoding="utf-8"))


def write_bundle(service, base: Path, kind: str, artifact_id: str,
                 payload: dict, markdown: str, extras: dict[str, str] | None = None) -> Path:
    """Stage a unique immutable bundle, validate it, then atomically publish latest."""
    root = base / "artifacts" / kind
    root.mkdir(parents=True, exist_ok=True)
    target = root / artifact_id
    if not target.exists():
        stage = Path(tempfile.mkdtemp(prefix=f".{artifact_id}-", dir=root))
        try:
            service.write_json(stage / "artifact.json", payload)
            service.write_text(stage / "artifact.md", markdown)
            for name, content in (extras or {}).items():
                if Path(name).name != name:
                    raise ValueError(f"非法产物文件名：{name}")
                service.write_text(stage / name, content)
            files = sorted(path.name for path in stage.iterdir() if path.is_file())
            service.write_json(stage / "manifest.json", {
                "artifact_id": artifact_id, "kind": kind,
                "sha256": {name: _digest(stage / name) for name in files},
            })
            validate_bundle(stage)
            stage.replace(target)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    else:
        validate_bundle(target)
    pointer = base / "latest" / f"{kind}.json"
    service.write_json(pointer, {"artifact_id": artifact_id,
                                 "bundle": str(target.relative_to(base))})
    return target


def list_valid_bundles(base: Path, kind: str) -> list[dict]:
    out = []
    root = base / "artifacts" / kind
    if not root.exists():
        return out
    for path in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        try:
            item = validate_bundle(path)
        except ValueError:
            continue
        item["_bundle_path"] = str(path)
        out.append(item)
    return sorted(out, key=lambda item: (item.get("generated_at", ""),
                                          item.get("artifact_id", "")), reverse=True)


def audit_bundles(base: Path, *, repair_latest: bool = False) -> dict:
    result = {"valid": 0, "invalid": 0, "invalid_pointers": 0,
              "repaired_pointers": 0, "errors": []}
    artifacts = base / "artifacts"
    if not artifacts.exists():
        return result
    for kind_dir in sorted(path for path in artifacts.iterdir() if path.is_dir()):
        valid = []
        for path in sorted((p for p in kind_dir.iterdir() if p.is_dir()), reverse=True):
            try:
                payload = validate_bundle(path)
                result["valid"] += 1
                valid.append((payload.get("generated_at", ""), path.name, path))
            except ValueError as exc:
                result["invalid"] += 1
                result["errors"].append(str(exc))
        pointer = base / "latest" / f"{kind_dir.name}.json"
        pointer_valid = False
        try:
            pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
            referenced = (base / pointer_data["bundle"]).resolve()
            if referenced.is_relative_to(base.resolve()):
                validate_bundle(referenced)
                newest = max(valid)[2].resolve() if valid else None
                pointer_valid = referenced == newest
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            pass
        if not pointer_valid:
            result["invalid_pointers"] += 1
        if repair_latest and valid and not pointer_valid:
            _, artifact_id, path = max(valid)
            pointer.parent.mkdir(parents=True, exist_ok=True)
            tmp = pointer.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"artifact_id": artifact_id,
                                       "bundle": str(path.relative_to(base))},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(pointer)
            result["repaired_pointers"] += 1
    return result
