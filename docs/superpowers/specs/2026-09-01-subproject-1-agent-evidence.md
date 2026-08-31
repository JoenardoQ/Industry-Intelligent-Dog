# Subproject 1: Authoritative Contract and Agent Evidence Loop Specification

Status: Approved, awaiting implementation verification
Parent specification: `2026-09-01-complete-local-first-product-design.md`

## Objective

Upgrade the current Agent task export and JSON import into a readable, auditable evidence loop that cannot skip levels, and eliminate the Agent Bridge’s undeclared response Schema, insufficient review information, and scattered file indexes.

## Scope

- Define complete Pydantic/OpenAPI Schemas for Agent Profiles, task packages, result lists, result details, reviews, and verification responses.
- Establish an extensible capability Manifest and local secure discovery: only verified CLI/API integrations may execute directly; other Agents use MCP, task packages, or restricted custom CLI; “discovered” does not mean “directly controllable.”
- Continue treating original import files as immutable audit artifacts; SQLite stores indexes, assertions, citations, review status, and verification status.
- Users inspect assertions and citations one by one and choose `rejected`, `opinion`, or `submitted_for_verification`.
- The verifier checks citation reachability, publisher identity, time validity, entity alignment, conflicts with existing facts, semantic support from citation content, evidence location, numeric/unit/currency/period consistency, and the independent corroboration required by the assertion type.
- Only atomic assertions that pass all applicable gates may promote the existing `claims.status` to `accepted`; when reproducible evidence location is missing, semantics are only partially supported, numeric qualifiers are inconsistent, or corroboration is insufficient, the assertion must remain `candidate`, and explicit contradictions enter `disputed` or `rejected`.

## Data Model

Schema 14 adds:

- `agent_results`: result ID, industry, task, Agent, original file, content hash, status, and creation time.
- `agent_assertions`: assertion text, type, status, associated claim, and verification summary.
- `agent_citations`: canonical URL, reachability, Source/Document associations, and verification time.
- `agent_result_reviews`: action, operator, explanation, and time.

Import and human-review-layer state transitions are:

`draft_review_required → rejected / opinion / submitted_for_verification → candidate / disputed / accepted`

Direct transitions from `draft_review_required` or `opinion` to `accepted` are prohibited. Repeated imports are idempotent by content hash and preserve existing review status.

The parent specification’s `raw → candidate → corroborated / disputed / rejected → accepted` describes the evidence/fact layer; the states here describe the Agent import and human-review layer. Only after verification may `submitted_for_verification` map to `candidate`, `disputed`, `rejected`, or `accepted` in the evidence layer; the two layers must not be mixed.

## Assertion-Level Evidence Sufficiency

Each assertion is first split into an atomic statement with an explicit subject, predicate, object, time, region, value, and qualifiers. Every support item must preserve a reproducible locator: the document content hash, plus one of an HTML selector/text offset, PDF page/table cell, or structured API field path; storing only a URL does not constitute supporting evidence.

The semantic decision outputs `supported / partial / contradicted / unknown` and records supporting excerpts, locators, and the reason. `partial` or `unknown` cannot enter accepted. The same Agent or the same model call that generated an assertion and scores itself cannot be the sole verification basis.

Numeric assertions must match value, sign, unit, currency, order of magnitude, statistical definition, and period item by item. When conversion is allowed, preserve the original value, target value, conversion formula, exchange rate/benchmark source, and tolerance; when the tolerance cannot be determined, default to zero and keep the assertion candidate.

Corroboration strategy is determined by assertion type:

- Identity, regulatory status, and formal company disclosures: one verified and applicable official primary record may suffice;
- Events, transactions, and value-chain relationships: one direct first-party disclosure by an involved party, or a cluster of two ownership-independent qualified publishers;
- Market size, share, valuation, and unofficial statistics: at least two ownership-independent sources, preserving differences in statistical definitions;
- Financial figures: regulatory filings/audited statements for the applicable period take priority; secondary sources require additional independent corroboration;
- Technical performance: a standard, official specification, or locatable academic-paper result, preserving experimental conditions; generalizing beyond the original text cannot be accepted;
- Causal inferences, forecasts, investment judgments, and opinions: do not automatically promote to facts; retain only as opinion/candidate unless decomposed observable subclaims separately pass their type gates.

## API

- `GET /api/agent-bridge/profiles`
- `POST /api/agent-bridge/profiles`
- `DELETE /api/agent-bridge/profiles/{profile_id}`
- `GET /api/industries/{folder}/agent-bridge/tasks`
- `GET /api/industries/{folder}/agent-bridge/tasks/{task_id}`
- `GET /api/industries/{folder}/agent-bridge/results`
- `GET /api/industries/{folder}/agent-bridge/results/{result_id}`
- `POST /api/industries/{folder}/agent-bridge/results`
- `POST /api/industries/{folder}/agent-bridge/results/{result_id}/review`
- `POST /api/industries/{folder}/agent-bridge/results/{result_id}/verify`
- `GET /api/agent-bridge/capabilities`
- `POST /api/agent-bridge/discover`
- `POST /api/agent-bridge/profiles/{profile_id}/diagnose`

Every response must have a `response_model`; paginated lists are limited to 1–100 items. The total number of Profiles is limited to 100 and files to 256 KiB; results are limited to 500 KiB; corrupted or oversized files must fail safely.

## UI

The research assistant displays a dedicated review area: result summary, Agent, task, import time, status, each assertion, and clickable citations. Actions must display semantically clear “Reject,” “Retain as opinion,” and “Submit for verification”; verification results display every gate and its failure reason.

## Security and Migration

- Imports accept only known industries and tasks; reject absolute paths, traversal, privilege escalation through unknown fields, and assertions without HTTP(S) citations.
- Original imports are written atomically to the industry directory; database indexes and audit records are completed in a transaction.
- Schema 14 migration only adds tables; existing JSON results are indexed idempotently on first read, without rewriting the original files.
- Verification must not accept an assertion because a single URL timed out, nor treat an Agent-reported source tier as a trusted identity.
- Automatic discovery checks only PATH, explicit application identifiers, and user-selected executables; it does not traverse user documents or read credential contents. Commands use an argv allowlist, version probing, timeouts, and output limits, without a shell.

## Acceptance

- OpenAPI no longer returns anonymous `{}` for Agent Bridge.
- The UI can inspect assertions and citations and execute the three review actions.
- The state machine rejects all illegal level skips and duplicate side effects.
- Repeated imports do not erase review status or duplicate audit records.
- Fact statistics change only after assertion-level semantic support, location, numeric consistency, and typed corroboration all pass.
- Agents such as Codex and Claude with stable secure CLIs may be diagnosed through native adapters; DeepSeek/Qwen and other compatible APIs, MCP/task-package Agents, and other unknown Agents enter through the capability Manifest, and the UI does not overstate direct-execution capability.
- Test IDs, oracles, priorities, platforms, and open gaps for requirements `AG-01` through `AG-08` are recorded in the bilingual requirements–test traceability matrix.
