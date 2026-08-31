# `worldmonitor` method notes for future IntDog UI and algorithm rounds

Reference: [koala73/worldmonitor](https://github.com/koala73/worldmonitor)

Inspected revision: `648db7f049fe53d8152b482fa96d09ce2aa00d93`

License at inspected revision: AGPL-3.0-only

Use decision: methodological reference only. IntDog will not install, execute,
vendor, depend on, or copy World Monitor code, assets, layouts, or formulas.

## Transferable UI ideas

1. **Build an operational picture, not a page collection.** A compact overview
   should connect headline developments, industry-chain nodes, companies,
   research, policy, markets, and collection health. Selecting a signal should
   reveal its evidence and related objects instead of opening an isolated
   decorative card.
2. **Use a stable workbench shell with modular surfaces.** A registry-backed
   route/panel catalog, consistent headers, shared filters, and persisted user
   choices scale better than page-specific navigation and styling. IntDog's
   approved sidebar and route model remain authoritative; this principle only
   strengthens their implementation.
3. **Prefer progressive disclosure.** The first screen should show status,
   significance, freshness, and next action. Details, raw evidence, alternate
   sources, and provenance belong in an inspectable secondary layer. Dense does
   not mean crowded: visual hierarchy, whitespace, and restrained color carry
   more information than permanent borders around every region.
4. **Synchronize related views.** For IntDog, the useful analogue of a
   map/panel link is a chain graph, timeline, ranked evidence list, and detail
   inspector sharing one selection. Clicking a chain node should filter its
   companies, technologies, documents, risks, and gaps; clicking a story should
   highlight affected nodes and entities.
5. **Expose operational truth in the product.** Each collection surface should
   show last successful content time, last attempt, coverage, failures, and
   whether displayed content is live, partial, stale, or last-known-good. A
   successful request with empty or old content is not healthy data.
6. **Make credibility visible but multidimensional.** Show publisher identity,
   source tier, first-party/secondary status, state or commercial affiliation,
   access limitations, independent corroboration, and content time separately.
   Do not collapse newsworthiness and reliability into one unexplained score.
7. **Use status color sparingly.** A low-saturation workbench can reserve strong
   color for severity, freshness degradation, selection, and destructive
   actions. Ordinary structure should rely on spacing, typography, and tonal
   surfaces. This is compatible with the already approved native Tk/ttk design.
8. **Keep expensive views incremental.** Lazy-create heavy research views,
   pause refreshes when hidden, back off after failures, and hydrate large data
   only when its route is opened. The UI must remain usable while enrichment or
   model-based classification arrives later.

## Transferable algorithm and data ideas

1. **Separate transport health, content health, coverage, and confidence.** A
   fresh heartbeat does not prove fresh or sufficient evidence. Track last
   attempt and last accepted content independently, validate domain-specific
   minimum coverage, and represent unavailable/partial/stale states explicitly
   rather than converting missingness to zero.
2. **Retain last-known-good data under a stricter admission rule.** Partial live
   results may be displayed without replacing a wider valid fallback. Any
   retained snapshot needs scope identity, coverage metadata, timestamps, and
   compare-and-swap semantics so concurrent weak runs cannot overwrite stronger
   evidence.
3. **Fuse heterogeneous signals only after normalization.** Normalize news,
   filings, papers, policies, company events, market observations, and chain
   evidence into attributable observations before correlation. Preserve each
   signal's source, event time, observation time, type, confidence, and expiry.
4. **Use recency decay and domain TTLs.** Volatile signals should lose effective
   weight as they age; structural facts should have longer review horizons.
   IntDog should not reuse one freshness threshold for an RSS item, annual
   filing, policy document, market quote, and company master record.
5. **Cluster before summarizing or alerting.** Use deterministic textual
   similarity first, semantic similarity only as a refinement, and measure
   convergence by independent publishers. Cluster velocity should count source
   diversity and time, not raw duplicates or syndicated copies.
6. **Correlate across evidence families.** A higher-priority signal is one that
   connects independently observed dimensions—for example a policy release,
   company filing, hiring change, paper, and affected chain node—not merely one
   that repeats across many news sites. Preserve the correlation evidence for
   inspection.
7. **Layer cheap deterministic classification with later refinement.** Render
   transparent rules immediately; refine asynchronously with local models or an
   LLM only when the refinement has higher supported confidence. Every result
   must retain its classifier origin, and model failure must not block the UI.
8. **Gate alerts by recency, credibility, corroboration, and cooldown.** A low-
   tier or self-media lead can enter the evidence inbox, but should require
   stronger independent confirmation before becoming an alert or investment
   conclusion. Deduplicate per event and prevent startup replay of stale items.
9. **Treat source balance as coverage contracts, not a cosmetic ratio.** China
   and foreign lanes should each have explicit primary, official, specialist,
   academic, financial, news, and self-media coverage. Curated presets may add
   sources without silently disabling user choices; state-affiliated and
   partisan sources remain useful but visibly attributed and never promoted by
   origin alone.
10. **Make registries the source of truth.** Industry routes, source classes,
    chain-node types, collectors, health contracts, and report products should
    be enumerable. New members must be classified or deliberately excluded so
    coverage checks cannot pass on an accidentally empty inventory.

## IntDog adaptation targets

| Current measured IntDog gap | Candidate method to evaluate |
| --- | --- |
| China-origin documents 2 vs foreign 66 | source-family coverage contracts, China-specific lanes, visible access/freshness status, and additive source presets |
| 0 of 66 claims independently corroborated | story clusters, publisher independence, cross-family convergence, and alert confidence gates |
| 14 chain nodes have `evidence_count=0` | synchronized chain/timeline/evidence selection and normalized observations linked to canonical nodes |
| Failed feeds and only 33/59 reachable sources | separate attempt/content/coverage health, adaptive retry, and last-known-good retention |
| Entity audit 27 vs 41 active entities | registry-backed entity aliases plus explicit coverage gaps rather than inferred completeness |
| Flat, visually weak desktop UI | professional route shell, restrained surfaces, progressive disclosure, status semantics, and synchronized research views |
| Long model/research operations | immediate deterministic state, asynchronous enrichment, job visibility, cancellation, and explicit partial results |

## Required evaluation before adoption

- Keep the approved professional research workbench information architecture;
  do not imitate World Monitor's visual identity, global map, or web stack.
- Prototype synchronized chain graph, timeline, evidence list, and inspector on
  temporary fixtures. Measure task completion, selection consistency, resize
  behavior, text sharpness, and information density before using production AI
  data for read-only GUI verification.
- Extend the frozen multilingual search benchmark with content freshness,
  independent-publisher convergence, coverage-gap accuracy, alert precision,
  stale-alert rate, and last-known-good admission/replacement cases.
- Add adversarial cases for healthy transport with empty content, stale content
  behind a fresh heartbeat, state-media attribution, syndicated stories,
  duplicate publisher groups, slow collectors, partial runs, and concurrent
  weaker snapshot writes.
- Adopt each UI or algorithm component only when it improves measured IntDog
  outcomes and preserves evidence lineage, draft/review status, explicit
  missingness, user-added sources, and the long-term industry knowledge model.
