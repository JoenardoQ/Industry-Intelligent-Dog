"""Exercise the installed native background service using isolated app data.

This script mutates the current account's scheduler only when the caller passes
``--allow-native-mutation``. Removal always runs in ``finally``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def _run(application: Path, arguments: list[str], env: dict[str, str],
         marker: Path, diagnostics: Path, timeout: int = 60) -> dict:
    marker.unlink(missing_ok=True)
    try:
        result = subprocess.run([str(application), *arguments], env=env,
                                capture_output=True, text=True, timeout=timeout,
                                shell=False)
    except subprocess.TimeoutExpired as exc:
        diagnostics.write_text(json.dumps({"timeout": timeout,
                                            "stdout": str(exc.stdout or "")[-4000:],
                                            "stderr": str(exc.stderr or "")[-4000:]}, indent=2),
                               encoding="utf-8")
        raise RuntimeError(f"background lifecycle timed out after {timeout}s") from exc
    diagnostics.write_text(json.dumps({"returncode": result.returncode,
                                        "stdout": result.stdout[-4000:],
                                        "stderr": result.stderr[-4000:]}, indent=2),
                           encoding="utf-8")
    payload = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
    if result.returncode != 0:
        raise RuntimeError(f"background lifecycle command failed: {arguments[0]}")
    return payload


def exercise(application: Path, kind: str, root: Path,
             *, allow_native_mutation: bool) -> dict:
    if not allow_native_mutation:
        return {"status": "external_gap",
                "reason": "native scheduler mutation not explicitly authorized"}
    marker = root / "background-marker.json"
    env = {**os.environ, "XDG_CONFIG_HOME": str(root / "config"),
           "XDG_CACHE_HOME": str(root / "cache"), "APPDATA": str(root / "appdata"),
           "LOCALAPPDATA": str(root / "localappdata"),
           "INTDOG_E2E_MARKER": str(marker),
           "INTDOG_NATIVE_SMOKE_ALLOW_SERVICE": "1"}
    common = ["--appimage-extract-and-run"] if kind == "appimage" else []
    common.extend(["--no-sandbox", "--disable-gpu"])
    try:
        installed = _run(application, [*common, "--e2e-service-install"], env,
                         marker, root / "service-install.json")
        if not installed.get("serviceInstalled") or not installed.get("serviceEnabled"):
            raise RuntimeError(f"service did not report installed/enabled: {installed!r}")
        background = _run(application, [*common, "--background-worker"], env,
                          marker, root / "background-run.json")
        if background.get("backgroundStatus") != "completed":
            raise RuntimeError(f"background worker failed: {background!r}")
        return {"status": "passed", "install": installed, "background": background}
    finally:
        removed = _run(application, [*common, "--e2e-service-remove"], env,
                       marker, root / "service-remove.json")
        if removed.get("serviceInstalled"):
            raise RuntimeError("background service remained installed after cleanup")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application", required=True, type=Path)
    parser.add_argument("--kind", required=True,
                        choices=("appimage", "windows-nsis", "macos-dmg"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--allow-native-mutation", action="store_true")
    args = parser.parse_args()
    result = exercise(args.application.resolve(), args.kind, args.root.resolve(),
                      allow_native_mutation=args.allow_native_mutation)
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "passed":
        raise SystemExit(4)


if __name__ == "__main__":
    main()
