/* Generated from openapi.json. Do not edit by hand. */
export type ApiPath = "/api/agent-bridge/capabilities" | "/api/agent-bridge/discover" | "/api/agent-bridge/profiles" | "/api/agent-bridge/profiles/{profile_id}" | "/api/agent-bridge/profiles/{profile_id}/diagnose" | "/api/agent-bridge/profiles/{profile_id}/probe" | "/api/artifact" | "/api/background" | "/api/background/permissions" | "/api/health" | "/api/industries" | "/api/industries/import" | "/api/industries/{folder}" | "/api/industries/{folder}/agent-bridge/results" | "/api/industries/{folder}/agent-bridge/results/{result_id}" | "/api/industries/{folder}/agent-bridge/results/{result_id}/review" | "/api/industries/{folder}/agent-bridge/results/{result_id}/verify" | "/api/industries/{folder}/agent-bridge/tasks" | "/api/industries/{folder}/agent-bridge/tasks/{task_id}" | "/api/industries/{folder}/automation" | "/api/industries/{folder}/automation/{action}" | "/api/industries/{folder}/automation/{action}/run" | "/api/industries/{folder}/conversation" | "/api/industries/{folder}/conversation/proposals/{proposal_id}/confirm" | "/api/industries/{folder}/conversation/proposals/{proposal_id}/reject" | "/api/industries/{folder}/conversation/turn" | "/api/industries/{folder}/coverage" | "/api/industries/{folder}/coverage-expansions" | "/api/industries/{folder}/coverage-expansions/{round_id}/execute" | "/api/industries/{folder}/coverage-matrix" | "/api/industries/{folder}/coverage-review-queue" | "/api/industries/{folder}/coverage/cells" | "/api/industries/{folder}/coverage/cells/{cell_id}/attempts" | "/api/industries/{folder}/coverage/initialize" | "/api/industries/{folder}/coverage/plan" | "/api/industries/{folder}/daily" | "/api/industries/{folder}/entity-candidates/{candidate_id}/review" | "/api/industries/{folder}/export" | "/api/industries/{folder}/generate" | "/api/industries/{folder}/history" | "/api/industries/{folder}/knowledge/entities" | "/api/industries/{folder}/knowledge/entities/{entity_id}" | "/api/industries/{folder}/overview" | "/api/industries/{folder}/portable/daily" | "/api/industries/{folder}/products" | "/api/industries/{folder}/quality-drift" | "/api/industries/{folder}/relation-candidates/{candidate_id}/review" | "/api/industries/{folder}/research" | "/api/industries/{folder}/settings/{operation}" | "/api/industries/{folder}/source-campaigns" | "/api/industries/{folder}/source-campaigns/{campaign_id}" | "/api/industries/{folder}/source-campaigns/{campaign_id}/execute" | "/api/industries/{folder}/source-candidates/{candidate_id}/review" | "/api/industries/{folder}/sources" | "/api/industries/{folder}/sources/{source_id}/reassess" | "/api/industries/{folder}/stories" | "/api/industries/{folder}/stories-momentum" | "/api/industries/{folder}/stories/{story_id}" | "/api/industries/{folder}/stories/{story_id}/ignore" | "/api/industries/{folder}/stories/{story_id}/merge" | "/api/industries/{folder}/stories/{story_id}/momentum" | "/api/industries/{folder}/stories/{story_id}/split" | "/api/industries/{folder}/stories/{story_id}/unlock" | "/api/jobs" | "/api/jobs/{run_id}/cancel" | "/api/jobs/{run_id}/output" | "/api/jobs/{run_id}/retry" | "/api/settings/effective" | "/api/settings/global/{operation}" | "/api/setup" | "/api/shutdown" | "/api/trash" | "/api/trash/audits/recent" | "/api/trash/{item_id}/preview" | "/api/trash/{item_id}/restore"
export type ApiOperation = "GET /api/agent-bridge/capabilities" | "POST /api/agent-bridge/discover" | "GET /api/agent-bridge/profiles" | "POST /api/agent-bridge/profiles" | "DELETE /api/agent-bridge/profiles/{profile_id}" | "POST /api/agent-bridge/profiles/{profile_id}/diagnose" | "POST /api/agent-bridge/profiles/{profile_id}/probe" | "GET /api/artifact" | "GET /api/background" | "PUT /api/background/permissions" | "GET /api/health" | "GET /api/industries" | "POST /api/industries" | "POST /api/industries/import" | "DELETE /api/industries/{folder}" | "PATCH /api/industries/{folder}" | "GET /api/industries/{folder}/agent-bridge/results" | "POST /api/industries/{folder}/agent-bridge/results" | "GET /api/industries/{folder}/agent-bridge/results/{result_id}" | "POST /api/industries/{folder}/agent-bridge/results/{result_id}/review" | "POST /api/industries/{folder}/agent-bridge/results/{result_id}/verify" | "GET /api/industries/{folder}/agent-bridge/tasks" | "GET /api/industries/{folder}/agent-bridge/tasks/{task_id}" | "GET /api/industries/{folder}/automation" | "PUT /api/industries/{folder}/automation/{action}" | "POST /api/industries/{folder}/automation/{action}/run" | "GET /api/industries/{folder}/conversation" | "POST /api/industries/{folder}/conversation/proposals/{proposal_id}/confirm" | "POST /api/industries/{folder}/conversation/proposals/{proposal_id}/reject" | "POST /api/industries/{folder}/conversation/turn" | "GET /api/industries/{folder}/coverage" | "GET /api/industries/{folder}/coverage-expansions" | "POST /api/industries/{folder}/coverage-expansions" | "POST /api/industries/{folder}/coverage-expansions/{round_id}/execute" | "GET /api/industries/{folder}/coverage-matrix" | "GET /api/industries/{folder}/coverage-review-queue" | "POST /api/industries/{folder}/coverage/cells" | "POST /api/industries/{folder}/coverage/cells/{cell_id}/attempts" | "POST /api/industries/{folder}/coverage/initialize" | "POST /api/industries/{folder}/coverage/plan" | "DELETE /api/industries/{folder}/daily" | "GET /api/industries/{folder}/daily" | "POST /api/industries/{folder}/entity-candidates/{candidate_id}/review" | "GET /api/industries/{folder}/export" | "POST /api/industries/{folder}/generate" | "GET /api/industries/{folder}/history" | "GET /api/industries/{folder}/knowledge/entities" | "GET /api/industries/{folder}/knowledge/entities/{entity_id}" | "GET /api/industries/{folder}/overview" | "POST /api/industries/{folder}/portable/daily" | "GET /api/industries/{folder}/products" | "GET /api/industries/{folder}/quality-drift" | "POST /api/industries/{folder}/relation-candidates/{candidate_id}/review" | "GET /api/industries/{folder}/research" | "DELETE /api/industries/{folder}/settings/{operation}" | "PUT /api/industries/{folder}/settings/{operation}" | "GET /api/industries/{folder}/source-campaigns" | "POST /api/industries/{folder}/source-campaigns" | "GET /api/industries/{folder}/source-campaigns/{campaign_id}" | "POST /api/industries/{folder}/source-campaigns/{campaign_id}/execute" | "POST /api/industries/{folder}/source-candidates/{candidate_id}/review" | "DELETE /api/industries/{folder}/sources" | "GET /api/industries/{folder}/sources" | "POST /api/industries/{folder}/sources" | "POST /api/industries/{folder}/sources/{source_id}/reassess" | "GET /api/industries/{folder}/stories" | "GET /api/industries/{folder}/stories-momentum" | "GET /api/industries/{folder}/stories/{story_id}" | "POST /api/industries/{folder}/stories/{story_id}/ignore" | "POST /api/industries/{folder}/stories/{story_id}/merge" | "GET /api/industries/{folder}/stories/{story_id}/momentum" | "POST /api/industries/{folder}/stories/{story_id}/split" | "POST /api/industries/{folder}/stories/{story_id}/unlock" | "GET /api/jobs" | "POST /api/jobs/{run_id}/cancel" | "GET /api/jobs/{run_id}/output" | "POST /api/jobs/{run_id}/retry" | "GET /api/settings/effective" | "DELETE /api/settings/global/{operation}" | "PUT /api/settings/global/{operation}" | "GET /api/setup" | "POST /api/shutdown" | "GET /api/trash" | "GET /api/trash/audits/recent" | "GET /api/trash/{item_id}/preview" | "POST /api/trash/{item_id}/restore"

