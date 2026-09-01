"""Deterministic, assertion-level evidence gates for imported Agent results.

The verifier consumes content returned by a trusted fetch/evaluation adapter.  It
never trusts publisher tiers or semantic scores embedded in the Agent import.
"""

from __future__ import annotations

import json
import inspect
import ipaddress
import io
import re
import socket
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
from typing import Callable, Literal
from urllib.parse import urljoin, urlsplit

import requests

from intdog_core.models import canonical_url, json_value
from intdog_core.source_trust import evidence_publisher_profile


SemanticDecision = Literal["supported", "partial", "contradicted", "unknown"]
Disposition = Literal["candidate", "disputed", "accepted", "rejected"]
_PASSING = {"passed", "not_applicable"}
_JUDGMENT_TYPES = {
    "causal", "causality", "forecast", "investment_judgment", "investment",
    "opinion", "judgment",
}
_OFFICIAL_ONE_SOURCE = {
    "identity", "regulatory_status", "formal_company_disclosure",
    "company_disclosure",
}
_EVENT_TYPES = {"event", "transaction", "value_chain_relationship"}
_MARKET_TYPES = {
    "market_size", "market_share", "valuation", "unofficial_statistics",
}
_FINANCIAL_TYPES = {"financial", "financial_figure"}
_TECHNICAL_TYPES = {"technical_performance", "technical"}
MAX_VERIFICATION_CITATIONS = 20
MAX_TOTAL_FETCH_BYTES = 512 * 1024
MAX_PROVIDER_EXCERPT_BYTES = 16 * 1024
MAX_PROVIDER_TOTAL_EXCERPT_BYTES = 64 * 1024
MAX_PROVIDER_APPROX_TOKENS = 16_000
MAX_STORED_VERIFICATION_BYTES = 256 * 1024
_FINANCIAL_SIGNAL_TERMS = (
    "assets", "total assets", "liabilities", "debt", "equity",
    "shareholders' equity", "ebitda", "ebit", "operating income",
    "net income", "revenue", "net sales", "gross profit", "operating profit",
    "profit", "earnings", "cash flow", "operating cash flow", "free cash flow",
    "capital expenditure", "capex", "accounts receivable", "accounts payable",
    "inventory", "资产", "总资产", "负债", "债务", "股东权益", "所有者权益",
    "息税折旧摊销前利润", "息税前利润", "营业利润", "净利润", "营收", "收入",
    "销售额", "毛利润", "现金流", "经营现金流", "自由现金流", "资本开支",
    "资本性支出", "应收账款", "应付账款", "存货",
    "eps", "diluted eps", "r&d expense", "dividend", "cogs",
    "每股收益", "稀释每股收益", "研发费用", "股息", "营业成本",
)
_TYPE_ALIASES = {
    "identity": "identity",
    "regulatory_status": "regulatory_status",
    "formal_company_disclosure": "formal_company_disclosure",
    "company_disclosure": "formal_company_disclosure",
    "event": "event",
    "transaction": "transaction",
    "value_chain_relationship": "value_chain_relationship",
    "market_size": "market_size",
    "market_share": "market_share",
    "valuation": "valuation",
    "unofficial_statistics": "unofficial_statistics",
    "financial": "financial",
    "financial_figure": "financial",
    "technical": "technical_performance",
    "technical_performance": "technical_performance",
    "causal": "causal",
    "causality": "causal",
    "forecast": "forecast",
    "forecast_estimate": "forecast",
    "estimate": "forecast",
    "investment": "investment_judgment",
    "investment_judgment": "investment_judgment",
    "opinion": "opinion",
}


@dataclass(frozen=True)
class EvidenceProbe:
    """Fetched content plus independently produced, locatable observations."""

    reachable: bool
    final_url: str
    status_code: int | None
    published_at: str = ""
    content: str = ""
    content_hash: str = ""
    locator: dict = field(default_factory=dict)
    located_text: str = ""
    semantic: SemanticDecision = "unknown"
    semantic_reason: str = ""
    verification_method: str = ""
    verifier_id: str = ""
    verifier_call_id: str = ""
    entity_ids: tuple[str, ...] = ()
    numeric_observations: tuple[dict, ...] = ()
    publisher_kind: str = ""
    experimental_conditions: tuple[tuple[str, str], ...] = ()
    page_texts: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class VerificationDecision:
    disposition: Disposition
    checks: dict[str, dict]
    claim_id: str | None


@dataclass(frozen=True)
class EvaluationEvidence:
    evidence_id: str
    role: str
    content_hash: str
    locator: dict
    excerpt: str
    page_texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticEvaluationRequest:
    assertion_id: str
    assertion_text: str
    atomic: dict
    evidence: tuple[EvaluationEvidence, ...]


@dataclass(frozen=True)
class SemanticEvaluation:
    evidence_id: str
    decision: SemanticDecision
    reason: str
    content_hash: str
    locator: dict
    evaluator_call_id: str
    entity_ids: tuple[str, ...] = ()
    numeric_observations: tuple[dict, ...] = ()
    publisher_kind: str = ""
    document_content_type: str = ""
    experimental_conditions: tuple[tuple[str, str], ...] = ()
    located_text: str = ""
    page_texts: tuple[str, ...] = ()
    structured_observations: bool = False
    assertion_type: str = ""


@dataclass(frozen=True)
class ConfiguredSemanticEvaluator:
    evaluator_id: str
    method: Literal["deterministic", "independent_model", "human"]
    evaluate: Callable[[SemanticEvaluationRequest], list[SemanticEvaluation]]
    requires_structured_observations: bool = False

    def __post_init__(self):
        if self.method not in {"deterministic", "independent_model", "human"}:
            raise ValueError("unsupported semantic evaluator method")
        if not self.evaluator_id.strip():
            raise ValueError("semantic evaluator id is required")


@dataclass(frozen=True)
class AssertionVerifier:
    fetch: Callable[[str], object]
    semantic_evaluator: ConfiguredSemanticEvaluator | None = None
    configuration_diagnostic: str = ""

    def verify(self, repo, folder: str, assertion_id: str) -> VerificationDecision:
        return verify_agent_assertion(
            repo, folder, assertion_id, fetch=self.fetch,
            semantic_evaluator=self.semantic_evaluator,
            verifier_diagnostic=self.configuration_diagnostic)


_BLOCKED_HOSTS = {
    "localhost", "localhost.localdomain", "metadata.google.internal",
    "metadata.azure.internal", "metadata.aws.internal",
}


