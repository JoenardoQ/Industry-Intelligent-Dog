"""Deterministic finished-artifact checks, deliberately separate from fact review."""
from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
_PLACEHOLDER = re.compile(r"\b(?:todo|tbd|lorem ipsum)\b|待补充|占位符|稍后填写", re.I)
_VAGUE = re.compile(r"值得关注|持续关注|未来可期|前景广阔|有望进一步发展")


def _slug(value: str) -> str:
    value = re.sub(r"[^\w\-\u4e00-\u9fff ]", "", value.lower()).strip()
    return re.sub(r"\s+", "-", value)


def _failure(code: str, detail: str, location: str = "") -> dict:
    return {"code": code, "detail": detail, "location": location}


def evaluate_artifact(markdown: str, metadata: dict | None = None,
                      *, sidecar_path: str | Path | None = None) -> dict:
    """Return stable machine-readable product-quality results.

    The input fact status is copied to ``fact_state`` but never altered. Only the
    reading artifact is downgraded to ``partial`` when a presentation gate fails.
    """
    metadata = metadata if isinstance(metadata, dict) else {}
    text = str(markdown or "").strip()
    failures: list[dict] = []
    if len(text) < 120:
        failures.append(_failure("artifact_too_short", "正文少于 120 个字符"))
    if _PLACEHOLDER.search(text):
        failures.append(_failure("placeholder_text", "正文包含占位文本"))
    for index, paragraph in enumerate(re.split(r"\n\s*\n", text)):
        if _VAGUE.search(paragraph) and not (re.search(r"\d", paragraph) or _LINK.search(paragraph)):
            failures.append(_failure("vague_paragraph", "段落只有空泛判断，缺少可核验细节", f"paragraph:{index+1}"))

    paragraphs = [re.sub(r"\s+", " ", item).strip().lower()
                  for item in re.split(r"\n\s*\n", text)
                  if item.strip() and not item.lstrip().startswith("#")]
    seen: set[str] = set()
    for index, paragraph in enumerate(paragraphs):
        if len(paragraph) >= 5 and paragraph in seen:
            failures.append(_failure("duplicate_paragraph", "存在重复段落", f"paragraph:{index+1}"))
            break
        seen.add(paragraph)

    headings = {_slug(value) for value in _HEADING.findall(text)}
    links = _LINK.findall(text)
    if len(re.findall(r"\[[^\]]+\]\(", text)) > len(links):
        failures.append(_failure("malformed_markdown_link", "Markdown 链接括号不完整"))
    for label, target in links:
        target = target.strip()
        if target.startswith("#"):
            if _slug(target[1:]) not in headings:
                failures.append(_failure("missing_internal_anchor", f"内部锚点不存在：{target}", label))
        else:
            parsed = urlparse(target)
            if parsed.scheme not in {"http", "https", "mailto"}:
                failures.append(_failure("invalid_link", f"不安全或无效链接：{target}", label))

    claims = metadata.get("claims") or []
    for index, claim in enumerate(claims if isinstance(claims, list) else []):
        evidence = claim.get("evidence_urls") or claim.get("citations") or claim.get("evidence")
        if not evidence:
            failures.append(_failure("claim_without_evidence", "结论没有关联证据", f"claims:{index}"))

    sections = re.split(r"(?m)^##\s+", text)[1:]
    for index, section in enumerate(sections):
        heading, _, body = section.partition("\n")
        plain = re.sub(r"[#*`>|\[\]()]", " ", body)
        plain = re.sub(r"https?://\S+", "", plain)
        if len(re.sub(r"\s+", "", plain)) < 24:
            failures.append(_failure("key_item_missing_summary", "重点条目缺少具体摘要", f"section:{index+1}"))
        if not re.search(r"\b20\d{2}[-年/]\d{1,2}", heading + "\n" + body):
            failures.append(_failure("key_item_missing_date", "重点条目缺少日期", f"section:{index+1}"))
        if not any(url.startswith(("http://", "https://")) for _, url in _LINK.findall(body)):
            failures.append(_failure("key_item_missing_source", "重点条目缺少来源", f"section:{index+1}"))

    references = metadata.get("references") or []
    if not references and not any(url.startswith(("http://", "https://")) for _, url in _LINK.findall(text)):
        failures.append(_failure("missing_sources", "产物没有来源链接"))
    if not metadata.get("generated_at") and not re.search(r"\b20\d{2}[-年/]\d{1,2}", text):
        failures.append(_failure("missing_date", "重点内容没有日期或生成时间"))

    # Numeric citations must resolve to the structured reference manifest. A URL
    # elsewhere in the paragraph cannot silently satisfy a dangling ``[n]``.
    reference_ids = {str(item.get("id")) for item in references
                     if isinstance(item, dict) and item.get("id") is not None}
    reference_ids.update(re.findall(r"(?m)^\s*-?\s*\[(\d+)\]\s+.+https?://", text))
    cited_ids = set(re.findall(r"\[(\d+)\](?!\()", text))
    for identifier in sorted(cited_ids - reference_ids):
        failures.append(_failure("dangling_reference",
                                 f"引用编号没有对应 reference：[{identifier}]"))

    documents = metadata.get("documents") or []
    document_ids = {str(item.get("id")) for item in documents
                    if isinstance(item, dict) and item.get("id")}
    evidence = metadata.get("evidence") or []
    evidence_ids = {str(item.get("id")) for item in evidence
                    if isinstance(item, dict) and item.get("id")}
    for index, claim in enumerate(claims if isinstance(claims, list) else []):
        links = claim.get("evidence") or []
        citation_values = claim.get("evidence_urls") or claim.get("citations") or []
        for citation in citation_values if isinstance(citation_values, list) else []:
            numbered = re.fullmatch(r"\[(\d+)\]", str(citation).strip())
            if numbered and numbered.group(1) not in reference_ids:
                failures.append(_failure(
                    "dangling_claim_evidence", "深研 claim 指向不存在的 reference",
                    f"claims:{index}"))
                break
        for link in links if isinstance(links, list) else []:
            if not isinstance(link, dict):
                continue
            document_id = str(link.get("document_id") or "")
            evidence_id = str(link.get("evidence_id") or "")
            if ((document_id and document_id not in document_ids) or
                    (evidence_id and evidence_id not in evidence_ids)):
                failures.append(_failure(
                    "dangling_claim_evidence", "深研 claim 指向不存在的 Document/Evidence",
                    f"claims:{index}"))
                break

    if sidecar_path is not None:
        try:
            sidecar = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
            if not isinstance(sidecar, dict):
                raise ValueError("sidecar must be an object")
            schema = sidecar.get("schema_version")
            if schema is not None and schema != 1:
                failures.append(_failure("invalid_sidecar_schema",
                                         f"不支持的 sidecar schema_version：{schema}"))
            for ref in sidecar.get("data_refs", []) or []:
                kind, separator, identifier = str(ref).partition(":")
                valid = ((kind == "document" and identifier in document_ids) or
                         (kind == "evidence" and identifier in evidence_ids))
                if not separator or not valid:
                    failures.append(_failure("dangling_sidecar_data_ref",
                                             f"sidecar 数据引用不存在：{ref}"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            failures.append(_failure("invalid_sidecar", f"可视化 sidecar 无法解析：{type(exc).__name__}"))

    fact_state = str(metadata.get("status") or "unknown")
    return {
        "version": "artifact-quality-v1", "passed": not failures,
        "fact_state": fact_state,
        "artifact_status": fact_state if not failures else "partial",
        "content_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "failures": failures,
    }