export interface ActionProposalState {
  "action": string
  "confirmed_at"?: string | null
  "conversation_id": string
  "created_at": string
  "expires_at": string
  "id": string
  "payload": Record<string, unknown>
  "revision": number
  "status": "pending" | "confirmed" | "rejected" | "expired" | "executed" | "failed"
  "task_run_id"?: string | null
  "updated_at": string
}

export interface AgendaItemState {
  "id": string
  "note"?: string | null
  "question"?: string | null
  "rationale"?: string | null
  "status"?: string | null
  "title"?: string | null
}

export interface AgentAggregateTruncation {
  "decision_count": number
  "final_bytes": number
  "original_bytes": number
}

export interface AgentAssertion {
  "atomic"?: AgentAtomicAssertion | null
  "citations": Array<string | AgentCitationInput>
  "text": string
  "type"?: "unspecified" | "identity" | "regulatory_status" | "formal_company_disclosure" | "company_disclosure" | "event" | "transaction" | "value_chain_relationship" | "market_size" | "market_share" | "valuation" | "unofficial_statistics" | "financial" | "financial_figure" | "technical" | "technical_performance" | "causal" | "causality" | "forecast" | "forecast_estimate" | "estimate" | "investment" | "investment_judgment" | "opinion"
}

export interface AgentAssertionState {
  "citations": Array<AgentCitationState>
  "claim_id"?: string | null
  "id": string
  "status": "draft_review_required" | "rejected" | "opinion" | "submitted_for_verification" | "candidate" | "disputed" | "accepted"
  "text": string
  "type": string
  "verification"?: AgentVerificationChecks | null
}

export interface AgentAtomicAssertion {
  "currency"?: string | null
  "object": unknown
  "period"?: string | null
  "predicate": string
  "qualifiers"?: Record<string, unknown>
  "region": string
  "statistical_definition"?: string | null
  "subject": string
  "subject_id"?: string | null
  "time": string
  "unit"?: string | null
  "value"?: number | string | null
}

export interface AgentBudgetTruncation {
  "evidence_id_count": number
  "failure_count": number
  "final_bytes": number
  "locator_count": number
  "original_bytes": number
}

export interface AgentCapabilityPage {
  "items": Array<AgentCapabilityState>
  "total": number
}

export interface AgentCapabilityState {
  "auth": string
  "commands": Array<string>
  "connection": "native_cli" | "api" | "mcp" | "taskpack" | "restricted_cli"
  "docs_url": string
  "execution_level": "direct" | "handoff" | "import_only"
  "fallbacks"?: Array<string>
  "id": string
  "kind": "agent" | "api" | "bridge"
  "name": string
  "native_args"?: Array<string>
  "native_session_implemented"?: boolean
  "note": string
  "protocol_maturity"?: string
  "region": string
  "schedulable": boolean
  "session_level"?: string
  "session_protocol"?: string
  "structured_output": boolean
  "web_access"?: boolean | null
}

export interface AgentCitationInput {
  "content_hash"?: string | null
  "locator"?: TextOffsetLocator | HtmlSelectorLocator | PdfPageLocator | ApiFieldLocator | null
  "role"?: "support" | "conversion_benchmark"
  "url": string
}

export interface AgentCitationState {
  "canonical_url": string
  "document_id"?: string | null
  "id": string
  "reachability": string
  "snapshot_id"?: string | null
  "source_id"?: string | null
  "url": string
  "verified_at"?: string | null
}

export interface AgentDiagnosticState {
  "authenticated"?: boolean | null
  "connection": "native_cli" | "api" | "mcp" | "taskpack" | "restricted_cli"
  "detail": string
  "executable"?: string
  "executable_fingerprint"?: ExecutableFingerprintState | null
  "execution_level": "direct" | "handoff" | "import_only"
  "failure_code"?: string | null
  "id": string
  "installed": boolean
  "ready": boolean
  "resolved_executable"?: string
  "status": "missing" | "detected" | "ready" | "incompatible" | "timeout" | "output_limit" | "auth_failed" | "handoff" | "import_only" | "invalid_configuration" | "not_configured" | "busy"
  "version"?: string
  "version_verified": boolean
}

export interface AgentDiscoveryPage {
  "items": Array<AgentDiscoveryState>
  "total": number
}

export interface AgentDiscoveryRequest {
  "path"?: string
  "selected_executables"?: Array<string>
}

