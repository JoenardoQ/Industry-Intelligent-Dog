# GitHub landscape: crawlers, intelligence workbenches, and knowledge systems

Checked: 2026-08-31. This is a product/architecture survey, not approval to copy,
install, or invoke any project.

## Executive finding

The closest product analogue is **Taranis AI**, not WorldMonitor. Taranis models the
full analyst pipeline—collect, enrich, review, produce, publish—and already separates
API, workers, job queue, SSE, health, and UI. WorldMonitor remains the strongest
reference for real-time monitoring UX and graceful degradation. Folo/RSSHub best
represent source subscription and reading; OpenCTI best represents evidence-aware
graphs; Onyx/RAGFlow best represent research over indexed documents.

No single project covers IntDog's cross-industry ontology, value chains, company
coverage, longitudinal monitoring, learning paths, and investment/research outputs.
The right lesson is to combine proven patterns behind IntDog-owned contracts, not
to fork one product wholesale.

## 1. Collection and crawling

| Project | License | Strength | Relevance / concern |
| --- | --- | --- | --- |
| [Crawlee Python](https://github.com/apify/crawlee-python) | Apache-2.0 | reliable queues, HTTP/browser crawlers, sessions, retries, proxy rotation, request lifecycle | best candidate for difficult dynamic sites; larger dependency footprint than feed/HTTP collectors |
| [Scrapy](https://github.com/scrapy/scrapy) | BSD-3-Clause | mature Python crawling framework, middleware, throttling, pipelines, broad operational history | strongest conservative crawler foundation; browser-heavy pages need an integration |
| [Trafilatura](https://github.com/adbar/trafilatura) | Apache-2.0 for current versions | precise article text/metadata extraction, feed/sitemap discovery, URL filtering and deduplication | best focused replacement/addition for article extraction after retrieval |
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io) | Apache-2.0 | durable page-change monitoring, notifications, selectors, history | useful pattern for non-feed official/company pages and “last changed” semantics |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Apache-2.0 with stated attribution requirement | browser pool, clean Markdown, structured extraction, local non-LLM modes | not a default server dependency: its GitHub security page lists multiple critical/high 2026 advisories; any future use needs a pinned patched library version and isolated threat model |
| [Firecrawl](https://github.com/mendableai/firecrawl) | AGPL-3.0 platform; some SDKs MIT | polished search/scrape/crawl/parse API | useful API-contract reference, but license and self-hosted operational weight argue against incorporating platform code |
| [RSSHub](https://github.com/DIYgod/RSSHub) | AGPL-3.0 | enormous route ecosystem for sites without native feeds | potentially useful as a separately operated source service; do not copy routes/code into MIT IntDog without license review |

Collection conclusion: feeds and official APIs remain first choice. Use an escalation
ladder—HTTP/feed → Trafilatura → browser crawler—rather than sending every URL
through Chromium. Each source adapter must expose robots/access policy, fetch time,
canonical URL, publisher identity, content hash, and failure reason.

## 2. Intelligence and research workbenches

| Project | License | What to study | Gap versus IntDog |
| --- | --- | --- | --- |
| [Taranis AI](https://github.com/taranis-ai/taranis-ai) | EUPL-1.2 | collectors/bots/presenters/publishers; analyst review; RQ workers; SSE; OpenAPI; liveness vs dependency health; SQLite/Postgres modes | security/OSINT framing and heavier service topology; license needs review before code reuse |
| [WorldMonitor](https://github.com/koala73/worldmonitor) | AGPL-3.0 | signal-dense dashboard, adaptive refresh, request coalescing, stale-on-error, circuit breakers, source convergence, visible degradation | map/geopolitics/event-first model is not an industry knowledge model |
| [OpenCTI](https://github.com/OpenCTI-Platform/opencti) | Apache-2.0 CE | source-linked entities/relations, confidence, first/last seen, connector lifecycle, analyst graph navigation | STIX/cyber ontology and enterprise deployment are too specialized/heavy as a base |
| [MISP](https://github.com/MISP/MISP) | AGPL-3.0 | taxonomies, event/object exchange, analyst sharing and enrichment modules | cyber indicator model and copyleft make it a reference, not a base |
| [IntelOwl](https://github.com/intelowlproject/IntelOwl) | AGPL-3.0 | parallel analyzers, task visibility, enrichment APIs and investigation workflow | observable/malware focus; operationally larger than IntDog needs |
| [Yeti](https://github.com/yeti-platform/yeti) | Apache-2.0 | extensible feeds, enrichment, timelines, user-defined exports | cyber/DFIR specialization; still useful for plugin contracts |
| [Folo](https://github.com/RSSNext/Folo) | AGPL-3.0 plus asset exception | modern reading queue, subscriptions/lists, mixed media, AI summary/translation, cross-platform UX | reader rather than evidence/industry research system; assets have extra restrictions |
| [Onyx CE](https://github.com/onyx-dot-app/onyx) | MIT core CE | connector sync, hybrid retrieval, deep research, artifacts, provider support, lite/full deployment split | enterprise-search/chat is only one IntDog subsystem; standard deployment brings workers, Redis and object storage |
| [RAGFlow](https://github.com/infiniflow/ragflow) | Apache-2.0 | document parsing, ingestion pipeline, chunking, retrieval and agent workflow UX | RAG context engine is not a factual temporal industry database; infrastructure is heavy |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | MIT core | local-first workspace/document/agent experience, provider abstraction, air-gap mode | chat-centric and lacks monitoring, source governance, entity resolution and industry-chain coverage |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | AGPL-3.0 platform | provider/fetcher abstractions and consistent financial response metadata | finance-specific; best considered as an optional provider/service |
| [Aleph](https://github.com/alephdata/aleph) | MIT core | document/entity search and cross-referencing for investigations | upstream maintenance ended after 2025; study its ontology, do not adopt the platform |

## 3. Knowledge-domain and entity systems

| Project / dataset | License/status | What to study | Caveat |
| --- | --- | --- | --- |
| [FollowTheMoney](https://github.com/alephdata/followthemoney) | MIT | pragmatic company/person/asset/ownership ontology and typed entity properties | investigative-finance bias; industry products, technologies, facilities and value-chain roles need IntDog extensions |
| [OpenSanctions](https://github.com/opensanctions/opensanctions) | MIT code; data has separate non-commercial terms | source-specific parsers, normalization, statement lineage, deduplication/entity resolution, multiple exports | code and data licenses differ; never treat open code as permission to redistribute its data |
| [OpenAlex](https://github.com/ourresearch/openalex-docs) | CC0 dataset; service terms/limits apply | scholarly entities—works, authors, institutions, topics, publishers, funders—and a massive directed graph | external scholarly source, not IntDog's entire ontology; API access rules have changed over time and must be checked at execution |
| [Graphiti](https://github.com/getzep/graphiti) | Apache-2.0 | temporal episodes, time-aware entity/relationship updates and retrieval | requires graph database and model calls; useful methods, premature dependency for a local single-user app |
| [Microsoft GraphRAG](https://github.com/microsoft/graphrag) | MIT, maintenance mode | hierarchical community summaries and graph-guided retrieval methodology | explicitly a research project, expensive indexing, no longer a fast-moving foundation |
| [TypeDB CE](https://github.com/typedb/typedb) | MPL-2.0 | strongly typed entity/relation/attribute schema, inference and visual studio | separate server/toolchain and schema language; only justified if relational constraints become a measured blocker |
| [TerminusDB](https://github.com/terminusdb/terminusdb) | Apache-2.0 | versioned collaborative document graph and GraphQL/JSON-LD interfaces | another server and data paradigm; attractive versioning does not yet justify migration |
| [Kuzu](https://github.com/kuzudb/kuzu) | MIT, archived Oct 2025 | embedded property-graph ideas, Cypher, FTS/vector integration | archived project is not acceptable for a new core dependency |

## 4. Emerging near-neighbours

These projects are directionally relevant but too young or insufficiently proven to
be foundations: Lynx (multi-agent company research), IntellyWeave (OSINT graphs and
agents), Beehive (personal news ranking/digests), IntelFlow (bilingual daily
intelligence pipeline), and smaller “control center” dashboards. Their README ideas
can inspire tests; their claims are not production evidence.

## 5. Shortlist for deeper source-code study

Priority A:

1. **Taranis AI** — end-to-end collection-to-publication workflow and operations.
2. **WorldMonitor** — real-time workbench behavior, caching, degradation and signal UX.
3. **OpenCTI** — temporal, evidence-bearing graph and analyst interactions.
4. **Folo + RSSHub** — source discovery, subscription, reading and Chinese/international feeds.
5. **Onyx or RAGFlow** — research assistant ingestion/retrieval/artifact lifecycle.

Priority B building blocks:

1. **Scrapy/Crawlee + Trafilatura** — layered retrieval and extraction.
2. **changedetection.io** — non-feed monitoring and change history.
3. **FollowTheMoney/OpenSanctions** — entity normalization, provenance and resolution.
4. **OpenAlex** — academic knowledge coverage.
5. **Graphiti/GraphRAG** — temporal graph and graph-retrieval methods only.

## 6. Immediate architectural implications

- IntDog needs a **collector plugin contract**, not one universal crawler.
- It needs a visible **analyst pipeline**: collected → normalized → corroborated →
  reviewed → published, rather than treating every generated report as finished.
- Sources, documents, claims, entities, relationships and generated products need
  separate lifecycles and explicit lineage.
- Tasks must be observable through persisted states plus streamed representative
  events; `/alive` and `/health` are distinct concepts.
- Research chat/RAG is a consumer of the industry knowledge system, not its source of
  truth.
- Copyleft projects can be studied and may be operated as clearly separated services
  after review, but IntDog should prefer permissive components for direct integration.
