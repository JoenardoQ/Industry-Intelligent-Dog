"""Dependency-free syntax and structural hygiene check for local development."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOTS = (Path(__file__).resolve().parents[1],
         Path(__file__).resolve().parents[2] / "DomainIntelApp")
_RELEASE_BANNED_PARTS = {
    "domaininteldata", ".venv", "venv", "keys", "node_modules",
    "__pycache__", "test-results", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "dist",
}
_RELEASE_BANNED_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".pyc"}


def release_manifest_violations(paths: list[str]) -> list[str]:
    """Reject mutable, secret, dependency, cache, test, and prior-build paths."""
    violations = []
    for value in paths:
        path = Path(str(value).replace("\\", "/"))
        parts = {part.casefold() for part in path.parts}
        allowed_web_dist = tuple(part.casefold() for part in path.parts[:2]) == (
            "domainintelweb", "dist")
        banned_parts = parts & _RELEASE_BANNED_PARTS
        if allowed_web_dist:
            banned_parts.discard("dist")
        if banned_parts or path.suffix.casefold() in _RELEASE_BANNED_SUFFIXES:
            violations.append(value)
    return violations


def duplicate_definitions(tree: ast.AST) -> list[tuple[str, int]]:
    duplicates = []
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        seen = set()
        for child in body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if child.name in seen:
                    duplicates.append((child.name, child.lineno))
                seen.add(child.name)
    return duplicates


def main() -> int:
    failures = []
    count = 0
    for root in ROOTS:
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or ".intdog-runtime" in path.parts:
                continue
            count += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError) as exc:
                failures.append(f"{path}: {exc}")
                continue
            for name, line in duplicate_definitions(tree):
                failures.append(f"{path}:{line}: duplicate definition {name}")
    resource_manifest = (Path(__file__).resolve().parents[2] /
                         "DomainIntelDesktop/build/resources/intdog/resource-manifest.json")
    if resource_manifest.is_file():
        try:
            payload = json.loads(resource_manifest.read_text(encoding="utf-8"))
            release_paths = [str(item.get("path") or "")
                             for item in payload.get("files", [])]
            failures.extend(
                f"release resource forbidden: {path}"
                for path in release_manifest_violations(release_paths))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            failures.append(f"{resource_manifest}: invalid resource manifest: {exc}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"checked {count} Python files: syntax and duplicate definitions OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