export interface AgentDiscoveryState {
  "auth": string
  "authenticated"?: boolean | null
  "commands": Array<string>
  "connection": "native_cli" | "api" | "mcp" | "taskpack" | "restricted_cli"
  "detail": string
  "docs_url": string
  "executable": string
  "execution_level": "direct" | "handoff" | "import_only"
  "failure_code"?: string | null
  "fallbacks"?: Array<string>
  "id": string
  "installed": boolean
  "kind": "agent" | "api" | "bridge"
  "name": string
  "native_args"?: Array<string>
  "native_session_implemented"?: boolean
  "note": string
  "protocol_maturity"?: string
  "ready": boolean
  "region": string
  "schedulable": boolean
  "session_level"?: string
  "session_protocol"?: string
  "status": "missing" | "detected" | "ready" | "incompatible" | "timeout" | "output_limit" | "auth_failed" | "handoff" | "import_only" | "invalid_configuration" | "not_configured"
  "structured_output": boolean
  "version"?: string
  "version_verified": boolean
  "web_access"?: boolean | null
}

export interface AgentGateAtomic {
  "currency"?: string | null
  "object": JsonValue
  "period"?: string | null
  "predicate": string
  "qualifiers"?: Record<string, JsonValue>
  "region": string
  "statistical_definition"?: string | null
  "subject": string
  "subject_id"?: string | null
  "time": string
  "unit"?: string | null
  "value"?: number | string | null
}

export interface AgentGateCheck {
  "approximate_provider_tokens"?: number | null
  "assertion_type"?: string | null
  "atomic"?: AgentGateAtomic | null
  "budget_truncation"?: AgentBudgetTruncation | null
  "citation_count"?: number | null
  "claim"?: AgentGateClaimProjection | null
  "conflicting_claim_ids"?: Array<string> | null
  "conversions"?: Array<AgentGateConversion> | null
  "declared_type"?: string | null
  "entity_ids"?: Array<string> | null
  "errors"?: Array<string> | null
  "evaluator_mode"?: string | null
  "evidence"?: Array<AgentGateEvidenceProjection> | null
  "evidence_ids": Array<string>
  "excerpt_bytes"?: number | null
  "expected_entity_id"?: string | null
  "failures"?: Array<AgentGateFailure> | null
  "fetched_bytes"?: number | null
  "generation_call_id"?: string | null
  "generator_id"?: string | null
  "high_risk_signals"?: Array<string> | null
  "inconsistent_signals"?: Array<string> | null
  "independent_assertion_types"?: Array<string> | null
  "independent_clusters"?: Array<string> | null
  "independent_verifiers"?: Array<string> | null
  "inferred_type"?: string | null
  "limits"?: AgentResourceLimits | null
  "locators": Array<AgentLocatorProvenance>
  "publication_times"?: Array<string> | null
  "publishers"?: Array<AgentGatePublisher> | null
  "reason": string
  "retryable"?: boolean | null
  "signals"?: Array<string> | null
  "status": "passed" | "failed" | "partial" | "unknown" | "not_applicable"
}

export interface AgentGateClaimProjection {
  "object": JsonValue
  "predicate": string
  "qualifiers": Record<string, JsonValue>
  "subject_id"?: string | null
  "valid_from": string
  "valid_to": string
}

export interface AgentGateConversion {
  "benchmark_source": string
  "formula"?: string | null
  "original_value"?: number | string | null
  "rate"?: string | null
  "target_value"?: number | string | null
  "tolerance": string
  "tolerance_status"?: "default_unverified" | null
}

export interface AgentGateEvidenceProjection {
  "citation_id": string
  "content_hash": string
  "excerpt": string
  "locator": TextOffsetLocator | HtmlSelectorLocator | PdfPageLocator | ApiFieldLocator
  "published_at": string
  "publisher_cluster": string
  "reachable": boolean
  "relation": "supports" | "qualifies"
  "role": "support" | "conversion_benchmark" | "invalid"
  "url": string
}

export interface AgentGateFailure {
  "content_hash_present"?: boolean | null
  "evidence_id": string
  "failure_code"?: "invalid_locator" | null
  "invalid_locator_type"?: string | null
  "reason": string
  "status_code"?: number | null
}

export interface AgentGatePublisher {
  "domain": string
  "evidence_id": string
  "name": string
  "owner_cluster": string
  "verification_status": string
}

export interface AgentLocatorProvenance {
  "content_hash": string
  "evidence_id": string
  "excerpt": string
  "locator": TextOffsetLocator | HtmlSelectorLocator | PdfPageLocator | ApiFieldLocator
  "url": string
}

export interface AgentProbeState {
  "connection"?: string | null
  "detail": string
  "latency_ms": number
  "provider": string
  "ready": boolean
  "status": "ready" | "not_ready" | "unsupported" | "unexpected_response" | "failed"
}

export interface AgentProfileDeleteState {
  "removed": boolean
}

export interface AgentProfilePage {
  "items": Array<CustomAgentProfile>
  "limit"?: 100
  "total": number
}

export interface AgentResourceLimits {
  "approximate_provider_tokens": number
  "citation_count": number
  "excerpt_bytes": number
  "fetched_bytes": number
  "single_excerpt_bytes": number
  "stored_verification_bytes": number
}

export interface AgentResultContract {
  "assertions": Array<AgentResultContractAssertion>
  "generation_call_id": "unique-generation-call-id"
  "status": "draft_review_required"
  "summary": "string"
}

export interface AgentResultContractAssertion {
  "atomic": AgentResultContractAtomic
  "citations": Array<AgentResultContractCitation>
  "text": "string"
  "type": "identity|event|market_size|financial|technical_performance|causal|forecast|opinion"
}

export interface AgentResultContractAtomic {
  "currency": "ISO-4217|null"
  "object": "value"
  "period": "string|null"
  "predicate": "string"
  "qualifiers": Record<string, unknown>
  "region": "string"
  "statistical_definition": "string|null"
  "subject": "string"
  "subject_id": "canonical-entity-id"
  "time": "ISO-8601 or explicit period"
  "unit": "string|null"
  "value": "number|null"
}

export interface AgentResultContractCitation {
  "content_hash": "sha256-hex"
  "locator": TextOffsetLocator
  "role": "support|conversion_benchmark"
  "url": "https://..."
}

export interface AgentResultImport {
  "agent_id": string
  "assertions": Array<AgentAssertion>
  "generation_call_id"?: string | null
  "summary": string
  "task_id": string
}

export interface AgentResultPage {
  "industry": string
  "items": Array<AgentResultState>
  "limit": number
  "next_offset"?: number | null
  "offset": number
  "total": number
}

export interface AgentResultState {
  "agent_id": string
  "assertions": Array<AgentAssertionState>
  "content_sha256": string
  "created_at": string
  "duplicate"?: boolean
  "industry": string
  "original_file": string
  "path"?: string | null
  "result_id": string
  "status": "draft_review_required" | "rejected" | "opinion" | "submitted_for_verification" | "candidate" | "disputed" | "accepted"
  "summary": string
  "task_id": string
}

