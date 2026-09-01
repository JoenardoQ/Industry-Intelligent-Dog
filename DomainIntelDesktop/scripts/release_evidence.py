"""Create a platform-scoped native artifact evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


SUFFIXES = {"windows": ".exe", "macos": ".dmg", "linux": ".AppImage"}


def build_manifest(dist: Path, platform: str, revision: str) -> dict:
    suffix = SUFFIXES[platform]
    candidates = sorted(path for path in Path(dist).iterdir()
                        if path.is_file() and path.name.startswith("IntDog-")
                        and path.name.endswith(suffix))
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one {platform} artifact, found {len(candidates)}")
    artifact = candidates[0]
    digest = hashlib.sha256()
    with artifact.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"schema": "intdog-native-evidence-v1", "platform": platform,
            "revision": revision,
            "artifacts": [{"name": artifact.name, "size": artifact.stat().st_size,
                           "sha256": digest.hexdigest()}]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument("--platform", required=True, choices=tuple(SUFFIXES))
    parser.add_argument("--revision", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.revision:
        raise SystemExit("release revision is required")
    manifest = build_manifest(args.dist, args.platform, args.revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    os.replace(temporary, args.output)
    hash_file = args.output.with_suffix(".sha256")
    item = manifest["artifacts"][0]
    hash_file.write_text(f"{item['sha256']}  {item['name']}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
