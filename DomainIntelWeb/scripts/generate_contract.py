"""Generate deterministic TypeScript declarations from the checked OpenAPI file."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "openapi.json"
OUTPUT = ROOT / "src" / "generated" / "openapi.ts"


def ts_type(schema: dict) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema:
        types = [ts_type(item) for item in schema["anyOf"]]
        return " | ".join(dict.fromkeys(types))
    kind = schema.get("type")
    if kind == "array":
        return f"Array<{ts_type(schema.get('items') or {})}>"
    if kind == "object":
        additional = schema.get("additionalProperties")
        return f"Record<string, {ts_type(additional)}>" if isinstance(additional, dict) \
            else "Record<string, unknown>"
    return {"string": "string", "integer": "number", "number": "number",
            "boolean": "boolean", "null": "null"}.get(kind, "unknown")


def component(name: str, schema: dict) -> str:
    properties = schema.get("properties") or {}
    if schema.get("type") != "object" or not properties:
        return f"export type {name} = {ts_type(schema)}\n"
    required = set(schema.get("required") or [])
    rows = [f"export interface {name} {{"]
    for key in sorted(properties):
        optional = "" if key in required else "?"
        rows.append(f"  {json.dumps(key)}{optional}: {ts_type(properties[key])}")
    rows.append("}")
    return "\n".join(rows) + "\n"


def main() -> None:
    contract = json.loads(INPUT.read_text(encoding="utf-8"))
    paths = sorted(contract.get("paths") or {})
    operations = []
    for path in paths:
        for method in sorted(contract["paths"][path]):
            if method in {"get", "post", "put", "patch", "delete"}:
                operations.append(f"{method.upper()} {path}")
    lines = [
        "/* Generated from openapi.json. Do not edit by hand. */",
        f"export type ApiPath = {' | '.join(json.dumps(path) for path in paths) or 'never'}",
        f"export type ApiOperation = {' | '.join(json.dumps(op) for op in operations) or 'never'}",
        "",
    ]
    schemas = ((contract.get("components") or {}).get("schemas") or {})
    for name in sorted(schemas):
        lines.append(component(name, schemas[name]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
