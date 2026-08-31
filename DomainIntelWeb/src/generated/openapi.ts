/* Generated from openapi.json. Do not edit by hand. */
export type ApiPath = "/api/artifact" | "/api/health" | "/api/industries" | "/api/industries/{folder}" | "/api/industries/{folder}/automation" | "/api/industries/{folder}/automation/{action}" | "/api/industries/{folder}/automation/{action}/run" | "/api/industries/{folder}/coverage" | "/api/industries/{folder}/coverage/cells" | "/api/industries/{folder}/coverage/cells/{cell_id}/attempts" | "/api/industries/{folder}/coverage/initialize" | "/api/industries/{folder}/coverage/plan" | "/api/industries/{folder}/daily" | "/api/industries/{folder}/generate" | "/api/industries/{folder}/history" | "/api/industries/{folder}/knowledge/entities" | "/api/industries/{folder}/knowledge/entities/{entity_id}" | "/api/industries/{folder}/overview" | "/api/industries/{folder}/products" | "/api/industries/{folder}/research" | "/api/industries/{folder}/sources" | "/api/industries/{folder}/stories" | "/api/industries/{folder}/stories/{story_id}" | "/api/industries/{folder}/stories/{story_id}/merge" | "/api/industries/{folder}/stories/{story_id}/split" | "/api/industries/{folder}/stories/{story_id}/unlock" | "/api/jobs" | "/api/jobs/{run_id}/cancel" | "/api/jobs/{run_id}/output" | "/api/jobs/{run_id}/retry" | "/api/shutdown" | "/api/trash" | "/api/trash/audits/recent" | "/api/trash/{item_id}/preview" | "/api/trash/{item_id}/restore"
export type ApiOperation = "GET /api/artifact" | "GET /api/health" | "GET /api/industries" | "POST /api/industries" | "DELETE /api/industries/{folder}" | "PATCH /api/industries/{folder}" | "GET /api/industries/{folder}/automation" | "PUT /api/industries/{folder}/automation/{action}" | "POST /api/industries/{folder}/automation/{action}/run" | "GET /api/industries/{folder}/coverage" | "POST /api/industries/{folder}/coverage/cells" | "POST /api/industries/{folder}/coverage/cells/{cell_id}/attempts" | "POST /api/industries/{folder}/coverage/initialize" | "POST /api/industries/{folder}/coverage/plan" | "DELETE /api/industries/{folder}/daily" | "GET /api/industries/{folder}/daily" | "POST /api/industries/{folder}/generate" | "GET /api/industries/{folder}/history" | "GET /api/industries/{folder}/knowledge/entities" | "GET /api/industries/{folder}/knowledge/entities/{entity_id}" | "GET /api/industries/{folder}/overview" | "GET /api/industries/{folder}/products" | "GET /api/industries/{folder}/research" | "DELETE /api/industries/{folder}/sources" | "GET /api/industries/{folder}/sources" | "POST /api/industries/{folder}/sources" | "GET /api/industries/{folder}/stories" | "GET /api/industries/{folder}/stories/{story_id}" | "POST /api/industries/{folder}/stories/{story_id}/merge" | "POST /api/industries/{folder}/stories/{story_id}/split" | "POST /api/industries/{folder}/stories/{story_id}/unlock" | "GET /api/jobs" | "POST /api/jobs/{run_id}/cancel" | "GET /api/jobs/{run_id}/output" | "POST /api/jobs/{run_id}/retry" | "POST /api/shutdown" | "GET /api/trash" | "GET /api/trash/audits/recent" | "GET /api/trash/{item_id}/preview" | "POST /api/trash/{item_id}/restore"

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
  "model"?: string | null
  "name"?: string | null
  "path"?: string | null
  "provider"?: string | null
  "references"?: Array<unknown>
  "report_file"?: string | null
  "slug"?: string | null
  "status"?: string | null
  "summary"?: string | null
  "title"?: string | null
  "visualization"?: Record<string, unknown>
  "window_end"?: string | null
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

export interface CancelState {
  "cancelled": boolean
}

export interface CountState {
  "deleted": number | boolean
}

