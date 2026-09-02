# Data Deduplication and Source Governance

## Objective

IntDog treats “whether two documents are duplicates” separately from “whether a source deserves continuous monitoring.” It preserves an auditable source catalog and corroboration from independent publishers while reducing repeated collection, syndicated copies, and active sources that add no coverage.

## Document Deduplication Contract

Deduplication runs in this order:

1. Equal canonical URLs identify the same document.
2. Equal content fingerprints identify the same document after title and abstract normalization; URLs are excluded from the fingerprint.
3. Highly similar titles from the same publisher in a nearby time window identify an update or repeated collection.
4. Similar titles from independent publishers remain separate documents for credibility corroboration.
5. Similar Chinese and English events are not removed by text similarity alone. They may be grouped at the Story layer only when canonical entities, event keys, and time windows agree.

Every merge keeps the richer title, abstract, authors, and timestamps, and records absorbed copies in `duplicate_urls`, `duplicate_count`, and `dedup_reason`. Historical cross-day duplicate associations are soft-deleted; `documents`, Stories, and evidence records are not deleted.

## Source Governance Contract

The source catalog may be larger than the automatic monitoring portfolio. Status semantics are:

- `active`: eligible for automatic collection.
- `recommended_manual`: authoritative but requires manual reading because of a paywall, login, anti-bot protection, or missing stable interface.
- `reserve`: valid but redundant with a stronger source or currently adds no regional, value-chain, topical, or publisher coverage.
- `quarantined`: invalid URL, conflicting publisher identity, or another high-risk condition; excluded from automatic collection.

The system neither lowers the admission bar to meet a count nor deletes valid catalog entries above it. Each of the nine automatic-monitoring categories has a minimum coverage target of eight and a target and hard cap of ten. A shortage remains explicit; additional valid sources stay available as manual recommendations or reserve entries. China-native sources receive coverage priority without a hard ratio; geography never overrides authority and verifiability.

## Ranking and Stop Conditions

Candidates receive an auditable score from code-verified publisher trust, primary or authoritative tier, RSS/API accessibility, coverage gain, China-native coverage, and manual addition history. By default, only one core endpoint per publisher may occupy a category; an additional endpoint is allowed only for distinct topical coverage.

Portfolio growth stops at ten active sources, when every remaining candidate adds no topic, region, publisher, or automated-access coverage, or when the search budget is exhausted. If eight cannot be reached, governance reports the gap and never promotes low-quality candidates merely to reach a number.

## Acceptance and Risk Coverage

Verification must cover these high-risk boundaries: tracking URLs, identical content on different URLs, near-identical titles from one publisher, equal titles from independent publishers, cross-language events, cross-day replay, multiple endpoints from one publisher, preservation of manual sources, exclusion of reserve sources from collection, idempotent reruns, and explicit shortages. Tests establish these contractual cases; they do not claim completeness for duplicate detection on the open web.