export interface AgentReviewRequest {
  "assertion_id": string
  "decision": "rejected" | "opinion" | "submitted_for_verification"
  "note"?: string
}

export interface AgentSemanticCheck {
  "approximate_provider_tokens"?: number | null
  "assertion_type"?: string | null
  "atomic"?: AgentGateAtomic | null
  "budget_truncation"?: AgentBudgetTruncation | null
  "citation_count"?: number | null
  "claim"?: AgentGateClaimProjection | null
  "conflicting_claim_ids"?: Array<string> | null
  "conversions"?: Array<AgentGateConversion> | null
  "decision": "supported" | "partial" | "contradicted" | "unknown"
  "declared_type"?: string | null
  "entity_ids"?: Array<string> | null
  "errors"?: Array<string> | null
  "evaluator_mode"?: string | null
  "evidence"?: Array<AgentGateEvidenceProjection> | null
  "evidence_ids": Array<string>
  "excerpt_bytes"?: number | null
  "expected_entity_id"?: string | null
  "failures"?: Array<AgentGateFailure> | null
  "fetched_bytes"?: number | null
  "generation_call_id"?: string | null
  "generator_id"?: string | null
  "high_risk_signals"?: Array<string> | null
  "inconsistent_signals"?: Array<string> | null
  "independent_assertion_types"?: Array<string> | null
  "independent_clusters"?: Array<string> | null
  "independent_verifiers"?: Array<string> | null
  "inferred_type"?: string | null
  "limits"?: AgentResourceLimits | null
  "locators": Array<AgentLocatorProvenance>
  "publication_times"?: Array<string> | null
  "publishers"?: Array<AgentGatePublisher> | null
  "reason": string
  "retryable"?: boolean | null
  "signals"?: Array<string> | null
  "status": "passed" | "failed" | "partial" | "unknown" | "not_applicable"
}

export interface AgentState {
  "authenticated"?: boolean | null
  "commands": Array<string>
  "connection": string
  "detail"?: string
  "docs_url": string
  "executable"?: string
  "execution": string
  "fallbacks"?: Array<string>
  "id": string
  "installed": boolean
  "name": string
  "native_args"?: Array<string>
  "native_session_implemented"?: boolean
  "note": string
  "protocol_maturity"?: string
  "ready": boolean
  "region": string
  "schedulable"?: boolean
  "session_level"?: string
  "session_protocol"?: string
}

export interface AgentTaskExport {
  "industry": string
  "result_contract": AgentResultContract
  "schema_version": 1
  "task": AgentTaskState
}

export interface AgentTaskPage {
  "industry": string
  "items": Array<AgentTaskState>
  "limit": number
  "next_offset"?: number | null
  "offset": number
  "total": number
}

export interface AgentTaskState {
  "acceptance": Record<string, unknown>
  "agenda_id": string
  "budget": number
  "constraints": Record<string, unknown>
  "created_at": string
  "id": string
  "industry": string
  "queries": Array<string>
  "rationale": string
  "result_artifact_id"?: string | null
  "run_id"?: string | null
  "status": string
  "title": string
}

export interface AgentVerificationChecks {
  "atomization": AgentGateCheck
  "conflict": AgentGateCheck
  "corroboration": AgentGateCheck
  "entity_alignment": AgentGateCheck
  "fact_projection": AgentGateCheck
  "generation_provenance": AgentGateCheck
  "locator_integrity": AgentGateCheck
  "numeric_consistency": AgentGateCheck
  "publication_time": AgentGateCheck
  "publisher_identity": AgentGateCheck
  "reachability": AgentGateCheck
  "resource_budget": AgentGateCheck
  "semantic_support": AgentSemanticCheck
  "type_classification": AgentGateCheck
  "type_policy": AgentGateCheck
  "verifier_independence": AgentGateCheck
}

export interface AgentVerificationDecisionState {
  "assertion_id": string
  "checks": AgentVerificationChecks
  "claim_id"?: string | null
  "disposition": "candidate" | "disputed" | "accepted" | "rejected"
}

export interface AgentVerificationState {
  "decisions": Array<AgentVerificationDecisionState>
  "detail": string
  "limit": number
  "next_offset"?: number | null
  "offset": number
  "response_truncation"?: AgentAggregateTruncation | null
  "result_id": string
  "status": "verified" | "partial" | "retryable" | "no_submitted_assertions"
  "total": number
}

export interface ApiFieldLocator {
  "path": string
  "type": "api_field"
}

export interface ApiProviderState {
  "api_base"?: string
  "auth_configurable"?: boolean
  "auth_type": "bearer" | "api_key_header"
  "configured": boolean
  "default_model"?: string
  "docs_url"?: string
  "id": string
  "key_env": string
  "model"?: string
  "name": string
  "ready": boolean
  "region": string
  "schedulable"?: boolean
  "web_search"?: boolean
}

export interface ArchiveState {
  "archived_to": string
}

export interface ArtifactState {
  "_file"?: string | null
  "_key"?: string | null
  "event"?: string | null
  "generated_at"?: string | null
  "id"?: string | null
  "limitations"?: Array<unknown>
  "manifest_file"?: string | null
  "model"?: string | null
  "name"?: string | null
  "path"?: string | null
  "portable_file"?: string | null
  "provider"?: string | null
  "quality"?: Record<string, unknown>
  "quality_file"?: string | null
  "references"?: Array<unknown>
  "report_file"?: string | null
  "slug"?: string | null
  "status"?: string | null
  "summary"?: string | null
  "title"?: string | null
  "visualization"?: ArtifactVisualizationState
  "window_end"?: string | null
}

export interface ArtifactVisualizationState {
  "directed_graph"?: DirectedGraphState | null
}

export interface AuditState {
  "action": string
  "actor": string
  "details": Record<string, unknown>
  "id": number
  "object_id"?: string | null
  "object_type": string
  "occurred_at": string
}

export interface AutomationState {
  "email_delivery"?: boolean
  "schedules": Array<ScheduleState>
}

export interface BackgroundPermissionMutation {
  "affected_run_ids"?: Array<string>
  "allowed": boolean
  "folder": string
  "operation": string
  "provider": string
  "updated_at": string
}

export interface BackgroundPermissionState {
  "allowed": boolean
  "folder": string
  "granted_at"?: string
  "granted_by"?: string
  "operation": string
  "provider": string
  "revoked_at"?: string | null
  "revoked_by"?: string | null
  "updated_at": string
}

