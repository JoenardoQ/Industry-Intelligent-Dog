"""Validated command payloads for the local workbench API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic import HttpUrl


class DailyIdentity(BaseModel):
    date: str
    category: str
    key: str


class DeleteDailyRequest(BaseModel):
    items: list[DailyIdentity] = Field(max_length=5000)


class SourceCreate(BaseModel):
    category: str
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=2000)
    note: str = Field(default="", max_length=2000)
    tier: str = Field(default="representative", max_length=80)
    publisher_country: str = Field(default="", max_length=100)


class IndustryCreate(BaseModel):
    folder: str = Field(min_length=1, max_length=80)
    name: str = Field(default="", max_length=120)


class IndustryRename(BaseModel):
    folder: str = Field(min_length=1, max_length=80)
    name: str = Field(default="", max_length=120)


class GenerateRequest(BaseModel):
    action: Literal[
        "daily", "weekly", "monthly", "quarterly", "report",
        "deep_report", "impact", "lab", "bootstrap",
        "coverage", "history",
    ]
    kind: str = Field(default="", max_length=80)
    event: str = Field(default="", max_length=1000)
    provider: str = Field(default="", max_length=80)
    pipeline_mode: Literal["aggregate", "generate"] = "generate"


class AgentAssertion(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    citations: list[HttpUrl] = Field(min_length=1, max_length=50)


class AgentResultImport(BaseModel):
    task_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    agent_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    summary: str = Field(min_length=1, max_length=100_000)
    assertions: list[AgentAssertion] = Field(min_length=1, max_length=500)


class AgentResultReview(BaseModel):
    decision: Literal["reviewed", "rejected"]
    note: str = Field(default="", max_length=2000)


class CustomAgentProfile(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    name: str = Field(min_length=1, max_length=120)
    command: str = Field(min_length=1, max_length=80)
    args: list[str] = Field(default_factory=list, max_length=40)


class ScheduleUpdate(BaseModel):
    enabled: bool = False
    local_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    weekday: int = Field(default=0, ge=0, le=6)
    monthday: int = Field(default=1, ge=1, le=28)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=100)
    catch_up: bool = True
    pipeline_mode: Literal["aggregate", "generate"] = "generate"
    provider: str = Field(default="codex", min_length=1, max_length=80)


class StoryMergeRequest(BaseModel):
    source_story_id: str = Field(min_length=1, max_length=120)


class StorySplitRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)


class StoryUnlockRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=500)


class CoverageCellCreate(BaseModel):
    dimensions: dict[str, str]
    priority: int = Field(default=50, ge=0, le=100)
    status: Literal["gap", "thin", "covered", "paused"] = "gap"
    rationale: str = Field(default="", max_length=2000)


class CoverageAttemptCreate(BaseModel):
    manual_correction: Literal[True]
    actor: str = Field(default="local-user", min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(default="", max_length=2000)
    status: Literal["planned", "running", "completed", "failed", "stopped"] = "planned"
    source_yield: int = Field(default=0, ge=0)
    entity_yield: int = Field(default=0, ge=0)
    evidence: list[dict] = Field(default_factory=list, max_length=200)
    stopping_reason: str = Field(default="", max_length=2000)


class TrashRestoreRequest(BaseModel):
    desired_folder: str = Field(default="", max_length=80)


class JobAccepted(BaseModel):
    run_id: str
    status: str
    title: str = ""
    action: str = ""
    email_delivery: bool = False


class ArtifactState(BaseModel):
    """Common, inspectable metadata for every research artifact card."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    slug: str | None = None
    name: str | None = None
    title: str | None = None
    event: str | None = None
    generated_at: str | None = None
    window_end: str | None = None
    status: str | None = None
    provider: str | None = None
    model: str | None = None
    report_file: str | None = None
    path: str | None = None
    file: str | None = Field(default=None, alias="_file")
    key: str | None = Field(default=None, alias="_key")
    summary: str | None = None
    limitations: list[Any] = Field(default_factory=list)
    references: list[Any] = Field(default_factory=list)
    visualization: dict[str, Any] = Field(default_factory=dict)


