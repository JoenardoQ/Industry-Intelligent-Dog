# Long-duration evidence collection

Long-duration reports are retrieval products before they are writing products.
IntDog must collect evidence across the requested interval, not extrapolate from
the newest daily batch and not pad a quota with duplicates.

## Default targets

| Horizon | Time stratification | Target range | Generation gate |
| --- | --- | ---: | --- |
| weekly | day | 25–50 | at least 75% of target and 80% of day buckets |
| monthly | week | 100–180 | same |
| quarterly | week | 300–500 | same |
| semiannual | week | 600–1,000 | same |
| biennial | week | 2,400–3,200 | same |
| fiveyear | month | 6,000–8,000 | same |

The configured point targets are 28, 120, 360, 720, 2,800 and 7,200. A bucket
has a minimum quota; event-dense buckets may exceed it. Duplicate canonical URLs,
undated records, unreachable records and irrelevant records do not count.

## Sources and admission

- GDELT DOC supplies dated news candidates, with date-qualified Google News RSS as
  a disclosed index fallback; OpenAlex supplies dated scholarly works.
  GDELT is sufficient to fill a bucket when the scholarly provider is unavailable.
  OpenAlex now requires a free `OPENALEX_API_KEY` for production-scale use; anonymous
  responses are treated as best-effort and a 429 is recorded as provider degradation.
- Results retain provider, retrieval time, publication time, publisher and query.
- Records are admitted through the normal daily-document normalization and canonical
  store. A provider response count is never treated as an admitted count.
- `history_manifest.json` records every bucket, errors, saved counts, coverage,
  publisher diversity and resumable completion state.
- China-native authoritative backfill remains a coverage priority, but no fixed
  domestic/foreign ratio is a correctness gate.

## Report consumption

The database retains the full admitted corpus. Model context is a deterministic,
time-stratified sample capped at about 500 records, plus full-corpus statistics and
the manifest. This prevents both recent-item bias and unbounded prompts. Sparse
history blocks long-duration generation unless a caller explicitly chooses a
disclosed sparse draft; the default App never silently bypasses the gate.