export interface BackgroundPermissionUpdate {
  "allowed": boolean
  "folder": string
  "operation": string
  "provider": string
  "reason"?: string
}

export interface BackgroundScheduleErrorState {
  "action": string
  "error": string
  "folder": string
  "pause_reason": string
  "retry_after"?: string | null
  "runtime_status": string
}

export interface BackgroundServiceState {
  "enabled": boolean
  "error_category"?: string
  "installed": boolean
  "interval_minutes"?: number
  "platform": string
}

export interface BackgroundState {
  "email_delivery"?: false
  "last_wakeup"?: WorkerWakeupState | null
  "next_run_at"?: string | null
  "permissions": Array<BackgroundPermissionState>
  "schedule_errors": Array<BackgroundScheduleErrorState>
  "service": BackgroundServiceState
}

export interface CampaignRoundHistoryState {
  "id": string
  "log": Array<OperationLogState>
  "outcome"?: Record<string, unknown>
  "round_no": number
  "status": string
}

export interface CancelState {
  "cancelled": boolean
}

export interface ChainEdgeState {
  "confidence"?: number | null
  "dst_name": string
  "dst_node_id": string
  "effect"?: string | null
  "evidence"?: Array<Record<string, unknown>>
  "evidence_count"?: number
  "id": string
  "lag_days"?: number | null
  "relation": string
  "src_name": string
  "src_node_id": string
  "status": string
  "valid_from"?: string | null
  "valid_to"?: string | null
}

export interface ChainNodeState {
  "coverage_status"?: string
  "description"?: string
  "entity_count"?: number
  "evidence_count"?: number
  "evidenced_entities"?: number
  "id"?: string | null
  "label"?: string | null
  "name": string
  "order"?: number
  "status"?: string
}

export interface ColumnarPrototypeState {
  "authority": "sqlite"
  "prototype_policy": string
  "prototype_recommended": boolean
  "triggers": Record<string, boolean>
  "write_path": "sqlite_only"
}

export interface ConfirmedProposalState {
  "job": Record<string, unknown>
  "proposal": ActionProposalState
}

export interface ConversationMessageState {
  "content": string
  "conversation_id": string
  "created_at": string
  "id": string
  "metadata"?: Record<string, unknown>
  "role": "user" | "assistant" | "system" | "tool"
}

export interface ConversationState {
  "capability": Record<string, unknown>
  "connection"?: string | null
  "connection_warning"?: string | null
  "conversation": Record<string, unknown>
  "messages": Array<ConversationMessageState>
  "proposals": Array<ActionProposalState>
}

export interface ConversationTurnRequest {
  "message": string
  "provider": string
}

export interface CountState {
  "deleted": number | boolean
}

export interface CoverageAttemptCreate {
  "actor"?: string
  "entity_yield"?: number
  "evidence"?: Array<Record<string, unknown>>
  "manual_correction": true
  "query": string
  "rationale"?: string
  "source_yield"?: number
  "status"?: "planned" | "running" | "completed" | "failed" | "stopped"
  "stopping_reason"?: string
}

export interface CoverageAttemptState {
  "cell_id": string
  "created_at": string
  "entity_yield": number
  "evidence": Array<unknown>
  "id": string
  "query": string
  "rationale": string
  "source_yield": number
  "status": string
  "stopping_reason": string
  "updated_at": string
}

export interface CoverageCandidateState {
  "assertion_id"?: string | null
  "canonical_key": string
  "cell_id": string
  "created_at": string
  "document_id"?: string | null
  "entity_id"?: string | null
  "id": string
  "industry_id": string
  "payload": Record<string, unknown>
  "query_id": string
  "round_id": string
  "status": "candidate" | "manual_review" | "accepted" | "rejected"
  "status_reason": string
  "updated_at": string
}

export interface CoverageCellCreate {
  "dimensions": Record<string, string>
  "priority"?: number
  "rationale"?: string
  "status"?: "gap" | "thin" | "covered" | "paused"
}

export interface CoverageCellState {
  "attempt_history"?: Array<CoverageAttemptState>
  "attempts": number
  "created_at": string
  "dimensions": Record<string, string>
  "entity_yield": number
  "id": string
  "last_attempt_at"?: string | null
  "priority": number
  "rationale": string
  "source_yield": number
  "status": string
  "updated_at": string
}

export interface CoverageExpansionExecutionRequest {
  "provider"?: string | null
}

export type CoverageExpansionRequest = Record<string, unknown>

export interface CoverageFrontierState {
  "cells": Array<Record<string, unknown>>
  "entity_queries": Array<Record<string, unknown>>
  "relation_queries": Array<Record<string, unknown>>
  "round_id": string
  "round_no": number
  "status": "planned" | "running" | "paused" | "completed" | "converged" | "failed"
  "stopping_reason"?: string | null
}

export interface CoverageQueryState {
  "id": string
  "kind"?: "entity" | "relation" | null
  "query": string
  "status": string
}

export interface CoverageReviewQueueState {
  "entities": Array<CoverageCandidateState>
  "relations": Array<CoverageCandidateState>
}

export interface CoverageRoundState {
  "created_at": string
  "frontier": Array<Record<string, unknown>>
  "id": string
  "industry_id": string
  "log": Array<OperationLogState>
  "outcome": Record<string, unknown>
  "queries"?: Array<CoverageQueryState>
  "round_no": number
  "status": "planned" | "running" | "paused" | "completed" | "converged" | "failed"
  "stopping_reason": string
  "updated_at": string
}

export interface CoverageState {
  "cells": Array<CoverageCellState>
  "summary": CoverageSummaryState
}

export interface CoverageSummaryState {
  "entity_yield": number
  "gaps": number
  "source_yield": number
  "total": number
}

export interface CustomAgentProfile {
  "args"?: Array<string>
  "capability_id"?: string | null
  "command": string
  "executable_path"?: string | null
  "id": string
  "name": string
}

export interface DailyIdentity {
  "category": string
  "date": string
  "key": string
}

export interface DailyItemState {
  "abstract"?: string | null
  "category": string
  "date": string
  "display_source": string
  "evidence_status"?: string | null
  "id": string
  "identity": DailyIdentity
  "origin": string
  "published_at"?: string | null
  "ranking_score"?: number | null
  "review_status"?: string | null
  "title": string
  "url": string
}

export interface DailyState {
  "counts": Record<string, number>
  "dates": Array<string>
  "items": Array<DailyItemState>
  "next_cursor"?: string | null
  "origins": Record<string, number>
  "selection_scope": "current_page"
  "timezone": string
  "total": number
  "window_end": string
  "window_reason": "previous_local_day_04_to_now"
  "window_start": string
}

