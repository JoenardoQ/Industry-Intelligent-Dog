"""Stage platform-neutral runtime resources for electron-builder."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "DomainIntelDesktop" / "build" / "resources" / "intdog"


def copy_tree(relative: str) -> None:
    source = ROOT / relative
    destination = TARGET / relative
    if not source.exists():
        raise SystemExit(f"required release resource missing: {source}")
    shutil.copytree(source, destination)


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    copy_tree("DomainIntelWeb/dist")
    copy_tree("DomainIntelSearch/config")
    copy_tree("DomainIntelSearch/evaluation")
    copy_tree("DomainIntelSearch/skills")


if __name__ == "__main__":
    main()
