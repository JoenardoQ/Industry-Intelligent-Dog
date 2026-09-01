"""Build the one-file API/CLI sidecar on the current native platform."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "DomainIntelDesktop" / "build" / "backend"
RESOURCE_ROOT = ROOT / "DomainIntelDesktop" / "build" / "resources" / "intdog"


def verify_resource_manifest() -> dict:
    manifest_path = RESOURCE_ROOT / "resource-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "release resources are not prepared; run "
            "DomainIntelDesktop/scripts/prepare_resources.py first"
        ) from exc
    expected = {"web", "config", "evaluation", "skills", "service_templates"}
    if manifest.get("schema") != "intdog-resource-manifest-v1":
        raise SystemExit("unsupported or invalid release resource manifest")
    if set(manifest.get("groups", {})) != expected or not manifest.get("files"):
        raise SystemExit("release resource manifest is incomplete")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-arch", choices=("native", "universal2"),
                        default="native")
    args = parser.parse_args()
    verify_resource_manifest()
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    work = ROOT / "DomainIntelDesktop" / "build" / "pyinstaller"
    dist = work / "dist"
    if work.exists():
        shutil.rmtree(work)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--name", "intdog-runtime", "--distpath", str(dist),
        "--workpath", str(work / "work"), "--specpath", str(work / "spec"),
        "--paths", str(ROOT), "--paths", str(ROOT / "DomainIntelSearch"),
        "--paths", str(ROOT / "DomainIntelApp"),
        "--collect-submodules", "DomainIntelWeb.api",
        "--collect-submodules", "runtime", "--collect-submodules", "src",
        "--collect-submodules", "intdog_core",
        "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan.on",
    ]
    if args.target_arch == "universal2":
        command.extend(["--target-architecture", "universal2"])
    command.append(str(ROOT / "DomainIntelApp" / "packaging" / "entry.py"))
    subprocess.run(command, check=True)
    suffix = ".exe" if sys.platform == "win32" else ""
    source = dist / f"intdog-runtime{suffix}"
    shutil.copy2(source, OUTPUT / source.name)


if __name__ == "__main__":
    main()