export interface DeleteDailyRequest {
  "items": Array<DailyIdentity>
}

export interface DirectedGraphState {
  "edges"?: Array<ChainEdgeState>
  "nodes"?: Array<ChainNodeState>
}

export interface DriftMetricState {
  "algorithm_version": string
  "baseline"?: number | null
  "baseline_denominator": number
  "delta"?: number | null
  "denominator": number
  "diagnosis": string
  "dimensions": Record<string, unknown>
  "metric": string
  "numerator": number
  "raw_observation_links": Array<string>
  "status": "stable" | "degraded" | "insufficient_data"
  "threshold": number
  "value"?: number | null
  "window_days": 7 | 30
}

export interface DriftSegmentState {
  "algorithm_version": string
  "dimensions": Record<string, unknown>
  "end": string
  "metric": string
  "observation_count": number
  "start": string
}

export interface EntityAliasState {
  "alias": string
  "language"?: string | null
  "valid_from"?: string | null
  "valid_to"?: string | null
}

export interface EntityCandidateReview {
  "actor": string
  "decision": "approve" | "manual_review" | "rejected"
  "reason": string
}

export interface EntityCandidateReviewState {
  "candidate_id": string
  "decision": "created" | "merged" | "manual_review" | "rejected"
  "entity_id"?: string | null
  "reason": string
  "review": Record<string, string>
}

export interface EntityCoverageCellState {
  "chain_stage": string
  "current": number
  "entity_type": string
  "explanation": string
  "gap": number
  "high_value": boolean
  "id": string
  "priority": number
  "region": "china" | "foreign"
  "relation_evidence": Array<RelationEvidenceState>
  "source_type": string
  "status": string
  "subdomain": string
  "target": number
}

export interface EntityCoverageMatrixState {
  "algorithm_version": string
  "cells": Array<EntityCoverageCellState>
  "completeness_proven": boolean
  "gap_count": number
  "industry": string
}

export interface EntityRelationState {
  "confidence"?: number | null
  "dst_entity_id": string
  "dst_name": string
  "id": string
  "predicate": string
  "src_entity_id": string
  "src_name": string
  "valid_from"?: string | null
  "valid_to"?: string | null
}

export interface EntityRoleState {
  "chain": string
  "confidence"?: number | null
  "evidence_count"?: number
  "role": string
  "status": string
  "valid_from"?: string | null
  "valid_to"?: string | null
}

export interface ExecutableFingerprintState {
  "canonical_path": string
  "device": number
  "inode": number
  "mtime_ns": number
  "sha256": string
  "size": number
  "source_path": string
}

export interface GenerateRequest {
  "action": "daily" | "weekly" | "monthly" | "quarterly" | "report" | "deep_report" | "impact" | "lab" | "bootstrap" | "coverage" | "history"
  "event"?: string
  "execution_mode"?: "taskpack" | "direct" | null
  "kind"?: string
  "pipeline_mode"?: "aggregate" | "generate" | null
  "provider"?: string
}

export interface HTTPValidationError {
  "detail"?: Array<ValidationError>
}

export interface HealthState {
  "active_jobs": number
  "automation_running": boolean
  "data_root": string
  "database": boolean
  "session_required": boolean
  "status": string
}

export interface HistoryCoverageState {
  "items": Array<HistoryHorizonState>
}

export interface HistoryHorizonState {
  "admitted_total": number
  "attempts"?: number
  "buckets_covered": number
  "buckets_total": number
  "horizon": "weekly" | "monthly" | "quarterly" | "semiannual" | "biennial" | "fiveyear"
  "publisher_count": number
  "ready": boolean
  "required_buckets": number
  "required_total": number
  "status": string
  "target": number
  "target_range": Array<number>
  "updated_at"?: string | null
  "window_end": string
  "window_start": string
}

export interface HtmlSelectorLocator {
  "selector": string
  "type": "html_selector"
}

export interface IndustryBundleState {
  "chain"?: Array<Record<string, JsonValue>>
  "chain_edges"?: Array<Record<string, JsonValue>>
  "checksum_sha256": string
  "claims"?: Array<Record<string, JsonValue>>
  "documents"?: Array<Record<string, JsonValue>>
  "entities"?: Array<Record<string, JsonValue>>
  "exported_at": string
  "industry": Record<string, JsonValue>
  "relations"?: Array<Record<string, JsonValue>>
  "schema_version": 1
  "sources"?: Array<Record<string, JsonValue>>
}

export interface IndustryCreate {
  "folder": string
  "name"?: string
}

export interface IndustryImportRequest {
  "bundle": IndustryBundleState
  "folder": string
  "name"?: string
}

export interface IndustryImportState {
  "folder": string
  "imported": Record<string, number>
  "name": string
}

export interface IndustryMutationState {
  "folder": string
  "name": string
}

export interface IndustryRename {
  "folder": string
  "name"?: string
}

export interface IndustryState {
  "folder": string
  "name": string
  "periodic_enabled"?: boolean
}

export interface JobAccepted {
  "action"?: string
  "email_delivery"?: boolean
  "run_id": string
  "status": string
  "title"?: string
}

export interface JobOutputState {
  "output": string
  "run_id": string
}

export interface JobState {
  "active"?: boolean
  "artifact_path"?: string | null
  "checkpoint"?: Record<string, unknown>
  "elapsed_seconds"?: number
  "error"?: string | null
  "error_category"?: string
  "heartbeat_at"?: string | null
  "model"?: string
  "operation"?: string | null
  "origin"?: "app" | "manual" | "system_schedule" | "background_worker"
  "parent_run_id"?: string | null
  "progress"?: number
  "progress_mode"?: "determinate" | "indeterminate"
  "provider"?: string
  "recovery_actions"?: Array<"cancel" | "retry" | "resume">
  "request_dispatched_at"?: string | null
  "result_kind"?: "artifact" | "local_data" | "task_package" | "unknown"
  "run_id": string
  "stage"?: string | null
  "stalled"?: boolean
  "status": string
  "time_window"?: JobTimeWindowState
  "title"?: string
  "updated_at"?: string
}

export interface JobTimeWindowState {
  "end"?: string | null
  "start"?: string | null
  "timezone"?: string | null
}

export type JsonValue = unknown

export interface KnowledgeEntityDetail {
  "aliases": Array<EntityAliasState>
  "canonical_name": string
  "chain"?: string | null
  "claims": Array<StoryClaimState>
  "confidence"?: number | null
  "country"?: string | null
  "evidence_count": number
  "id": string
  "kind": string
  "name_en"?: string | null
  "relations": Array<EntityRelationState>
  "role"?: string | null
  "roles": Array<EntityRoleState>
  "status": string
}

