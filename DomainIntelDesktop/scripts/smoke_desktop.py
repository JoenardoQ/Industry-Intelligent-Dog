"""Launch a packaged desktop artifact twice and verify graceful lifecycle."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def verify_launches(application: Path, kind: str, root: Path) -> None:
    for attempt in (1, 2):
        marker = root / f"attempt-{attempt}.json"
        env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "APPDATA": str(root / "appdata"),
            "LOCALAPPDATA": str(root / "localappdata"),
            "INTDOG_E2E_MARKER": str(marker),
            "INTDOG_E2E_AUTO_CLOSE_MS": "750",
            "INTDOG_E2E_FULL_WORKFLOW": "1",
        }
        command = [str(application)]
        if kind == "appimage":
            command.append("--appimage-extract-and-run")
        command.extend(["--no-sandbox", "--disable-gpu"])
        result = subprocess.run(command, env=env, capture_output=True, text=True,
                                timeout=60)
        if result.returncode:
            raise SystemExit(
                f"desktop attempt {attempt} failed ({result.returncode})\n"
                f"stdout:\n{result.stdout[-4000:]}\nstderr:\n{result.stderr[-4000:]}")
        state = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        if state.get("state") != "stopped":
            raise SystemExit(f"desktop attempt {attempt} did not stop cleanly: {state!r}")
        expected_task = "persisted" if attempt == 2 else "completed"
        if (state.get("workflow") != "completed" or
                state.get("firstTask") != expected_task or
                state.get("rendererReady") is not True):
            raise SystemExit(f"desktop attempt {attempt} did not complete first-run workflow: {state!r}")
        if state.get("credentialLifecycle") not in {"passed", "unavailable"}:
            raise SystemExit(f"desktop attempt {attempt} did not check credential lifecycle: {state!r}")
        expected_existing = attempt == 2
        if bool(state.get("industryPreexisting")) != expected_existing:
            raise SystemExit(f"desktop attempt {attempt} persistence check failed: {state!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--kind", choices=("appimage", "windows-nsis", "macos-dmg"),
                        required=True)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise SystemExit(f"desktop artifact missing: {artifact}")
    with tempfile.TemporaryDirectory(prefix="intdog-desktop-smoke-") as temporary:
        root = Path(temporary)
        cleanup = lambda: None
        if args.kind == "windows-nsis":
            install = root / "installed"
            installed = subprocess.run([str(artifact), "/S", f"/D={install}"], timeout=90)
            if installed.returncode:
                raise SystemExit(f"NSIS install failed ({installed.returncode})")
            application = install / "IntDog.exe"
            cleanup = lambda: subprocess.run(
                [str(install / "Uninstall IntDog.exe"), "/S"], timeout=60, check=False)
        elif args.kind == "macos-dmg":
            mount = root / "mount"
            mount.mkdir()
            subprocess.run(["hdiutil", "attach", "-nobrowse", "-mountpoint", str(mount),
                            str(artifact)], check=True, timeout=90)
            applications = list(mount.glob("*.app/Contents/MacOS/*"))
            if not applications:
                raise SystemExit("DMG does not contain an application executable")
            application = applications[0]
            cleanup = lambda: subprocess.run(
                ["hdiutil", "detach", str(mount)], timeout=60, check=False)
        else:
            application = artifact
        try:
            verify_launches(application, args.kind, root)
        finally:
            cleanup()
