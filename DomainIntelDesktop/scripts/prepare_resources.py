"""Deterministically stage the explicit immutable Electron runtime resources."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "DomainIntelDesktop" / "build" / "resources" / "intdog"
RESOURCE_GROUPS = {
    "web": "DomainIntelWeb/dist",
    "config": "DomainIntelSearch/config",
    "evaluation": "DomainIntelSearch/evaluation",
    "skills": "DomainIntelSearch/skills",
    "service_templates": "DomainIntelDesktop/resources/service-templates",
}
_BANNED_PARTS = {"domaininteldata", ".venv", "venv", "keys", "__pycache__"}
_BANNED_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".pyc"}


def _allowed(relative: Path) -> bool:
    parts = {part.casefold() for part in relative.parts}
    return not (parts & _BANNED_PARTS) and relative.suffix.casefold() not in _BANNED_SUFFIXES


def _copy_group(root: Path, stage: Path, group: str, relative: str) -> list[dict]:
    source = root / relative
    if not source.is_dir():
        raise FileNotFoundError(f"required release resource missing: {source}")
    rows = []
    for item in sorted(source.rglob("*")):
        if item.is_symlink():
            raise ValueError(f"release resource may not be a symlink: {item}")
        if not item.is_file():
            continue
        target_relative = item.relative_to(root)
        if not _allowed(target_relative):
            continue
        target = stage / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        rows.append({"group": group, "path": target_relative.as_posix(),
                     "size": target.stat().st_size,
                     "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    if not rows:
        raise ValueError(f"release resource group is empty: {group}")
    return rows


def _atomic_replace(stage: Path, target: Path) -> None:
    backup = target.with_name(f".{target.name}.backup-{uuid.uuid4().hex}")
    moved_old = False
    try:
        if target.exists():
            os.replace(target, backup)
            moved_old = True
        os.replace(stage, target)
    except BaseException:
        if moved_old and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)


def stage_resources(root: Path = ROOT, target: Path = TARGET) -> dict:
    root, target = Path(root).resolve(), Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_name(f".{target.name}.stage-{uuid.uuid4().hex}")
    stage.mkdir(parents=True)
    try:
        files = []
        for group, relative in RESOURCE_GROUPS.items():
            files.extend(_copy_group(root, stage, group, relative))
        manifest = {"schema": "intdog-resource-manifest-v1",
                    "groups": RESOURCE_GROUPS,
                    "files": sorted(files, key=lambda row: row["path"])}
        (stage / "resource-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        _atomic_replace(stage, target)
        return manifest
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def main() -> None:
    manifest = stage_resources()
    print(json.dumps({"target": str(TARGET), "files": len(manifest["files"]),
                      "groups": list(manifest["groups"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