export interface KnowledgeEntityPage {
  "items": Array<KnowledgeEntitySummary>
  "limit": number
  "next_offset"?: number | null
  "offset": number
  "total": number
}

export interface KnowledgeEntitySummary {
  "chain"?: string | null
  "confidence"?: number | null
  "country"?: string | null
  "id": string
  "kind": string
  "name": string
  "name_en"?: string | null
  "role"?: string | null
  "status": string
}

export interface McpConfigState {
  "format": string
  "id": string
  "name": string
  "value": string | Record<string, unknown>
}

export interface MomentumDeltaState {
  "evidence_strength": number
  "independent_publishers": number
  "rank": number
  "score": number
}

export interface MomentumObservationState {
  "algorithm_segment_started": boolean
  "algorithm_version": string
  "classification": string
  "deltas"?: MomentumDeltaState | null
  "evidence_strength": number
  "id": string
  "independent_publishers": number
  "intelligence_date": string
  "missing_days": number
  "observed_at"?: string | null
  "rank": number
  "raw_observation_link": string
  "score": number
  "seven_day_trend": MomentumDeltaState
  "status": "new" | "heating" | "tracking" | "cooling" | "unresolved"
}

export interface OperationLogState {
  "at": string
  "level"?: string
  "message": string
}

export interface OverviewIndustryState {
  "description"?: string | null
  "id"?: string | null
  "name"?: string | null
  "name_en"?: string | null
  "references"?: Array<unknown>
  "status"?: string | null
}

export interface OverviewState {
  "chain": Array<ChainNodeState>
  "chain_edges": Array<ChainEdgeState>
  "entities": Array<KnowledgeEntitySummary>
  "industry": OverviewIndustryState
  "latest_document_date"?: string | null
  "source_categories": Record<string, number>
  "stats": OverviewStatsState
}

export interface OverviewStatsState {
  "candidate_entities"?: number
  "chain_nodes"?: number
  "claims"?: number
  "documents": number
  "empty_chain_nodes"?: number
  "entities": number
  "events"?: number
  "evidence"?: number
  "relations": number
  "sources": number
  "verified_claims"?: number
}

export interface PdfPageLocator {
  "end": number
  "page": number
  "start": number
  "type": "pdf_page"
}

export interface PeriodicArtifactsState {
  "monthly": Array<ArtifactState>
  "quarterly": Array<ArtifactState>
  "weekly": Array<ArtifactState>
}

export interface PortableExportState {
  "path": string
  "quality"?: Record<string, unknown>
  "status": string
}

export interface ProductsState {
  "deep_reports": Array<ArtifactState>
  "impacts": Array<ArtifactState>
  "periodic": PeriodicArtifactsState
  "reports": Array<ArtifactState>
}

export interface ProposalDecisionRequest {
  "revision": number
}

export interface QualityDriftState {
  "alert_count": number
  "as_of": string
  "columnar_prototype": ColumnarPrototypeState
  "metrics": Array<DriftMetricState>
  "segments": Array<DriftSegmentState>
}

export interface RelationEvidenceState {
  "edge_id": string
  "evidence_count": number
  "relation": string
}

export interface ResearchEvidenceState {
  "nodes"?: Array<unknown>
}

export interface ResearchLabState {
  "evidence"?: ResearchEvidenceState
  "scenarios"?: Array<unknown>
}

export interface ResearchState {
  "agenda": Array<AgendaItemState>
  "impacts": Array<ArtifactState>
  "lab": ResearchLabState
  "tasks": Array<ResearchTaskState>
}

export interface ResearchTaskState {
  "budget"?: number | null
  "id": string
  "status"?: string | null
  "title"?: string | null
}

export interface RestorePreviewState {
  "collisions": Array<string>
  "folder": string
  "id": string
  "kind": "industry" | "daily"
  "restorable": boolean
  "restore_count": number
  "skip_count": number
}

export interface RestoreState {
  "folder": string
  "kind": "industry" | "daily"
  "restored": number
  "skipped": number
}

export interface ScheduleState {
  "action": "daily" | "weekly" | "monthly" | "quarterly"
  "attempted_period_identity"?: string | null
  "attempted_period_key"?: string | null
  "catch_up": boolean
  "enabled": boolean
  "last_artifact_path"?: string | null
  "last_attempt_at"?: string | null
  "last_error"?: string | null
  "last_job_run_id"?: string | null
  "last_origin"?: string
  "last_period_identity"?: string | null
  "last_period_key"?: string | null
  "last_success_at"?: string | null
  "last_success_boundary"?: string | null
  "last_window_end"?: string | null
  "last_window_start"?: string | null
  "last_window_timezone"?: string | null
  "local_time": string
  "max_retries"?: number
  "monthday": number
  "next_run_at"?: string | null
  "pause_reason"?: string
  "pipeline_mode"?: "aggregate" | "generate"
  "provider"?: string
  "retry_after"?: string | null
  "retry_count"?: number
  "runtime_status"?: "idle" | "running" | "completed" | "partial" | "failed" | "paused" | "cancelled" | "interrupted"
  "timezone": string
  "weekday": number
}

export interface ScheduleUpdate {
  "catch_up"?: boolean
  "enabled"?: boolean
  "local_time"?: string
  "monthday"?: number
  "pipeline_mode"?: "aggregate" | "generate"
  "provider"?: string
  "timezone"?: string
  "weekday"?: number
}

export interface SetupState {
  "agent_profiles"?: Array<CustomAgentProfile>
  "agents": Array<AgentState>
  "api_providers": Array<ApiProviderState>
  "data_root": string
  "mcp_command": Array<string>
  "mcp_configs": Array<McpConfigState>
  "privacy_note": string
  "runtime_ready": boolean
  "taskpack_ready": boolean
}

export interface ShutdownState {
  "status": "stopping"
}

export interface SourceCampaignCreate {
  "budget"?: number
  "targets": Array<string>
}

export interface SourceCampaignDetail {
  "budget": number
  "candidate_page": SourceCandidatePage
  "created_at": string
  "id": string
  "industry_id": string
  "query_ledger": Array<SourceQueryState>
  "round_history": Array<CampaignRoundHistoryState>
  "rounds": number
  "source_gaps": Array<SourceGapState>
  "status": "planned" | "running" | "paused" | "converged" | "failed"
  "stopping_reason": string
  "targets": Array<string>
  "updated_at": string
}

