"""Small domain primitives shared by storage and pipelines."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(namespace: str, *parts: object) -> str:
    normalized = "\x1f".join(str(part or "").strip().casefold() for part in parts)
    digest = hashlib.sha256(f"{namespace}\x1e{normalized}".encode("utf-8")).hexdigest()
    return f"{namespace}_{digest[:24]}"


def normalized_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def validate_folder(value: str) -> str:
    folder = str(value or "").strip()
    if (not folder or folder in {".", ".."} or folder.startswith("_")
            or re.search(r'[/\\:*?"<>|]', folder)):
        raise ValueError("行业文件夹名称为空或包含非法字符")
    return folder


def canonical_url(value: str) -> str:
    try:
        parts = urlsplit(str(value or "").strip())
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    ignored = {"gclid", "fbclid", "ref", "source", "spm"}
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
             if not key.casefold().startswith("utm_") and key.casefold() not in ignored]
    host = parts.netloc.casefold().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold(), host, path, urlencode(query), ""))


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_value(value: str | None, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, json.JSONDecodeError):
        return default
