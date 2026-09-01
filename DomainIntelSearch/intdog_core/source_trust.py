"""Auditable publisher identity and trust rules shared by storage and verification."""

from __future__ import annotations

from urllib.parse import urlsplit


# Only code-reviewed domains grant authority. Names and model-declared tiers do not.
TRUSTED_DOMAINS = {
    "gov.cn": ("China Government", "official_primary", "china-government", 0.90),
    "samr.gov.cn": ("SAMR", "official_primary", "china-government", 0.90),
    "miit.gov.cn": ("MIIT", "official_primary", "china-government", 0.90),
    "cac.gov.cn": ("CAC", "official_primary", "china-government", 0.90),
    "sec.gov": ("US SEC", "official_primary", "us-government", 0.90),
    "fda.gov": ("US FDA", "official_primary", "us-government", 0.90),
    "europa.eu": ("European Union", "official_primary", "eu-institutions", 0.90),
    "cninfo.com.cn": ("CNInfo", "official_primary", "cninfo", 0.90),
    "hkexnews.hk": ("HKEX News", "official_primary", "hkex", 0.90),
    "who.int": ("WHO", "official_primary", "who", 0.90),
    "clinicaltrials.gov": ("ClinicalTrials.gov", "primary_record", "nih", 0.85),
    "nih.gov": ("NIH", "official_primary", "us-government", 0.90),
    "nist.gov": ("NIST", "official_primary", "us-government", 0.90),
    "arxiv.org": ("arXiv", "primary_record", "arxiv", 0.85),
    "doi.org": ("DOI", "primary_record", "doi", 0.85),
    "github.com": ("GitHub", "primary_record", "github", 0.85),
    "nature.com": ("Nature", "primary_record", "springer-nature", 0.85),
    "science.org": ("Science", "primary_record", "aaas", 0.85),
    "ieee.org": ("IEEE", "primary_record", "ieee", 0.85),
    "acm.org": ("ACM", "primary_record", "acm", 0.85),
    "reuters.com": ("Reuters", "established_media", "reuters", 0.72),
    "reutersagency.com": ("Reuters", "established_media", "reuters", 0.72),
    "bloomberg.com": ("Bloomberg", "established_media", "bloomberg", 0.72),
    "apnews.com": ("Associated Press", "established_media", "ap", 0.72),
    "ft.com": ("Financial Times", "established_media", "ft", 0.72),
    "wsj.com": ("Wall Street Journal", "established_media", "dow-jones", 0.72),
    "caixin.com": ("Caixin", "established_media", "caixin", 0.72),
    "xinhuanet.com": ("Xinhua", "established_media", "xinhua", 0.72),
    "people.com.cn": ("People's Daily", "established_media", "peoples-daily", 0.72),
}
LOW_SIGNAL_DOMAINS = {"producthunt.com", "reddit.com", "medium.com"}


def domain_of(value: str) -> str:
    try:
        return urlsplit(str(value or "")).netloc.casefold().removeprefix("www.")
    except ValueError:
        return ""


def trusted_entry(domain: str):
    domain = str(domain or "").casefold().removeprefix("www.")
    matches = [(key, value) for key, value in TRUSTED_DOMAINS.items()
               if domain == key or domain.endswith("." + key)]
    return max(matches, key=lambda pair: len(pair[0]))[1] if matches else None


def _indexed_publisher(item: dict) -> str:
    """Publisher label supplied by a controlled index adapter, not user claims."""
    if item.get("history_provider") != "google_news_rss":
        return ""
    value = str(item.get("source_domain") or item.get("source") or "")
    return " ".join(value.split()).strip()


def publisher_profile(item: dict) -> dict:
    domain = domain_of(item.get("url", ""))
    indexed = _indexed_publisher(item)
    if indexed:
        return {"name": indexed, "domain": domain,
                "owner_cluster": f"indexed:{indexed.casefold()}",
                "verification_status": "unverified",
                "evidence_type": "secondary_source", "quality": 0.50}
    entry = trusted_entry(domain)
    if entry:
        name, evidence_type, cluster, quality = entry
        return {"name": name, "domain": domain, "owner_cluster": cluster,
                "verification_status": "verified", "evidence_type": evidence_type,
                "quality": quality}
    return {"name": str(item.get("publisher_name") or item.get("name") or domain),
            "domain": domain, "owner_cluster": domain or "unknown",
            "verification_status": "unverified", "evidence_type": "secondary_source",
            "quality": 0.35 if domain in LOW_SIGNAL_DOMAINS else 0.50}