export interface SourceCampaignExecutionRequest {
  "provider"?: string | null
}

export interface SourceCampaignPage {
  "items": Array<SourceCampaignState>
  "limit": number
  "next_offset"?: number | null
  "offset": number
  "total": number
}

export interface SourceCampaignState {
  "budget": number
  "created_at": string
  "id": string
  "industry_id": string
  "rounds": number
  "status": "planned" | "running" | "paused" | "converged" | "failed"
  "stopping_reason": string
  "targets": Array<string>
  "updated_at": string
}

export interface SourceCandidatePage {
  "items": Array<SourceCandidateState>
  "limit": number
  "next_offset"?: number | null
  "offset": number
  "total": number
}

export interface SourceCandidateReview {
  "actor": string
  "decision": "manual_review" | "active" | "reserve" | "rejected"
  "reason": string
}

export interface SourceCandidateState {
  "campaign_id": string
  "canonical_url": string
  "category": string
  "id": string
  "name": string
  "query_ids"?: Array<string>
  "review"?: SourceReviewState | null
  "score": number
  "selection_reason"?: string
  "status": "candidate" | "manual_review" | "active" | "reserve" | "rejected"
  "status_reason"?: string
  "url": string
}

export interface SourceCreate {
  "category": string
  "name": string
  "note"?: string
  "publisher_country"?: string
  "tier"?: string
  "url": string
}

export interface SourceGapState {
  "candidate_count": number
  "category": string
  "current": number
  "explanation": string
  "gap": number
  "query_count": number
  "rejection_reasons": Record<string, number>
  "target": number
}

export interface SourceHealthState {
  "adapter"?: string | null
  "consecutive_failures"?: number
  "error_code"?: string | null
  "error_message"?: string | null
  "last_checked_at"?: string | null
  "last_good_at"?: string | null
  "last_success_at"?: string | null
  "retry_after"?: string | null
  "status": string
}

export interface SourceItemState {
  "category": string
  "governance_reason"?: string | null
  "governance_role"?: string | null
  "governance_score"?: number | null
  "health"?: SourceHealthState | null
  "id"?: string | null
  "monitoring_status"?: string | null
  "name": string
  "note"?: string | null
  "origin"?: string | null
  "publisher_country"?: string | null
  "selection_reason"?: string | null
  "tier"?: string | null
  "url": string
}

export interface SourceMutationState {
  "added": boolean
}

export interface SourceQueryState {
  "campaign_id": string
  "created_at": string
  "dimensions": Record<string, unknown>
  "family": string
  "id": string
  "language": string
  "outcome": Record<string, unknown>
  "query": string
  "round_no": number
}

export interface SourceReassessmentRequest {
  "actor": string
  "decision": "active" | "manual" | "reserve" | "rejected"
  "reason": string
}

export interface SourceReassessmentState {
  "review": Record<string, string>
  "source_id": string
  "state": "active" | "manual" | "reserve" | "rejected"
}

export interface SourceReviewState {
  "actor"?: string
  "decision"?: string
  "reason"?: string
}

export interface SourcesState {
  "categories": Record<string, Array<SourceItemState>>
  "industry": string
}

export interface StoryClaimEvidenceState {
  "document_title"?: string | null
  "document_url"?: string | null
  "relation": string
}

export interface StoryClaimState {
  "evidence": Array<StoryClaimEvidenceState>
  "id": string
  "object": unknown
  "predicate": string
  "status": string
}

export interface StoryDetailState {
  "canonical_title": string
  "claims": Array<StoryClaimState>
  "clustering_version": string
  "corroborated": boolean
  "document_count": number
  "documents": Array<StoryDocumentState>
  "first_seen_at": string
  "id": string
  "last_seen_at": string
  "metadata"?: Record<string, unknown>
  "publisher_count": number
  "reviews": Array<StoryReviewState>
  "status": string
  "story_family": string
}

export interface StoryDocumentState {
  "abstract"?: string | null
  "category": string
  "editorially_locked"?: boolean
  "id": string
  "observed_date": string
  "origin"?: string | null
  "published_at"?: string | null
  "publisher_cluster"?: string | null
  "relation": string
  "title": string
  "url": string
}

export interface StoryIgnoreRequest {
  "reason": string
}

export interface StoryListState {
  "items": Array<StorySummaryState>
  "total": number
}

export interface StoryMergeRequest {
  "source_story_id": string
}

export interface StoryMomentumBatchState {
  "items": Array<StoryMomentumState>
  "total": number
}

export interface StoryMomentumState {
  "first_appearance"?: string | null
  "last_observation"?: string | null
  "raw_observation_links": Array<string>
  "status": "new" | "heating" | "tracking" | "cooling" | "unresolved"
  "story_id": string
  "timeline": Array<MomentumObservationState>
}

export interface StoryReviewState {
  "action": string
  "actor": string
  "details": Record<string, unknown>
  "occurred_at": string
}

export interface StorySplitRequest {
  "document_ids": Array<string>
  "title": string
}

export interface StorySummaryState {
  "canonical_title": string
  "clustering_version": string
  "document_count": number
  "first_seen_at": string
  "id": string
  "last_seen_at": string
  "publisher_count": number
  "status": string
  "story_family": string
}

export interface StoryUnlockRequest {
  "document_ids": Array<string>
}

export interface TextOffsetLocator {
  "end": number
  "start": number
  "type": "text_offset"
}

export interface TrashItemState {
  "created_at": string
  "folder": string
  "id": string
  "item_count": number
  "kind": "industry" | "daily"
  "name": string
}

export interface TrashRestoreRequest {
  "desired_folder"?: string
}

export interface TrashState {
  "items": Array<TrashItemState>
  "permanent_delete_available": boolean
  "total": number
}

export interface ValidationError {
  "ctx"?: Record<string, unknown>
  "input"?: unknown
  "loc": Array<string | number>
  "msg": string
  "type": string
}

export interface WorkerWakeupState {
  "error"?: Record<string, unknown>
  "finished_at"?: string | null
  "id": string
  "origin": string
  "owner": string
  "started_at": string
  "status": string
  "summary"?: Record<string, unknown>
}

export interface WorkflowSettingsState {
  "execution_mode": "taskpack" | "direct"
  "layers": Array<Record<string, unknown>>
  "pipeline_mode": "aggregate" | "generate"
  "provenance": Record<string, string>
  "provider": string
}

export interface WorkflowSettingsUpdate {
  "execution_mode"?: "taskpack" | "direct" | null
  "pipeline_mode"?: "aggregate" | "generate" | null
  "provider"?: string | null
}