def _public_addresses(url: str) -> set[str]:
    parsed = urlsplit(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("blocked_invalid_http_url")
    host = parsed.hostname.casefold().rstrip(".")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise ValueError("blocked_metadata_or_localhost")
    try:
        rows = socket.getaddrinfo(
            host, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("blocked_dns_resolution_failed") from exc
    addresses = {str(row[4][0]).split("%")[0] for row in rows}
    if not addresses:
        raise ValueError("blocked_dns_resolution_empty")
    for address in addresses:
        try:
            value = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("blocked_invalid_resolved_address") from exc
        if (value.is_loopback or value.is_private or value.is_link_local or
                value.is_multicast or value.is_reserved or value.is_unspecified):
            raise ValueError("blocked_non_public_address")
    return addresses


def _peer_address(response) -> str:
    try:
        connection = getattr(response.raw, "_connection", None)
        sock = getattr(connection, "sock", None)
        return str(sock.getpeername()[0]).split("%")[0] if sock else ""
    except (AttributeError, OSError, TypeError):
        return ""


def _pdf_pages(raw: bytes) -> tuple[str, ...]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
        return tuple(str(page.extract_text() or "")
                     for page in PdfReader(io.BytesIO(raw)).pages)
    except (ImportError, OSError, ValueError):
        return ()


def _extract_submitted_locator(
        text: str, raw: bytes, locator: dict) -> tuple[str, tuple[str, ...]]:
    locator_type = str(locator.get("type") or "")
    if locator_type == "text_offset":
        start, end = locator.get("start"), locator.get("end")
        if (not isinstance(start, int) or isinstance(start, bool) or
                not isinstance(end, int) or isinstance(end, bool) or
                start < 0 or end <= start or end > len(text)):
            raise ValueError("locator_text_offsets_invalid")
        return text[start:end], ()
    if locator_type == "html_selector":
        selector = str(locator.get("selector") or "").strip()
        if not selector:
            raise ValueError("locator_html_selector_missing")
        parser = _SimpleSelectorParser(selector)
        parser.feed(text)
        if not parser.text:
            raise ValueError("locator_html_selector_empty")
        return parser.text, ()
    if locator_type == "api_field":
        path = str(locator.get("path") or "").strip()
        if not path:
            raise ValueError("locator_api_path_missing")
        value = _api_field_value(text, path)
        excerpt = (value if isinstance(value, str) else
                   json.dumps(value, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")))
        return str(excerpt), ()
    if locator_type == "pdf_page":
        pages = _pdf_pages(raw)
        page, start, end = locator.get("page"), locator.get("start"), locator.get("end")
        if (not isinstance(page, int) or isinstance(page, bool) or page < 1 or
                page > len(pages) or not isinstance(start, int) or
                isinstance(start, bool) or not isinstance(end, int) or
                isinstance(end, bool) or start < 0 or end <= start or
                end > len(pages[page - 1])):
            raise ValueError("locator_pdf_page_invalid_or_extractor_unavailable")
        return pages[page - 1][start:end], pages
    raise ValueError("locator_required")


def probe_agent_evidence(
        url: str, timeout: int = 12, *, locator: dict | None = None,
        expected_hash: str = "", max_bytes: int = MAX_TOTAL_FETCH_BYTES,
        ) -> EvidenceProbe:
    """Fetch bounded public content without pretending to judge its semantics."""

    canonical = canonical_url(url)
    if not isinstance(locator, dict) or not locator:
        return EvidenceProbe(False, canonical, None, reason="locator_required")
    session = requests.Session()
    session.trust_env = False
    current_url = str(url)
    try:
        response = None
        for redirect_count in range(6):
            try:
                resolved = _public_addresses(current_url)
            except ValueError as exc:
                return EvidenceProbe(False, canonical_url(current_url), None,
                                     reason=str(exc))
            response = session.get(
                current_url, timeout=timeout, allow_redirects=False, stream=True,
                headers={"User-Agent": "IntDog/4.0 assertion-verifier"})
            peer = _peer_address(response)
            if not peer:
                response.close()
                return EvidenceProbe(False, canonical_url(current_url), None,
                                     reason="blocked_peer_address_unverifiable")
            if peer not in resolved or any(
                    flag for flag in (ipaddress.ip_address(peer).is_private,
                                      ipaddress.ip_address(peer).is_loopback,
                                      ipaddress.ip_address(peer).is_link_local)):
                response.close()
                return EvidenceProbe(False, canonical_url(current_url), None,
                                     reason="blocked_dns_rebinding_or_peer_address")
            if response.status_code in {301, 302, 303, 307, 308}:
                location = str(response.headers.get("Location") or "")
                response.close()
                if not location:
                    return EvidenceProbe(False, canonical_url(current_url),
                                         response.status_code,
                                         reason="redirect_location_missing")
                if redirect_count >= 5:
                    return EvidenceProbe(False, canonical_url(current_url),
                                         response.status_code,
                                         reason="redirect_limit_exceeded")
                current_url = urljoin(current_url, location)
                continue
            break
        if response is None:
            return EvidenceProbe(False, canonical, None, reason="fetch_failed")
        with response:
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > max(0, int(max_bytes)):
                    return EvidenceProbe(
                        False, canonical_url(response.url) or canonical_url(url),
                        response.status_code,
                        reason="response_exceeds_verification_budget")
                chunks.append(chunk)
            raw = b"".join(chunks)
            text = raw.decode(response.encoding or "utf-8", errors="replace")
            content_hash = sha256(text.encode("utf-8")).hexdigest()
            if expected_hash and expected_hash != content_hash:
                return EvidenceProbe(False, canonical_url(current_url),
                                     response.status_code, content=text,
                                     content_hash=content_hash,
                                     reason="submitted_content_hash_mismatch")
            try:
                located_text, page_texts = _extract_submitted_locator(text, raw, locator)
            except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                return EvidenceProbe(False, canonical_url(current_url),
                                     response.status_code, content=text,
                                     content_hash=content_hash,
                                     reason=str(exc))
            published_at = ""
            # HTTP Date is response time, not publication time; using it would turn
            # a reachable URL into a false temporal verification.
            header_time = response.headers.get("Last-Modified")
            if header_time:
                try:
                    published_at = parsedate_to_datetime(header_time).isoformat()
                except (TypeError, ValueError):
                    pass
            final_url = canonical_url(current_url) or canonical
            reachable = 200 <= response.status_code < 400
        return EvidenceProbe(
            reachable=reachable, final_url=final_url,
            status_code=response.status_code, published_at=published_at,
            content=text, content_hash=content_hash,
            locator=dict(locator), located_text=located_text, semantic="unknown",
            semantic_reason="public fetch does not perform semantic verification",
            verification_method="deterministic", verifier_id="intdog-public-fetch",
            page_texts=page_texts,
            reason="" if reachable else f"HTTP {response.status_code}")
    except requests.RequestException as exc:
        return EvidenceProbe(
            False, canonical_url(url), None, reason=type(exc).__name__)
    finally:
        session.close()


def _check(status: str, reason: str, *, evidence_ids: list[str],
           locators: list[dict], **details) -> dict:
    return {
        "status": status,
        "reason": reason,
        "evidence_ids": list(evidence_ids),
        "locators": list(locators),
        **details,
    }


def _probe_value(probe, name: str, default):
    if isinstance(probe, dict):
        return probe.get(name, default)
    return getattr(probe, name, default)


def _coerce_probe(value, source_url: str) -> EvidenceProbe:
    if isinstance(value, EvidenceProbe):
        return value
    return EvidenceProbe(
        reachable=bool(_probe_value(value, "reachable", False)),
        final_url=str(_probe_value(value, "final_url", source_url) or source_url),
        status_code=_probe_value(value, "status_code", None),
        published_at=str(_probe_value(value, "published_at", "") or ""),
        content=str(_probe_value(value, "content", "") or ""),
        content_hash=str(_probe_value(value, "content_hash", "") or ""),
        locator=dict(_probe_value(value, "locator", {}) or {}),
        located_text=str(_probe_value(value, "located_text", "") or ""),
        semantic=str(_probe_value(value, "semantic", "unknown") or "unknown"),
        semantic_reason=str(_probe_value(value, "semantic_reason", "") or ""),
        verification_method=str(_probe_value(value, "verification_method", "") or ""),
        verifier_id=str(_probe_value(value, "verifier_id", "") or ""),
        verifier_call_id=str(_probe_value(value, "verifier_call_id", "") or ""),
        entity_ids=tuple(_probe_value(value, "entity_ids", ()) or ()),
        numeric_observations=tuple(
            _probe_value(value, "numeric_observations", ()) or ()),
        publisher_kind=str(_probe_value(value, "publisher_kind", "") or ""),
        experimental_conditions=_condition_pairs(
            _probe_value(value, "experimental_conditions", ())),
        page_texts=tuple(_probe_value(value, "page_texts", ()) or ()),
        reason=str(_probe_value(value, "reason", "") or ""),
    )


def _load_context(repo, folder: str, assertion_id: str) -> dict:
    industry_id = repo.industry_id(folder)
    with repo.connection() as con:
        row = con.execute("""SELECT a.*,r.agent_id,r.record_json
            FROM agent_assertions a JOIN agent_results r ON r.id=a.result_id
            WHERE a.id=? AND r.industry_id=?""",
            (assertion_id, industry_id)).fetchone()
        if not row:
            raise FileNotFoundError(f"Agent assertion not found: {assertion_id}")
        citations = [dict(item) for item in con.execute("""SELECT *
            FROM agent_citations WHERE assertion_id=? ORDER BY id""",
            (assertion_id,))]
    record = json_value(row["record_json"], {})
    imported = (record.get("assertions") or [])[row["ordinal"]]
    return {
        "industry_id": industry_id,
        "row": dict(row),
        "record": record,
        "imported": imported if isinstance(imported, dict) else {},
        "citations": citations,
    }


def _atomic_statement(imported: dict) -> dict:
    atomic = imported.get("atomic")
    if isinstance(atomic, dict):
        return dict(atomic)
    keys = (
        "subject", "subject_id", "predicate", "object", "time", "region",
        "value", "unit", "currency", "period", "statistical_definition",
        "qualifiers",
    )
    return {key: imported[key] for key in keys if key in imported}


def _fetch_with_submission(
        fetch: Callable, url: str, expected: dict, *, max_bytes: int):
    try:
        signature = inspect.signature(fetch)
        parameters = signature.parameters
        supports_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values())
    except (TypeError, ValueError):
        parameters, supports_kwargs = {}, False
    kwargs = {}
    for name, value in {
            "locator": expected.get("locator"),
            "expected_hash": str(expected.get("content_hash") or ""),
            "max_bytes": max_bytes}.items():
        if supports_kwargs or name in parameters:
            kwargs[name] = value
    return fetch(url, **kwargs)


def _nonempty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _condition_pairs(value) -> tuple[tuple[str, str], ...]:
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        return ()
    pairs = []
    for item in items:
        try:
            key, field_value = item
        except (TypeError, ValueError):
            continue
        key, field_value = str(key).strip(), str(field_value).strip()
        if key and field_value:
            pairs.append((key, field_value))
    return tuple(sorted(set(pairs)))


def _valid_publication_time(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= datetime.now(timezone.utc) + timedelta(days=2)
    except (TypeError, ValueError):
        return False


def _citation_metadata(imported: dict) -> dict[str, dict]:
    metadata = {}
    for raw in imported.get("citations") or []:
        item = raw if isinstance(raw, dict) else {"url": str(raw)}
        url = canonical_url(item.get("url", ""))
        if url:
            metadata[url] = item
    return metadata


class _SimpleSelectorParser(HTMLParser):
    """Resolve the deliberately small selector subset accepted by the verifier."""

    def __init__(self, selector: str):
        super().__init__(convert_charrefs=True)
        match = re.fullmatch(
            r"(?:(?P<tag>[A-Za-z][\w-]*))?(?:#(?P<id>[\w-]+)|\.(?P<class>[\w-]+))?",
            selector.strip())
        if not match or not any(match.groupdict().values()):
            raise ValueError("unsupported HTML selector")
        self.tag = (match.group("tag") or "").casefold()
        self.element_id = match.group("id") or ""
        self.class_name = match.group("class") or ""
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = str(attrs.get("class") or "").split()
        matched = (not self.tag or tag.casefold() == self.tag)
        matched = matched and (not self.element_id or attrs.get("id") == self.element_id)
        matched = matched and (not self.class_name or self.class_name in classes)
        if self.depth:
            self.depth += 1
        elif matched:
            self.depth = 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.depth:
            self.handle_endtag(tag)

    def handle_endtag(self, _tag):
        if self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


def _api_field_value(content: str, path: str):
    value = json.loads(content)
    if path.startswith("/"):
        parts = [part.replace("~1", "/").replace("~0", "~")
                 for part in path.split("/")[1:]]
    else:
        parts = [part for part in path.split(".") if part]
    if not parts:
        raise ValueError("empty API field path")
    for part in parts:
        if isinstance(value, list):
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise KeyError(part)
    return value


def _locator_result(probe: EvidenceProbe, expected: dict) -> tuple[bool, str, dict]:
    content = probe.content
    actual_hash = sha256(content.encode("utf-8")).hexdigest() if content else ""
    locator = probe.locator if isinstance(probe.locator, dict) else {}
    record = {
        "url": canonical_url(probe.final_url),
        "content_hash": probe.content_hash,
        "locator": locator,
        "excerpt": probe.located_text,
    }
    if not content or not probe.content_hash or actual_hash != probe.content_hash:
        return False, "fetched content hash does not match the located content", record
    expected_hash = str(expected.get("content_hash") or "")
    if expected_hash and expected_hash != probe.content_hash:
        return False, "located content changed from the submitted content hash", record
    locator_type = str(locator.get("type") or "")
    if locator_type == "text_offset":
        start, end = locator.get("start"), locator.get("end")
        if (not isinstance(start, int) or isinstance(start, bool) or
                not isinstance(end, int) or isinstance(end, bool) or
                start < 0 or end <= start or end > len(content)):
            return False, "text locator offsets are outside fetched content", record
        if content[start:end] != probe.located_text:
            return False, "text locator excerpt does not match fetched content", record
    elif locator_type == "html_selector":
        if not str(locator.get("selector") or "").strip() or not probe.located_text:
            return False, "HTML locator requires a selector and excerpt", record
        try:
            parser = _SimpleSelectorParser(str(locator["selector"]))
            parser.feed(content)
        except (ValueError, TypeError) as exc:
            return False, f"HTML selector cannot be resolved: {exc}", record
        if parser.text != " ".join(probe.located_text.split()):
            return False, "HTML selector text does not equal the located excerpt", record
    elif locator_type == "pdf_page":
        page = locator.get("page")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            return False, "PDF locator requires a positive page number", record
        if page > len(probe.page_texts):
            return False, "PDF locator page was not independently extracted", record
        page_text = probe.page_texts[page - 1]
        start, end = locator.get("start"), locator.get("end")
        if (not isinstance(start, int) or isinstance(start, bool) or
                not isinstance(end, int) or isinstance(end, bool) or
                start < 0 or end <= start or end > len(page_text) or
                page_text[start:end] != probe.located_text):
            return False, "PDF page offsets do not reproduce the excerpt", record
    elif locator_type == "api_field":
        if not str(locator.get("path") or "").strip() or not probe.located_text:
            return False, "API locator requires a field path and value", record
        try:
            value = _api_field_value(content, str(locator["path"]))
        except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
            return False, "API field path cannot be resolved", record
        resolved_text = (value if isinstance(value, str) else
                         json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")))
        if str(resolved_text) != probe.located_text:
            return False, "API field value does not equal the located excerpt", record
    else:
        return False, "a reproducible locator type is required", record
    submitted_locator = expected.get("locator")
    if submitted_locator and submitted_locator != locator:
        return False, "fetched locator differs from the submitted locator", record
    return True, "content hash and locator reproduce the excerpt", record


def _decimal(value) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _same_label(left, right) -> bool:
    return " ".join(str(left or "").casefold().split()) == \
        " ".join(str(right or "").casefold().split())


def _scalar_numeric_source(value) -> dict | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return {"value": value}
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)\s*"
        r"(%|percent|percentage|万亿|亿|万)?\s*", value, re.IGNORECASE)
    if not match:
        return None
    result = {"value": match.group(1)}
    if match.group(2):
        result["unit"] = match.group(2)
    return result


def _structured_numeric_claim(
        atomic: dict, assertion_types: set[str] | None = None) -> tuple[dict | None, str]:
    """Return one complete numeric claim, wherever the producer placed it."""
    sources = [atomic]
    if isinstance(atomic.get("object"), dict):
        sources.append(atomic["object"])
    else:
        scalar = _scalar_numeric_source(atomic.get("object"))
        if scalar:
            sources.append(scalar)
    if isinstance(atomic.get("qualifiers"), dict):
        sources.append(atomic["qualifiers"])
    canonical_types = set(assertion_types or ())
    signal = any(_nonempty(source.get("value")) for source in sources)
    if not signal:
        if canonical_types & (_FINANCIAL_TYPES | _MARKET_TYPES):
            return {}, ("financial, market, and valuation assertions require a "
                        "structured numeric value, unit, period, and definition")
        return None, "assertion has no numeric value"
    merged: dict = {}
    for field_name in ("value", "unit", "currency", "period",
                       "statistical_definition"):
        values = [source.get(field_name) for source in sources
                  if _nonempty(source.get(field_name))]
        if values and any(not _same_label(values[0], item) for item in values[1:]):
            return {}, f"structured numeric field {field_name} is contradictory"
        if values:
            merged[field_name] = values[0]
    missing = [key for key in ("value", "unit", "period", "statistical_definition")
               if not _nonempty(merged.get(key))]
    unit = str(merged.get("unit") or "").casefold()
    monetary = bool(canonical_types & {"financial", "valuation", "market_size"})
    non_monetary_unit = unit in {
        "%", "percent", "percentage", "ratio", "share", "count", "unit", "units"}
    if monetary and not non_monetary_unit \
            and not _nonempty(merged.get("currency")):
        missing.append("currency")
    if missing:
        return {}, "structured numeric claim lacks required fields: " + ", ".join(missing)
    return merged, "structured numeric claim is complete"


def _conversion_benchmark(
        conversion: dict, benchmark_items: list[dict], expected: dict,
        observed_source: dict) -> tuple[bool, str, Decimal]:
    benchmark_url = canonical_url(conversion.get("benchmark_source", ""))
    rate = _decimal(conversion.get("rate"))
    formula = str(conversion.get("formula") or "")
    for item in benchmark_items:
        probe = item["probe"]
        if (canonical_url(probe.final_url) != benchmark_url or not item["locator_ok"] or
                item["profile"]["verification_status"] != "verified"):
            continue
        if str(rate) not in probe.located_text:
            continue
        for benchmark_observation in probe.numeric_observations:
            if str(benchmark_observation.get("kind") or "") != "conversion_rate":
                continue
            bindings = {
                "rate": _decimal(benchmark_observation.get("rate")) == rate,
                "formula": str(benchmark_observation.get("formula") or "") == formula,
                "from_currency": _same_label(benchmark_observation.get("from_currency"),
                                              observed_source.get("currency")),
                "to_currency": _same_label(benchmark_observation.get("to_currency"),
                                            expected.get("currency")),
                "from_unit": _same_label(benchmark_observation.get("from_unit"),
                                          observed_source.get("unit")),
                "to_unit": _same_label(benchmark_observation.get("to_unit"), expected.get("unit")),
                "period": _same_label(benchmark_observation.get("period"), expected.get("period")),
            }
            if not all(bindings.values()):
                continue
            if "tolerance" not in benchmark_observation:
                return (False,
                        "located benchmark tolerance is absent; default 0 is unverified",
                        Decimal(0))
            tolerance = _decimal(benchmark_observation.get("tolerance", 0))
            if tolerance is None or tolerance < 0:
                return False, "located benchmark tolerance is invalid", Decimal(0)
            maximum = max(abs(_decimal(conversion.get("target_value")) or Decimal(0)) *
                          Decimal("0.01"), Decimal("0.000001"))
            if tolerance > maximum:
                return False, "located benchmark tolerance exceeds safety bound", tolerance
            located = " ".join(probe.located_text.casefold().split())
            required_terms = {
                str(rate), formula.casefold(),
                str(benchmark_observation.get("from_currency") or "").casefold(),
                str(benchmark_observation.get("to_currency") or "").casefold(),
                str(benchmark_observation.get("from_unit") or "").casefold(),
                str(benchmark_observation.get("to_unit") or "").casefold(),
                str(benchmark_observation.get("period") or "").casefold(),
            }
            if "tolerance" in benchmark_observation:
                required_terms.update({"tolerance", str(tolerance)})
            if any(term and term not in located for term in required_terms):
                return False, "conversion benchmark bindings are not located in excerpt", tolerance
            return True, "conversion bindings are reproduced by benchmark evidence", tolerance
    return False, ("conversion benchmark is not a second locatable evidence item "
                   "binding rate, formula, currencies, units, and period"), Decimal(0)


def _numeric_match(expected: dict, observed: dict, benchmark_items: list[dict]) -> tuple[bool, str, dict | None]:
    expected_value = _decimal(expected.get("value"))
    observed_value = _decimal(observed.get("value"))
    if expected_value is None or observed_value is None:
        return False, "numeric value is missing or invalid", None
    for field_name in ("period", "statistical_definition"):
        if not _same_label(expected.get(field_name), observed.get(field_name)):
            return False, f"{field_name} differs", None
    conversion = observed.get("conversion")
    if not conversion:
        for field_name in ("unit", "currency"):
            if not _same_label(expected.get(field_name), observed.get(field_name)):
                return False, f"{field_name} differs", None
        if expected_value != observed_value:
            if expected_value.is_signed() != observed_value.is_signed():
                return False, "numeric sign differs", None
            return False, "numeric value or order of magnitude differs", None
        return True, "numeric value and qualifiers match", None
    if not isinstance(conversion, dict):
        return False, "conversion record is malformed", None
    required = {
        "original_value", "target_value", "target_unit", "target_currency",
        "formula", "rate", "benchmark_source",
    }
    if not required.issubset(conversion):
        return False, "conversion lacks formula, benchmark, or explicit tolerance", None
    original = _decimal(conversion.get("original_value"))
    target = _decimal(conversion.get("target_value"))
    rate = _decimal(conversion.get("rate"))
    if "tolerance" in conversion:
        return False, "conversion tolerance must come from located benchmark evidence", None
    if None in {original, target, rate} or rate <= 0:
        return False, "conversion numbers are invalid", None
    if original != observed_value:
        return False, "conversion original value differs from observed value", None
    formula = str(conversion.get("formula") or "")
    if formula == "multiply":
        calculated = original * rate
    elif formula == "divide":
        calculated = original / rate
    else:
        return False, "conversion formula is not an allowed deterministic operation", None
    if (not _same_label(expected.get("unit"), conversion.get("target_unit")) or
            not _same_label(expected.get("currency"), conversion.get("target_currency"))):
        return False, "conversion target unit or currency differs", None
    benchmark = canonical_url(conversion.get("benchmark_source", ""))
    if not benchmark or evidence_publisher_profile(benchmark)["verification_status"] != "verified":
        return False, "conversion benchmark source is not verified", None
    benchmark_ok, benchmark_reason, tolerance = _conversion_benchmark(
        conversion, benchmark_items, expected, observed)
    if not benchmark_ok:
        audit = ({
            "benchmark_source": benchmark,
            "tolerance": "0",
            "tolerance_status": "default_unverified",
        } if "tolerance is absent" in benchmark_reason else None)
        return False, benchmark_reason, audit
    if abs(calculated - target) > tolerance or abs(target - expected_value) > tolerance:
        return False, "converted value falls outside the benchmark tolerance", None
    audit = {
        "original_value": int(original) if original == int(original) else str(original),
        "target_value": int(target) if target == int(target) else str(target),
        "formula": formula,
        "rate": str(rate),
        "tolerance": str(tolerance),
        "benchmark_source": benchmark,
    }
    return True, "auditable conversion matches within tolerance", audit


def _claim_projection(repo, context: dict, atomic: dict) -> dict:
    subject_id = str(atomic.get("subject_id") or "") or None
    if subject_id:
        with repo.connection() as con:
            if not con.execute("SELECT 1 FROM entities WHERE id=?", (subject_id,)).fetchone():
                subject_id = None
    qualifiers = dict(atomic.get("qualifiers") or {})
    for key in ("subject", "time", "region", "value", "unit", "currency",
                "period", "statistical_definition"):
        if key in atomic and _nonempty(atomic.get(key)):
            qualifiers[key] = atomic[key]
    return {
        "subject_id": subject_id,
        "predicate": str(atomic.get("predicate") or "agent_assertion"),
        "object": atomic.get("object"),
        "qualifiers": qualifiers,
        "valid_from": str(atomic.get("valid_from") or ""),
        "valid_to": str(atomic.get("valid_to") or ""),
    }


def _conflicting_claims(repo, context: dict, projection: dict) -> list[str]:
    predicate = projection["predicate"]
    subject_id = projection["subject_id"]
    wanted_subject = str(projection["qualifiers"].get("subject") or "").casefold()
    wanted_period = str(projection["qualifiers"].get("period") or
                        projection["qualifiers"].get("time") or "").casefold()
    wanted_definition = str(
        projection["qualifiers"].get("statistical_definition") or "").casefold()
    with repo.connection() as con:
        rows = con.execute("""SELECT id,subject_id,object_json,qualifiers_json
            FROM claims WHERE industry_id=? AND predicate=?
            AND status IN ('accepted','verified','corroborated')
            AND superseded_at IS NULL""",
            (context["industry_id"], predicate)).fetchall()
    conflicts = []
    for row in rows:
        qualifiers = json_value(row["qualifiers_json"], {})
        existing_subject = str(qualifiers.get("subject") or "").casefold()
        if subject_id and row["subject_id"] != subject_id:
            continue
        existing_period = str(qualifiers.get("period") or qualifiers.get("time") or "").casefold()
        existing_definition = str(qualifiers.get("statistical_definition") or "").casefold()
        if wanted_period and existing_period and wanted_period != existing_period:
            continue
        if wanted_definition and existing_definition and wanted_definition != existing_definition:
            continue
        existing_object = json_value(row["object_json"], None)
        wanted_object = projection["object"]
        structured_fields = ("value", "unit", "currency", "period",
                             "statistical_definition")
        existing_values = dict(qualifiers)
        wanted_values = dict(projection["qualifiers"])
        if isinstance(existing_object, dict):
            existing_values = {**existing_object, **existing_values}
        if isinstance(wanted_object, dict):
            wanted_values = {**wanted_object, **wanted_values}
        structured_difference = any(
            _nonempty(existing_values.get(key)) and
            _nonempty(wanted_values.get(key)) and
            not _same_label(existing_values.get(key), wanted_values.get(key))
            for key in structured_fields)
        if existing_object != wanted_object or structured_difference:
            conflicts.append(row["id"])
    return sorted(conflicts)


def _period_key(value: str) -> str:
    return re.sub(r"[^0-9a-z]", "", str(value or "").casefold())


def _period_is_located(expected: str, text: str) -> bool:
    wanted = _period_key(expected)
    if not wanted:
        return True
    tokens = re.findall(
        r"(?<![0-9A-Za-z])(?:FY\s*\d{4}|Q[1-4]\s*\d{4}|"
        r"\d{4}\s*Q[1-4]|\d{4})(?![0-9A-Za-z])",
        str(text or ""), re.IGNORECASE)
    return wanted in {_period_key(token) for token in tokens}


def _conditions_are_located(
        conditions: tuple[tuple[str, str], ...], text: str) -> bool:
    if not conditions:
        return False
    located = str(text or "")
    return all(re.search(
        rf"(?<![0-9A-Za-z]){re.escape(key)}\s*[:=]\s*"
        rf"{re.escape(value)}(?![0-9A-Za-z])",
        located, re.IGNORECASE) for key, value in conditions)


def _audited_direct_party_matches(
        repo, industry_id: str, atomic: dict, item: dict) -> bool:
    """Extension point for a future independently audited entity-domain table.

    Task 3 intentionally has no such authority.  Ordinary Source/Entity JSON is
    user- or pipeline-writable and therefore cannot authorize a one-source event.
    """
    del repo, industry_id, atomic, item
    return False


def _corroboration(
        assertion_type: str, eligible: list[dict], *, expected_period: str = "",
        ) -> tuple[bool, str, list[str]]:
    clusters = sorted({item["profile"]["owner_cluster"] for item in eligible})
    official = [item for item in eligible
                if "official_identity" in item["profile"].get("authorities", ())]
    direct = [item for item in eligible
              if "direct_party" in item["profile"].get("authorities", ()) and
              item.get("direct_party_match")]
    financial_primary = [item for item in eligible
        if ({"regulatory_filing", "audited_statement"} &
            set(item["profile"].get("authorities", ()))) and
        _period_is_located(expected_period, item["probe"].located_text)]
    technical_primary = []
    for item in eligible:
        authorities = set(item["profile"].get("authorities", ()))
        if authorities & {"standard", "official_spec"}:
            technical_primary.append(item)
            continue
        conditions = item["probe"].experimental_conditions
        if ("academic_result" in authorities and
                _conditions_are_located(conditions, item["probe"].located_text)):
            technical_primary.append(item)
    if assertion_type in _OFFICIAL_ONE_SOURCE:
        passed = bool(official)
        reason = "one applicable verified official primary record is required"
    elif assertion_type in _EVENT_TYPES:
        passed = bool(direct) or len(clusters) >= 2
        reason = "one direct involved-party disclosure or two independent publishers are required"
    elif assertion_type in _MARKET_TYPES:
        passed = len(clusters) >= 2
        reason = "two ownership-independent publishers are required"
    elif assertion_type in _FINANCIAL_TYPES:
        passed = bool(financial_primary) or len(clusters) >= 2
        reason = "an applicable filing/audit or two independent secondary sources are required"
    elif assertion_type in _TECHNICAL_TYPES:
        passed = bool(technical_primary)
        reason = "a locatable standard, specification, or conditioned academic result is required"
    else:
        passed = len(clusters) >= 2
        reason = "unclassified assertions require two ownership-independent publishers"
    return passed, reason, clusters


def _normalized_type(value: str) -> str:
    key = re.sub(r"[^0-9a-z]+", "_", str(value or "").casefold()).strip("_")
    return _TYPE_ALIASES.get(key, "")


def _type_signals(atomic: dict, text: str) -> set[str]:
    signals: set[str] = set()
    predicate = _normalized_type(str(atomic.get("predicate") or ""))
    if predicate:
        signals.add(predicate)
    haystack = f"{atomic.get('predicate', '')} {atomic.get('object', '')} {text}".casefold()
    if re.search(r"\b(forecast|estimate|projected|will)\b|预计|预测|估计", haystack):
        signals.add("forecast")
    if re.search(r"\b(cause|causes|caused|drives?|because)\b|导致|驱动|因为", haystack):
        signals.add("causal")
    financial_signal = any(
        (term in haystack if not term.isascii() else
         re.search(rf"(?<![0-9a-z]){re.escape(term)}(?![0-9a-z])", haystack))
        for term in _FINANCIAL_SIGNAL_TERMS)
    if financial_signal:
        signals.add("financial")
    if re.search(r"\bmarket share\b|市场份额", haystack):
        signals.add("market_share")
    if re.search(r"\bmarket size\b|市场规模", haystack):
        signals.add("market_size")
    return signals


def _run_semantic_evaluator(
        evaluator: ConfiguredSemanticEvaluator | None, *, context: dict,
        atomic: dict, fetched: list[dict], generation_call_id: str,
        generator_id: str, unconfigured_reason: str = "", budget_error: str = "",
        ) -> tuple[list[dict], list[str], str]:
    support = [item for item in fetched if item["role"] == "support"]
    if budget_error:
        return [], [budget_error], "resource_exceeded"
    if evaluator is None:
        return [], [unconfigured_reason or "semantic verifier is not configured"], \
            "not_configured"
    request = SemanticEvaluationRequest(
        assertion_id=context["row"]["id"],
        assertion_text=context["row"]["assertion_text"], atomic=atomic,
        evidence=tuple(EvaluationEvidence(
            evidence_id=item["citation"]["id"], role=item["role"],
            content_hash=item["probe"].content_hash,
            locator=dict(item["probe"].locator), excerpt=item["probe"].located_text,
            page_texts=())
            for item in fetched))
    try:
        raw_results = evaluator.evaluate(request)
    except Exception as exc:
        return [], [f"semantic evaluator failed: {type(exc).__name__}"], "failed"
    expected_items = fetched if evaluator.requires_structured_observations else support
    by_id = {item["citation"]["id"]: item for item in expected_items}
    valid: list[dict] = []
    errors: list[str] = []
    seen = set()
    for result in raw_results if isinstance(raw_results, list) else []:
        if not isinstance(result, SemanticEvaluation):
            errors.append("semantic evaluator returned an invalid result type")
            continue
        source = by_id.get(result.evidence_id)
        if source is None or result.evidence_id in seen:
            errors.append("semantic evaluation does not map one-to-one to support evidence")
            continue
        if result.decision not in {"supported", "partial", "contradicted", "unknown"}:
            errors.append("semantic evaluator returned an invalid decision")
            continue
        if (result.content_hash != source["probe"].content_hash or
                result.locator != source["probe"].locator):
            errors.append("semantic evaluation hash/locator does not match fetched evidence")
            continue
        if evaluator.requires_structured_observations and (
                not result.structured_observations or
                result.located_text != source["probe"].located_text):
            errors.append("semantic evaluator lacks validated structured probe observations")
            continue
        same_agent = evaluator.evaluator_id == generator_id
        same_call = bool(generation_call_id and
                         result.evaluator_call_id == generation_call_id)
        if not generation_call_id or same_agent or same_call:
            errors.append("generation Agent/call is not independent from semantic evaluator")
            continue
        seen.add(result.evidence_id)
        valid.append({"source": source, "result": result,
                      "evaluator_id": evaluator.evaluator_id,
                      "method": evaluator.method})
    if len(seen) != len(expected_items):
        errors.append("not every evidence item received a validated structured decision")
    return valid, errors, "configured"


def _verification_bytes(checks: dict) -> int:
    return len(json.dumps(checks, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))


def _compact_oversized_checks(checks: dict, original_bytes: int) -> dict:
    counts = {
        "evidence_id_count": sum(len(check.get("evidence_ids") or [])
                                 for check in checks.values()),
        "locator_count": sum(len(check.get("locators") or [])
                             for check in checks.values()),
        "failure_count": sum(len(check.get("failures") or [])
                             for check in checks.values()),
    }
    compacted: dict[str, dict] = {}
    for name, check in checks.items():
        bounded = {
            "status": check.get("status", "failed"),
            "reason": str(check.get("reason") or "verification detail omitted")[:512],
            "evidence_ids": list(dict.fromkeys(check.get("evidence_ids") or []))[:20],
            "locators": [],
        }
        if name == "semantic_support":
            bounded["decision"] = check.get("decision", "unknown")
            bounded["retryable"] = bool(check.get("retryable", False))
        if name == "resource_budget":
            for field_name in ("citation_count", "fetched_bytes", "excerpt_bytes",
                               "approximate_provider_tokens", "limits"):
                if field_name in check:
                    bounded[field_name] = check[field_name]
        compacted[name] = bounded
    resource = compacted["resource_budget"]
    resource.update({
        "status": "failed",
        "reason": "verification detail exceeded the 256 KiB storage budget and was compacted",
        "budget_truncation": {
            "original_bytes": original_bytes,
            "final_bytes": 0,
            **counts,
        },
    })
    for _ in range(3):
        final_bytes = _verification_bytes(compacted)
        resource["budget_truncation"]["final_bytes"] = final_bytes
    if _verification_bytes(compacted) > MAX_STORED_VERIFICATION_BYTES:
        raise ValueError("bounded verification summary exceeds hard storage budget")
    return compacted


def verify_agent_assertion(
        repo, folder: str, assertion_id: str, *, fetch: Callable[[str], object],
        semantic_evaluator: ConfiguredSemanticEvaluator | None = None,
        verifier_diagnostic: str = "",
        ) -> VerificationDecision:
    """Run every gate and atomically persist the resulting fact disposition."""

    context = _load_context(repo, folder, assertion_id)
    row = context["row"]
    existing_checks = json_value(row["verification_json"], {})
    if row["status"] in {"candidate", "disputed", "accepted", "rejected"} and existing_checks:
        return VerificationDecision(row["status"], existing_checks, row["claim_id"])
    if row["status"] != "submitted_for_verification":
        raise ValueError(
            f"assertion must be submitted_for_verification, got {row['status']}")

    citation_metadata = _citation_metadata(context["imported"])
    evidence_ids = [item["id"] for item in context["citations"]]
    fetched: list[dict] = []
    locator_records: list[dict] = []
    citation_budget_exceeded = len(context["citations"]) > MAX_VERIFICATION_CITATIONS
    total_fetched_bytes = 0
    total_excerpt_bytes = 0
    for citation in context["citations"]:
        expected = citation_metadata.get(citation["canonical_url"], {})
        if citation_budget_exceeded:
            probe = EvidenceProbe(
                False, citation["canonical_url"], None,
                reason="verification_citation_budget_exceeded")
        else:
            try:
                remaining_bytes = max(0, MAX_TOTAL_FETCH_BYTES - total_fetched_bytes)
                if remaining_bytes == 0:
                    raise RuntimeError("verification_fetch_budget_exhausted")
                probe = _coerce_probe(
                    _fetch_with_submission(
                        fetch, citation["url"], expected, max_bytes=remaining_bytes),
                    citation["url"])
            except Exception as exc:
                probe = EvidenceProbe(
                    False, citation["canonical_url"], None,
                    reason=f"fetch_error:{type(exc).__name__}")
        total_fetched_bytes += len(probe.content.encode("utf-8"))
        total_excerpt_bytes += len(probe.located_text.encode("utf-8"))
        role = str(expected.get("role") or "support")
        if role not in {"support", "conversion_benchmark"}:
            role = "invalid"
        locator_ok, locator_reason, locator_record = _locator_result(probe, expected)
        locator_record["evidence_id"] = citation["id"]
        if locator_ok:
            locator_records.append(locator_record)
        profile = evidence_publisher_profile(probe.final_url)
        fetched.append({
            "citation": citation, "probe": probe, "profile": profile,
            "locator_ok": locator_ok, "locator_reason": locator_reason,
            "role": role,
        })

    checks: dict[str, dict] = {}
    approximate_provider_tokens = (total_excerpt_bytes + 3) // 4
    budget_failures = []
    if citation_budget_exceeded:
        budget_failures.append("citation count exceeds verification budget")
    if total_fetched_bytes > MAX_TOTAL_FETCH_BYTES:
        budget_failures.append("total fetched content exceeds verification budget")
    if any(item["probe"].reason in {
            "response_exceeds_verification_budget",
            "fetch_error:RuntimeError"} for item in fetched):
        budget_failures.append("fetch byte budget was exhausted")
    if any(len(item["probe"].located_text.encode("utf-8")) >
           MAX_PROVIDER_EXCERPT_BYTES for item in fetched):
        budget_failures.append("one or more excerpts exceed provider budget")
    if total_excerpt_bytes > MAX_PROVIDER_TOTAL_EXCERPT_BYTES or \
            approximate_provider_tokens > MAX_PROVIDER_APPROX_TOKENS:
        budget_failures.append("total provider excerpt budget is exceeded")
    budget_error = "; ".join(budget_failures)
    checks["resource_budget"] = _check(
        "failed" if budget_error else "passed",
        budget_error or "verification resource use is within bounded limits",
        evidence_ids=evidence_ids, locators=locator_records,
        citation_count=len(context["citations"]), fetched_bytes=total_fetched_bytes,
        excerpt_bytes=total_excerpt_bytes,
        approximate_provider_tokens=approximate_provider_tokens,
        limits={"citation_count": MAX_VERIFICATION_CITATIONS,
                "fetched_bytes": MAX_TOTAL_FETCH_BYTES,
                "excerpt_bytes": MAX_PROVIDER_TOTAL_EXCERPT_BYTES,
                "single_excerpt_bytes": MAX_PROVIDER_EXCERPT_BYTES,
                "approximate_provider_tokens": MAX_PROVIDER_APPROX_TOKENS,
                "stored_verification_bytes": MAX_STORED_VERIFICATION_BYTES})
    atomic = _atomic_statement(context["imported"])
    missing_atomic = [key for key in ("subject", "predicate", "object", "time", "region")
                      if not _nonempty(atomic.get(key))]
    qualifiers_valid = isinstance(atomic.get("qualifiers", {}), dict)
    atomization_ok = not missing_atomic and qualifiers_valid
    checks["atomization"] = _check(
        "passed" if atomization_ok else "failed",
        "atomic subject, predicate, object, time, region, and qualifiers are present"
        if atomization_ok else f"missing or invalid atomic fields: {', '.join(missing_atomic) or 'qualifiers'}",
        evidence_ids=evidence_ids, locators=locator_records,
        atomic=atomic if atomization_ok else None)

    reachable = [
        item for item in fetched if item["probe"].reachable and
        item["probe"].status_code is not None and
        200 <= item["probe"].status_code < 400]
    reachability_ok = len(reachable) == len(fetched) and bool(fetched)
    checks["reachability"] = _check(
        "passed" if reachability_ok else "failed",
        "all citation URLs returned a successful bounded response" if reachability_ok
        else "one or more citation URLs were unreachable",
        evidence_ids=evidence_ids, locators=locator_records,
        failures=[{
            "evidence_id": item["citation"]["id"],
            "status_code": item["probe"].status_code,
            "reason": item["probe"].reason,
        } for item in fetched if item not in reachable])

    publishers_ok = bool(fetched) and all(
        item["profile"]["verification_status"] == "verified" for item in fetched)
    checks["publisher_identity"] = _check(
        "passed" if publishers_ok else "failed",
        "publisher identities were resolved from the reviewed domain registry"
        if publishers_ok else "one or more publisher identities are not verified",
        evidence_ids=evidence_ids, locators=locator_records,
        publishers=[{
            "evidence_id": item["citation"]["id"],
            "name": item["profile"]["name"],
            "domain": item["profile"]["domain"],
            "owner_cluster": item["profile"]["owner_cluster"],
            "verification_status": item["profile"]["verification_status"],
        } for item in fetched])

    publication_ok = bool(fetched) and all(
        _valid_publication_time(item["probe"].published_at) for item in fetched)
    checks["publication_time"] = _check(
        "passed" if publication_ok else "unknown",
        "all evidence has a valid publication time" if publication_ok
        else "one or more evidence items lack a valid publication time",
        evidence_ids=evidence_ids, locators=locator_records,
        publication_times=[item["probe"].published_at for item in fetched])

    support_fetched = [item for item in fetched if item["role"] == "support"]
    entity_ids = sorted({str(entity_id) for item in support_fetched
                         for entity_id in item["probe"].entity_ids if str(entity_id)})
    expected_entity = str(atomic.get("subject_id") or "")
    subject = str(atomic.get("subject") or "").strip().casefold()
    subject_located = bool(subject) and bool(support_fetched) and all(
        subject in item["probe"].located_text.casefold() for item in support_fetched)
    entity_ok = (bool(expected_entity) and len(entity_ids) == 1 and subject_located and
                 entity_ids[0] == expected_entity)
    entity_status = "passed" if entity_ok else ("unknown" if not entity_ids else "failed")
    checks["entity_alignment"] = _check(
        entity_status,
        "evidence resolves to one aligned entity" if entity_ok else
        "entity is absent, ambiguous, or does not match the atomic subject",
        evidence_ids=evidence_ids, locators=locator_records,
        entity_ids=entity_ids, expected_entity_id=expected_entity or None)

    locator_ok = bool(fetched) and all(item["locator_ok"] for item in fetched)
    checks["locator_integrity"] = _check(
        "passed" if locator_ok else "failed",
        "every excerpt is reproducible from its content hash and locator" if locator_ok
        else "one or more evidence locators or content hashes cannot be reproduced",
        evidence_ids=evidence_ids, locators=locator_records,
        failures=[{
            "evidence_id": item["citation"]["id"],
            "reason": item["locator_reason"],
            "failure_code": "invalid_locator",
            "invalid_locator_type": (
                str(item["probe"].locator.get("type") or "") or None
                if isinstance(item["probe"].locator, dict) else None),
            "content_hash_present": bool(item["probe"].content_hash),
        }
            for item in fetched if not item["locator_ok"]])

    generation_call_id = str(context["record"].get("generation_call_id") or "").strip()
    generator_id = str(row["agent_id"] or "").strip()
    generation_ok = bool(generation_call_id and generator_id)
    checks["generation_provenance"] = _check(
        "passed" if generation_ok else "failed",
        "generation Agent and call identifiers are recorded" if generation_ok else
        "generation_call_id and generator agent_id are required for fact promotion",
        evidence_ids=evidence_ids, locators=locator_records,
        generation_call_id=generation_call_id or None, generator_id=generator_id or None)

    evaluated, semantic_errors, evaluator_mode = _run_semantic_evaluator(
        semantic_evaluator, context=context, atomic=atomic, fetched=fetched,
        generation_call_id=generation_call_id, generator_id=generator_id,
        unconfigured_reason=verifier_diagnostic, budget_error=budget_error)
    for item in evaluated:
        result = item["result"]
        source = item["source"]
        source["observed_probe"] = (replace(
            source["probe"], entity_ids=result.entity_ids,
            numeric_observations=result.numeric_observations,
            publisher_kind=result.publisher_kind,
            experimental_conditions=result.experimental_conditions)
            if result.structured_observations else source["probe"])
    observed_support = [item for item in evaluated
                        if item["source"]["role"] == "support"]
    observed_entity_ids = sorted({str(entity_id) for item in observed_support
        for entity_id in item["source"]["observed_probe"].entity_ids if str(entity_id)})
    observed_subject_located = bool(subject) and bool(observed_support) and all(
        subject in item["source"]["probe"].located_text.casefold()
        for item in observed_support)
    observed_entity_ok = (bool(expected_entity) and len(observed_entity_ids) == 1 and
                          observed_subject_located and
                          observed_entity_ids[0] == expected_entity)
    checks["entity_alignment"] = _check(
        "passed" if observed_entity_ok else
        ("unknown" if not observed_entity_ids else "failed"),
        "evidence resolves to one aligned entity" if observed_entity_ok else
        "entity is absent, ambiguous, or does not match the atomic subject",
        evidence_ids=[item["source"]["citation"]["id"] for item in observed_support],
        locators=locator_records, entity_ids=observed_entity_ids,
        expected_entity_id=expected_entity or None)
    independence_ok = bool(evaluated) and not semantic_errors
    checks["verifier_independence"] = _check(
        "passed" if independence_ok else "failed",
        "at least one semantic judgment is independent of the generation call"
        if independence_ok else "the generation Agent/call is the only semantic judge",
        evidence_ids=[item["source"]["citation"]["id"] for item in evaluated],
        locators=locator_records,
        independent_verifiers=sorted({item["evaluator_id"] for item in evaluated}),
        evaluator_mode=evaluator_mode, errors=semantic_errors)

    semantic_values = [item["result"].decision for item in observed_support]
    if "contradicted" in semantic_values:
        semantic_status, semantic_decision = "failed", "contradicted"
    elif semantic_values and all(value == "supported" for value in semantic_values):
        semantic_status, semantic_decision = "passed", "supported"
    elif "partial" in semantic_values or ("supported" in semantic_values and
                                           "unknown" in semantic_values):
        semantic_status, semantic_decision = "partial", "partial"
    else:
        semantic_status, semantic_decision = "unknown", "unknown"
    semantic_reasons = "; ".join(item["result"].reason for item in observed_support
                                 if item["result"].reason)
    if semantic_errors:
        semantic_reasons = "; ".join(semantic_errors)
    if not semantic_reasons:
        semantic_reasons = (
            "independent located content supports the assertion"
            if semantic_decision == "supported" else
            "no independent semantic decision fully supports the assertion")
    checks["semantic_support"] = _check(
        semantic_status,
        semantic_reasons,
        evidence_ids=[item["source"]["citation"]["id"] for item in observed_support],
        locators=locator_records, decision=semantic_decision,
        retryable=evaluator_mode in {"not_configured", "failed"})

    conversions: list[dict] = []
    declared_type = _normalized_type(str(row["assertion_type"] or ""))
    evaluator_type_values = [
        _normalized_type(item["result"].assertion_type)
        for item in observed_support]
    independent_assertion_types = sorted({
        value for value in evaluator_type_values if value})
    canonical_numeric_types = {declared_type, *independent_assertion_types} - {""}
    numeric_claim, numeric_schema_reason = _structured_numeric_claim(
        atomic, canonical_numeric_types)
    if numeric_claim is None:
        numeric_ok = True
        numeric_status = "not_applicable"
        numeric_reason = "assertion has no numeric value"
    elif not numeric_claim:
        numeric_ok = False
        numeric_status = "failed"
        numeric_reason = numeric_schema_reason
    else:
        numeric_ok = True
        numeric_reason = "all numeric observations match the atomic assertion"
        benchmark_items = [{**item, "probe": item.get("observed_probe", item["probe"])}
                           for item in fetched if item["role"] == "conversion_benchmark"]
        for evaluated_item in observed_support:
            item = evaluated_item["source"]
            observations = item["observed_probe"].numeric_observations
            if not observations:
                numeric_ok = False
                numeric_reason = "supporting evidence lacks a structured numeric observation"
                break
            matched = False
            last_conversion = None
            last_reason = "no numeric observation matches"
            for observation in observations:
                matched, last_reason, conversion = _numeric_match(
                    numeric_claim, observation, benchmark_items)
                last_conversion = conversion
                if matched:
                    if conversion:
                        conversions.append(conversion)
                    break
            if not matched:
                if last_conversion:
                    conversions.append(last_conversion)
                numeric_ok = False
                numeric_reason = last_reason
                break
        numeric_status = "passed" if numeric_ok and observed_support else "failed"
    checks["numeric_consistency"] = _check(
        numeric_status, numeric_reason,
        evidence_ids=[item["source"]["citation"]["id"] for item in observed_support],
        locators=locator_records, conversions=conversions)

    type_signals = _type_signals(atomic, row["assertion_text"])
    predicate_type = _normalized_type(str(atomic.get("predicate") or ""))
    inferred_type = predicate_type or next(iter(sorted(type_signals)), "")
    evaluator_type_complete = (
        bool(observed_support) and
        len(evaluator_type_values) == len(observed_support) and
        all(evaluator_type_values) and
        len(independent_assertion_types) == 1)
    inconsistent_signals = sorted(
        signal for signal in type_signals if signal != declared_type)
    if (evaluator_type_complete and
            independent_assertion_types[0] != declared_type):
        inconsistent_signals.append(independent_assertion_types[0])
        inconsistent_signals = sorted(set(inconsistent_signals))
    classification_ok = (bool(declared_type) and evaluator_type_complete and
                         not inconsistent_signals)
    checks["type_classification"] = _check(
        "passed" if classification_ok else "failed",
        "declared assertion type is controlled and consistent" if classification_ok else
        "assertion type is missing, divergent, or inconsistent across Agent, text, and evaluator",
        evidence_ids=evidence_ids, locators=locator_records,
        declared_type=declared_type or None, inferred_type=inferred_type or None,
        signals=sorted(type_signals), inconsistent_signals=inconsistent_signals)
    checks["type_classification"]["independent_assertion_types"] = \
        independent_assertion_types
    assertion_type = declared_type
    high_risk_signals = sorted(type_signals & {"causal", "forecast",
                                               "investment_judgment", "opinion"})
    type_allowed = (classification_ok and assertion_type not in _JUDGMENT_TYPES and
                    not high_risk_signals)
    checks["type_policy"] = _check(
        "passed" if type_allowed else "failed",
        "assertion type may be evaluated for fact promotion" if type_allowed
        else "causal, forecast, investment, and opinion judgments are never auto-promoted",
        evidence_ids=evidence_ids, locators=locator_records,
        assertion_type=assertion_type, high_risk_signals=high_risk_signals)

    eligible = []
    for item in observed_support:
        source = item["source"]
        if (item["result"].decision != "supported" or
                not source["probe"].reachable or not source["locator_ok"] or
                source["profile"]["verification_status"] != "verified" or
                not _valid_publication_time(source["probe"].published_at)):
            continue
        eligible_item = {
            **source, "probe": source.get("observed_probe", source["probe"])}
        eligible_item["direct_party_match"] = _audited_direct_party_matches(
            repo, context["industry_id"], atomic, eligible_item)
        eligible.append(eligible_item)
    corroborated, corroboration_reason, clusters = _corroboration(
        assertion_type, eligible,
        expected_period=str((numeric_claim or {}).get("period") or
                            atomic.get("period") or atomic.get("time") or ""))
    checks["corroboration"] = _check(
        "passed" if corroborated else "failed", corroboration_reason,
        evidence_ids=[item["citation"]["id"] for item in eligible],
        locators=locator_records, independent_clusters=clusters)

    projection = _claim_projection(repo, context, atomic) if atomization_ok else {
        "subject_id": None, "predicate": "agent_assertion", "object": None,
        "qualifiers": {}, "valid_from": "", "valid_to": "",
    }
    conflicts = (_conflicting_claims(repo, context, projection)
                 if atomization_ok and projection["subject_id"] else [])
    conflict_status = "failed" if conflicts else (
        "unknown" if atomization_ok and not projection["subject_id"] else "passed")
    checks["conflict"] = _check(
        conflict_status,
        "existing accepted claims contradict this assertion" if conflicts
        else ("canonical subject_id is required for conflict-safe promotion"
              if conflict_status == "unknown"
              else "no conflicting accepted claim was found in the same scope"),
        evidence_ids=evidence_ids, locators=locator_records,
        conflicting_claim_ids=conflicts)

    raw_evidence = [{
        "citation_id": item["citation"]["id"],
        "url": canonical_url(item["probe"].final_url),
        "content_hash": item["probe"].content_hash,
        "content": item["probe"].content,
        "role": item["role"],
        "published_at": item["probe"].published_at,
        "excerpt": item["probe"].located_text,
        "publisher_cluster": item["profile"]["owner_cluster"],
        "relation": ("supports" if item["role"] == "support" and
                     any(result["source"] is item and
                         result["result"].decision == "supported"
                         for result in evaluated) else "qualifies"),
        "locator": item["probe"].locator,
        "reachable": item["probe"].reachable,
    } for item in fetched if item["locator_ok"]]
    public_evidence = [{key: value for key, value in item.items() if key != "content"}
                       for item in raw_evidence]
    checks["fact_projection"] = _check(
        "passed" if atomization_ok else "failed",
        "verified claim and evidence projection is ready" if atomization_ok
        else "an atomic claim projection cannot be built",
        evidence_ids=evidence_ids, locators=locator_records,
        claim=projection,
        evidence=public_evidence)

    # Locator excerpts are canonical in the two locator/semantic gates and the
    # fact projection.  Avoid multiplying the same text through every check.
    for name, check in checks.items():
        if name not in {"locator_integrity", "semantic_support", "fact_projection"}:
            check["locators"] = []
    stored_size = _verification_bytes(checks)
    if stored_size > MAX_STORED_VERIFICATION_BYTES:
        checks = _compact_oversized_checks(checks, stored_size)
        budget_error = checks["resource_budget"]["reason"]

    if conflicts or semantic_decision == "contradicted":
        disposition: Disposition = "disputed"
    elif any(check.get("status") not in _PASSING for check in checks.values()):
        disposition = "candidate"
    else:
        disposition = "accepted"
    if evaluator_mode in {"not_configured", "failed"}:
        return VerificationDecision(disposition, checks, None)
    stored = repo._apply_assertion_verification_from_verifier(
        folder, assertion_id, checks=checks, disposition=disposition,
        raw_evidence=(raw_evidence if not budget_error else []))
    return VerificationDecision(
        stored["status"], stored["verification"], stored["claim_id"])
