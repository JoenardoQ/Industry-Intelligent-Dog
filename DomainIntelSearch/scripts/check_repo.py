"""Dependency-free syntax and structural hygiene check for local development."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOTS = (Path(__file__).resolve().parents[1],
         Path(__file__).resolve().parents[2] / "DomainIntelApp")


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
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"checked {count} Python files: syntax and duplicate definitions OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
