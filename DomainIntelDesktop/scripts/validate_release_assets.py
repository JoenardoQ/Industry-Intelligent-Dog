"""Validate a complete three-platform release bundle before publication."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


class ReleaseAssetError(ValueError):
    """Raised when a native release bundle is incomplete or inconsistent."""


def _one(root: Path, name: str, description: str) -> Path:
    matches = sorted(path for path in root.rglob(name) if path.is_file())
    if len(matches) != 1:
        raise ReleaseAssetError(
            f"expected exactly one {description}, found {len(matches)}"
        )
    return matches[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_release_assets(root: Path, version: str, revision: str) -> dict[str, Path]:
    expected = {
        "windows": f"IntDog-{version}-windows-x64.exe",
        "macos": f"IntDog-{version}-macos-arm64.dmg",
        "linux": f"IntDog-{version}-linux-x86_64.AppImage",
    }
    assets: dict[str, Path] = {}
    for platform, filename in expected.items():
        installer = _one(root, filename, f"{platform} installer")
        checksum = _one(
            root, f"{platform}-artifact-evidence.sha256", f"{platform} checksum"
        )
        evidence = _one(
            root, f"{platform}-artifact-evidence.json", f"{platform} evidence"
        )
        digest = _sha256(installer)
        if checksum.read_text(encoding="utf-8") != f"{digest}  {filename}\n":
            raise ReleaseAssetError(f"{platform} checksum mismatch")
        manifest = json.loads(evidence.read_text(encoding="utf-8"))
        artifact = manifest.get("artifacts", [{}])
        if (
            manifest.get("schema") != "intdog-native-evidence-v1"
            or manifest.get("platform") != platform
            or manifest.get("revision") != revision
            or len(artifact) != 1
            or artifact[0].get("name") != filename
            or artifact[0].get("size") != installer.stat().st_size
            or artifact[0].get("sha256") != digest
        ):
            raise ReleaseAssetError(f"{platform} evidence mismatch")
        assets[platform] = installer
        assets[f"{platform}_checksum"] = checksum
    return assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        validate_release_assets(args.root, args.version, args.revision)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print("validated 3 native installers")


if __name__ == "__main__":
    main()
