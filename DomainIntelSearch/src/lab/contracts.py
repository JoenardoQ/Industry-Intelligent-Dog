"""Shared Intelligence Lab constants and deterministic identifiers."""

from __future__ import annotations

import hashlib
import json
import re


ALGORITHM_VERSION = "intelligence-lab/1.2"
SOURCE_CATEGORIES = ("official", "associations", "blogs", "platforms",
                     "self_media", "news", "journals", "financials", "finance")
LIMITATION = ("结果只描述本地已观察数据；未发现不等于不存在。分析结果与情景传播均需人工复核，"
              "情景分数不是概率，也不构成因果预测或投资建议。")


def content_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip(), flags=re.UNICODE)
    return slug.strip("-")[:80] or "scenario"


def mermaid_text(value: object) -> str:
    """Keep data inside a quoted Mermaid label, not Mermaid syntax."""
    text = str(value or "").replace("\\", "／").replace('"', "'")
    return text.replace("[", "（").replace("]", "）").replace("\n", " ")[:160]