class PeriodicArtifactsState(BaseModel):
    weekly: list[ArtifactState]
    monthly: list[ArtifactState]
    quarterly: list[ArtifactState]


class ProductsState(BaseModel):
    periodic: PeriodicArtifactsState
    reports: list[ArtifactState]
    deep_reports: list[ArtifactState]
    impacts: list[ArtifactState]


class ResearchState(BaseModel):
    lab: dict[str, Any]
    agenda: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    impacts: list[ArtifactState]


class ScheduleState(BaseModel):
    action: Literal["daily", "weekly", "monthly", "quarterly"]
    enabled: bool
    local_time: str
    weekday: int
    monthday: int
    timezone: str
    catch_up: bool
    pipeline_mode: Literal["aggregate", "generate"] = "generate"
    provider: str = "codex"
    last_period_key: str | None = None
    next_run_at: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    attempted_period_key: str | None = None
    retry_count: int = 0
    retry_after: str | None = None
    last_job_run_id: str | None = None
    last_artifact_path: str | None = None


class AutomationState(BaseModel):
    email_delivery: bool = False
    schedules: list[ScheduleState]


class StorySummaryState(BaseModel):
    id: str
    canonical_title: str
    story_family: str
    status: str
    clustering_version: str
    first_seen_at: str
    last_seen_at: str
    document_count: int = 0
    publisher_count: int = 0


class StoryListState(BaseModel):
    items: list[StorySummaryState]
    total: int


class StoryDocumentState(BaseModel):
    id: str
    title: str
    url: str
    abstract: str | None = None
    published_at: str | None = None
    origin: str | None = None
    category: str
    observed_date: str
    relation: str
    publisher_cluster: str | None = None
    editorially_locked: bool = False


class StoryReviewState(BaseModel):
    action: str
    actor: str
    details: dict[str, Any]
    occurred_at: str


class StoryDetailState(StorySummaryState):
    metadata: dict[str, Any] = Field(default_factory=dict)
    documents: list[StoryDocumentState]
    corroborated: bool
    reviews: list[StoryReviewState]
    claims: list[dict[str, Any]] = Field(default_factory=list)


class CoverageAttemptState(BaseModel):
    id: str
    cell_id: str
    query: str
    rationale: str
    status: str
    source_yield: int
    entity_yield: int
    evidence: list[Any]
    stopping_reason: str
    created_at: str
    updated_at: str


class CoverageCellState(BaseModel):
    id: str
    dimensions: dict[str, str]
    priority: int
    status: str
    rationale: str
    attempts: int
    source_yield: int
    entity_yield: int
    last_attempt_at: str | None = None
    updated_at: str
    created_at: str
    attempt_history: list[CoverageAttemptState] = Field(default_factory=list)


class CoverageSummaryState(BaseModel):
    total: int
    gaps: int
    source_yield: int
    entity_yield: int


class CoverageState(BaseModel):
    cells: list[CoverageCellState]
    summary: CoverageSummaryState


class HistoryHorizonState(BaseModel):
    horizon: Literal[
        "weekly", "monthly", "quarterly", "semiannual", "biennial", "fiveyear"
    ]
    window_start: str
    window_end: str
    target: int
    target_range: list[int]
    required_total: int
    admitted_total: int
    buckets_total: int
    buckets_covered: int
    required_buckets: int
    publisher_count: int
    ready: bool
    status: str
    updated_at: str | None = None
    attempts: int = 0


class HistoryCoverageState(BaseModel):
    items: list[HistoryHorizonState]


class TrashItemState(BaseModel):
    id: str
    kind: Literal["industry", "daily"]
    folder: str
    name: str
    created_at: str
    item_count: int


class TrashState(BaseModel):
    items: list[TrashItemState]
    total: int
    permanent_delete_available: bool