def evidence_publisher_profile(url: str) -> dict:
    """Resolve verification identity from a fetched URL only.

    Agent-supplied publisher names, tiers, indexed-source labels, and ownership
    claims are intentionally excluded from this boundary.
    """
    profile = publisher_profile({"url": str(url or "")})
    parsed = urlsplit(str(url or ""))
    domain = domain_of(url)
    path = parsed.path.casefold()
    authorities: set[str] = set()

    # Authority is granted to a reviewed document class, not to every page on
    # a trusted domain.  These rules are intentionally narrow and local.
    if domain == "sec.gov" or domain.endswith(".sec.gov"):
        authorities.update({"official_identity", "direct_party"})
        if "/archives/edgar/" in path:
            authorities.update({"regulatory_filing", "audited_statement"})
    elif domain in {"cninfo.com.cn", "hkexnews.hk"}:
        authorities.update({"official_identity", "direct_party",
                            "regulatory_filing", "audited_statement"})
    elif profile["evidence_type"] == "official_primary":
        authorities.update({"official_identity", "direct_party"})

    if domain == "nist.gov" or domain.endswith(".nist.gov"):
        if any(marker in path for marker in
               ("/publications/", "/standards/", "/standard/", "/specifications/")):
            authorities.update({"standard", "official_spec"})
    if domain in {"nature.com", "science.org", "ieee.org", "acm.org",
                  "arxiv.org", "doi.org"}:
        authorities.add("academic_result")

    return {**profile, "authorities": sorted(authorities)}


def publisher_key(item: dict) -> str:
    indexed = _indexed_publisher(item)
    if indexed:
        return f"indexed:{indexed.casefold()}"
    original = (item.get("original_publisher_url") or item.get("syndicated_from") or
                item.get("original_url"))
    domain = domain_of(original) if original else domain_of(item.get("url", ""))
    entry = trusted_entry(domain)
    return entry[2] if entry else (domain or str(item.get("source") or "unknown").casefold())


def source_assessment(item: dict) -> tuple[float, str]:
    profile = publisher_profile(item)
    return float(profile["quality"]), str(profile["evidence_type"])


def _review_record(item: dict, key: str) -> dict:
    value = item.get(key)
    return value if isinstance(value, dict) else {}


def _has_evidence_url(record: dict) -> bool:
    return bool(domain_of(record.get("evidence_url", "")))


def source_verification(item: dict) -> dict:
    """Evaluate explicit source-review records without promoting domain hints.

    `TRUSTED_DOMAINS` remains useful for routing and prioritization, but cannot
    itself satisfy identity, ownership, or URL admission gates.
    """
    profile = publisher_profile(item)
    identity = _review_record(item, "identity_verification")
    ownership = _review_record(item, "ownership_verification")
    url_review = _review_record(item, "url_verification")

    identity_passed = (
        str(identity.get("status") or "").casefold() == "verified"
        and _has_evidence_url(identity)
        and bool(str(identity.get("verified_by") or "").strip()))
    owner_cluster = str(ownership.get("owner_cluster") or "").strip().casefold()
    ownership_passed = (
        str(ownership.get("status") or "").casefold() == "verified"
        and bool(owner_cluster) and _has_evidence_url(ownership)
        and bool(str(ownership.get("verified_by") or "").strip()))
    checked_domain = domain_of(url_review.get("checked_url", ""))
    candidate_domain = domain_of(item.get("url", ""))
    try:
        status_code = int(url_review.get("status_code"))
    except (TypeError, ValueError):
        status_code = 0
    url_passed = (
        str(url_review.get("status") or "").casefold() == "verified"
        and url_review.get("reachable") is True
        and 200 <= status_code < 400
        and bool(candidate_domain) and checked_domain == candidate_domain
        and str(url_review.get("verification_origin") or "").casefold()
        == "server_guarded")

    observed_owner = str(item.get("observed_owner_cluster") or "").strip().casefold()
    ownership_changed = bool(
        item.get("ownership_changed") or
        (observed_owner and owner_cluster and observed_owner != owner_cluster))
    return {
        "identity_passed": identity_passed,
        "ownership_passed": ownership_passed,
        "url_passed": url_passed,
        "all_passed": identity_passed and ownership_passed and url_passed,
        "identity_hint": profile["verification_status"] == "verified",
        "hint_evidence_type": profile["evidence_type"],
        "owner_cluster": owner_cluster or profile["owner_cluster"],
        "ownership_changed": ownership_changed,
        "records": {
            "identity": identity,
            "ownership": ownership,
            "url": url_review,
        },
    }
