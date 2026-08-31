# `last30days-skill` method notes for future IntDog algorithm rounds

Reference: [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill)

Inspected revision: `a218edadbc3361672f5e5e2cd72a8212b0b3fbb8`

License at inspected revision: MIT

Use decision: methodological reference only. IntDog will not install, invoke,
vendor, or depend on this skill, and will not copy its implementation wholesale.

## Transferable ideas

1. **Separate entity from intent.** Derive a primary entity and intent modifier
   before expanding queries. Preserve compound phrases and use CJK-aware
   segmentation. A decisive off-entity penalty must have a conservative test so
   false misses degrade toward no penalty rather than burying valid evidence.
2. **Plan before retrieval.** Build intent-aware subqueries and source weights,
   then fan them out across heterogeneous sources. Keep each `(subquery, source)`
   stream and its outcome rather than flattening early.
3. **Normalize with provenance.** Convert source-specific payloads to one
   evidence schema containing native rank, source, query lane, retrieval time,
   publication time, date confidence, engagement, and access/failure state.
4. **Fuse ranks, not incomparable raw scores.** Weighted reciprocal-rank fusion
   is a useful baseline for merging source/query streams. Apply source-diversity
   floors only when a source has sufficiently relevant evidence, plus author or
   publisher caps to prevent domination.
5. **Deduplicate by the right identity.** Canonical URL first; then hybrid
   character-ngram and token Jaccard for text. Identity rules must be source- or
   entity-type aware because shared boilerplate can collapse distinct records.
6. **Cluster stories after retrieval.** Preserve representative diversity and
   independent source clusters. Compute corroboration from publisher/source
   independence rather than raw link count.
7. **Use absolute confidence floors.** A trend or industry claim should clear a
   fixed evidence threshold: independent corroboration or a narrowly defined
   high-quality first-party spike. If nothing qualifies, return an honest
   `nothing solid` result plus the closest weak signal; never rank junk merely
   because the candidate pool is weak.
8. **Make time windows binding.** Hard-filter or visibly demote out-of-window
   evidence. Separate retrieval freshness from claim freshness, and selectively
   refetch volatile facts instead of regenerating an entire report.
9. **Persist resumable research stages safely.** Expensive semantic workflows
   can pause at a versioned checkpoint for the host model to judge. Checkpoints
   need bundle identity, TTL, provenance, store scoping, strict top-level
   validation, fail-closed structural emptiness, and retained degraded-source
   status across resume steps.
10. **Treat scraped text as untrusted input.** Keep evidence inside explicit
    prompt/data fences and structural instructions outside them. Cap host-facing
    digests without truncating the lossless machine resume state.
11. **Keep fuzzy history annotate-only.** For recurring topics, fuzzy matching
    may annotate recurrence but must not merge or overwrite distinct rows.
    Match all candidates before writing any from the same run, and preserve
    user-set covered/reviewed states across naming drift.
12. **Budget the process, not only the answer.** A timeout over non-daemon worker
    threads does not guarantee process exit. Every concurrency design must state
    what happens to a running straggler; abandonment is allowed only for workers
    proven to be write-free.
13. **Evaluate search revisions explicitly.** Compare a fixed multilingual
    topic set with deterministic overlap/retention/source-count metrics and a
    judged pool for `Precision@5`, `nDCG@5`, and source-coverage recall. These
    are regression/evaluation signals, not substitutes for truth.

## IntDog adaptation targets

These ideas become review criteria during the later algorithm/search rounds,
not implementation authorization during the current UI redesign:

| Current measured IntDog gap | Candidate method to evaluate |
| --- | --- |
| China-origin documents 2 vs foreign 66 | language/region-aware query lanes, source floors, and recall metrics without a hard ratio quota |
| 0 of 66 claims independently corroborated | publisher-cluster evidence fusion and an absolute confidence floor |
| 14 of 14 chain nodes have `evidence_count=0` | preserve query/source provenance through normalization and aggregate evidence to canonical chain nodes |
| Two duplicate canonical URLs | canonical URL plus source-aware hybrid similarity and cluster identity tests |
| Three failed feeds and 33/59 reachable sources | per-source outcome taxonomy, degraded coverage propagation, and source-specific fallback lanes |
| Entity audit 27 vs 41 distinct industry entities | conservative entity grounding, alias-aware identity, and non-destructive fuzzy annotation |
| Daily/history/weekly research stages | identity-bound checkpoint/resume with honest partial and corrupt-state handling |

## Required evaluation before adoption

- Establish a frozen multilingual industry-query benchmark spanning Chinese and
  foreign sources, companies, research groups, policies, technologies, and
  upstream/downstream chain nodes.
- Measure baseline and candidate `Precision@k`, `nDCG@k`, source/domain recall,
  China/foreign recall, first-party coverage, corroboration, duplicate rate,
  empty-node evidence coverage, wall-clock time, and source-failure disclosure.
- Add adversarial tests for entity-name collisions, multi-word entities, CJK
  segmentation, tracking-URL aliases, syndicated articles, paywalls/403s,
  old-but-republished content, and same-author domination.
- Adopt components independently only when they improve measured quality and
  preserve IntDog's source-first gates, evidence lineage, draft/review status,
  and long-term industry knowledge model.