class RestoreState(BaseModel):
    kind: Literal["industry", "daily"]
    folder: str
    restored: int
    skipped: int


class RestorePreviewState(BaseModel):
    id: str
    kind: Literal["industry", "daily"]
    folder: str
    restorable: bool
    restore_count: int
    skip_count: int
    collisions: list[str]


class HealthState(BaseModel):
    status: str
    data_root: str
    database: bool
    active_jobs: int
    automation_running: bool
    session_required: bool


class AgentState(BaseModel):
    id: str
    name: str
    region: str
    commands: list[str]
    connection: str
    execution: str
    docs_url: str
    note: str
    installed: bool
    authenticated: bool | None = None
    ready: bool
    executable: str = ""
    detail: str = ""
    schedulable: bool = False


class ApiProviderState(BaseModel):
    id: str
    name: str
    region: str
    configured: bool
    ready: bool
    model: str = ""
    api_base: str = ""
    key_env: str
    default_model: str = ""
    docs_url: str = ""
    web_search: bool = False
    schedulable: bool = False


class McpConfigState(BaseModel):
    id: str
    name: str
    format: str
    value: str | dict[str, Any]


class SetupState(BaseModel):
    runtime_ready: bool
    data_root: str
    taskpack_ready: bool
    agents: list[AgentState]
    api_providers: list[ApiProviderState]
    mcp_command: list[str]
    mcp_configs: list[McpConfigState]
    agent_profiles: list[CustomAgentProfile] = Field(default_factory=list)
    privacy_note: str


class KnowledgeEntitySummary(BaseModel):
    id: str
    kind: str
    name: str
    name_en: str | None = None
    country: str | None = None
    role: str | None = None
    chain: str | None = None
    status: str
    confidence: float | None = None


class KnowledgeEntityPage(BaseModel):
    items: list[KnowledgeEntitySummary]
    total: int
    offset: int
    limit: int
    next_offset: int | None = None


class KnowledgeEntityDetail(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    kind: str
    canonical_name: str
    name_en: str | None = None
    country: str | None = None
    role: str | None = None
    chain: str | None = None
    status: str
    confidence: float | None = None
    aliases: list[dict[str, Any]]
    roles: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    evidence_count: int


class AuditState(BaseModel):
    id: int
    occurred_at: str
    actor: str
    action: str
    object_type: str
    object_id: str | None = None
    details: dict[str, Any]


class IndustryState(BaseModel):
    model_config = ConfigDict(extra="allow")
    folder: str
    name: str
    periodic_enabled: bool = False


class IndustryMutationState(BaseModel):
    folder: str
    name: str


class ArchiveState(BaseModel):
    archived_to: str


class OverviewState(BaseModel):
    industry: dict[str, Any]
    stats: dict[str, Any]
    chain: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    source_categories: dict[str, int]
    latest_document_date: str | None = None


class DailyState(BaseModel):
    items: list[dict[str, Any]]
    total: int
    next_cursor: str | None = None
    selection_scope: Literal["current_page"]
    dates: list[str]
    counts: dict[str, int]
    origins: dict[str, int]


class CountState(BaseModel):
    deleted: int | bool


class SourceMutationState(BaseModel):
    added: bool


class SourcesState(BaseModel):
    industry: str
    categories: dict[str, list[dict[str, Any]]]


class JobState(BaseModel):
    model_config = ConfigDict(extra="allow")
    run_id: str
    title: str = ""
    status: str
    updated_at: str = ""
    stalled: bool = False
    active: bool = False
    stage: str | None = None
    progress: float = 0.0
    artifact_path: str | None = None
    parent_run_id: str | None = None
    operation: str | None = None
    error: str | None = None


class JobOutputState(BaseModel):
    run_id: str
    output: str


class CancelState(BaseModel):
    cancelled: bool


class ShutdownState(BaseModel):
    status: Literal["stopping"]