export interface CoverageAttemptCreate {
  "actor"?: string
  "entity_yield"?: number
  "evidence"?: Array<Record<string, unknown>>
  "manual_correction": boolean
  "query": string
  "rationale"?: string
  "source_yield"?: number
  "status"?: string
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

export interface CoverageCellCreate {
  "dimensions": Record<string, string>
  "priority"?: number
  "rationale"?: string
  "status"?: string
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

export interface DailyIdentity {
  "category": string
  "date": string
  "key": string
}

export interface DailyState {
  "counts": Record<string, number>
  "dates": Array<string>
  "items": Array<Record<string, unknown>>
  "next_cursor"?: string | null
  "origins": Record<string, number>
  "selection_scope": string
  "total": number
}

export interface DeleteDailyRequest {
  "items": Array<DailyIdentity>
}

export interface GenerateRequest {
  "action": string
  "event"?: string
  "kind"?: string
  "pipeline_mode"?: string
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
  "horizon": string
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

export interface IndustryCreate {
  "folder": string
  "name"?: string
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
  "error"?: string | null
  "operation"?: string | null
  "parent_run_id"?: string | null
  "progress"?: number
  "run_id": string
  "stage"?: string | null
  "stalled"?: boolean
  "status": string
  "title"?: string
  "updated_at"?: string
}

export interface KnowledgeEntityDetail {
  "aliases": Array<Record<string, unknown>>
  "canonical_name": string
  "chain"?: string | null
  "claims": Array<Record<string, unknown>>
  "confidence"?: number | null
  "country"?: string | null
  "evidence_count": number
  "id": string
  "kind": string
  "name_en"?: string | null
  "relations": Array<Record<string, unknown>>
  "role"?: string | null
  "roles": Array<Record<string, unknown>>
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

export interface OverviewState {
  "chain": Array<Record<string, unknown>>
  "entities": Array<Record<string, unknown>>
  "industry": Record<string, unknown>
  "latest_document_date"?: string | null
  "source_categories": Record<string, number>
  "stats": Record<string, unknown>
}

export interface PeriodicArtifactsState {
  "monthly": Array<ArtifactState>
  "quarterly": Array<ArtifactState>
  "weekly": Array<ArtifactState>
}

export interface ProductsState {
  "deep_reports": Array<ArtifactState>
  "impacts": Array<ArtifactState>
  "periodic": PeriodicArtifactsState
  "reports": Array<ArtifactState>
}

export interface ResearchState {
  "agenda": Array<Record<string, unknown>>
  "impacts": Array<ArtifactState>
  "lab": Record<string, unknown>
  "tasks": Array<Record<string, unknown>>
}

export interface RestorePreviewState {
  "collisions": Array<string>
  "folder": string
  "id": string
  "kind": string
  "restorable": boolean
  "restore_count": number
  "skip_count": number
}

export interface RestoreState {
  "folder": string
  "kind": string
  "restored": number
  "skipped": number
}

export interface ScheduleState {
  "action": string
  "attempted_period_key"?: string | null
  "catch_up": boolean
  "enabled": boolean
  "last_artifact_path"?: string | null
  "last_attempt_at"?: string | null
  "last_error"?: string | null
  "last_job_run_id"?: string | null
  "last_period_key"?: string | null
  "last_success_at"?: string | null
  "local_time": string
  "monthday": number
  "next_run_at"?: string | null
  "pipeline_mode"?: string
  "provider"?: string
  "retry_after"?: string | null
  "retry_count"?: number
  "timezone": string
  "weekday": number
}

export interface ScheduleUpdate {
  "catch_up"?: boolean
  "enabled"?: boolean
  "local_time"?: string
  "monthday"?: number
  "pipeline_mode"?: string
  "provider"?: string
  "timezone"?: string
  "weekday"?: number
}

export interface ShutdownState {
  "status": string
}

export interface SourceCreate {
  "category": string
  "name": string
  "note"?: string
  "publisher_country"?: string
  "tier"?: string
  "url": string
}

export interface SourceMutationState {
  "added": boolean
}

export interface SourcesState {
  "categories": Record<string, Array<Record<string, unknown>>>
  "industry": string
}

export interface StoryDetailState {
  "canonical_title": string
  "claims"?: Array<Record<string, unknown>>
  "clustering_version": string
  "corroborated": boolean
  "document_count"?: number
  "documents": Array<StoryDocumentState>
  "first_seen_at": string
  "id": string
  "last_seen_at": string
  "metadata"?: Record<string, unknown>
  "publisher_count"?: number
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

export interface StoryListState {
  "items": Array<StorySummaryState>
  "total": number
}

export interface StoryMergeRequest {
  "source_story_id": string
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
  "document_count"?: number
  "first_seen_at": string
  "id": string
  "last_seen_at": string
  "publisher_count"?: number
  "status": string
  "story_family": string
}

export interface StoryUnlockRequest {
  "document_ids": Array<string>
}

export interface TrashItemState {
  "created_at": string
  "folder": string
  "id": string
  "item_count": number
  "kind": string
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
