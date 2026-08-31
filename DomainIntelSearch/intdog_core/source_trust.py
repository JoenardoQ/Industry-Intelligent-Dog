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
