"""Validated command payloads for the local workbench API."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_serializer, model_validator
from pydantic import HttpUrl


AgentAssertionStatus = Literal[
    "draft_review_required", "rejected", "opinion", "submitted_for_verification",
    "candidate", "disputed", "accepted",
]
AgentResultStatus = Literal[
    "draft_review_required", "rejected", "opinion", "submitted_for_verification",
    "candidate", "disputed", "accepted",
]


class DailyIdentity(BaseModel):
    date: str
    category: str
    key: str


class DailyItemState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    title: str
    url: str
    abstract: str | None = None
    category: str
    date: str
    published_at: str | None = None
    display_source: str
    origin: str
    review_status: str | None = None
    evidence_status: str | None = None
    ranking_score: float | None = None
    identity: DailyIdentity


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


class IndustryBundleState(BaseModel):
    """Portable, credential-free snapshot of one industry's canonical data."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    exported_at: str
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    industry: dict[str, JsonValue]
    sources: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=5_000)
    documents: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=100_000)
    chain: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=5_000)
    chain_edges: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=20_000)
    entities: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=100_000)
    relations: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=200_000)
    claims: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=100_000)


class IndustryImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: str = Field(min_length=1, max_length=80)
    name: str = Field(default="", max_length=120)
    bundle: IndustryBundleState


class IndustryImportState(BaseModel):
    folder: str
    name: str
    imported: dict[str, int]


class GenerateRequest(BaseModel):
    action: Literal[
        "daily", "weekly", "monthly", "quarterly", "report",
        "deep_report", "impact", "lab", "bootstrap",
        "coverage", "history",
    ]
    kind: str = Field(default="", max_length=80)
    event: str = Field(default="", max_length=1000)
    provider: str = Field(default="", max_length=80)
    execution_mode: Literal["taskpack", "direct"] | None = None
    pipeline_mode: Literal["aggregate", "generate"] | None = None

    @model_validator(mode="after")
    def validate_execution(self):
        if self.execution_mode == "direct" and not self.provider.strip():
            raise ValueError("direct execution requires an explicit provider")
        if self.execution_mode == "taskpack" and self.provider.strip():
            raise ValueError("taskpack execution cannot select a direct provider")
        return self


class TextOffsetLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text_offset"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class HtmlSelectorLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["html_selector"]
    selector: str = Field(min_length=1, max_length=500)


class PdfPageLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["pdf_page"]
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class ApiFieldLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["api_field"]
    path: str = Field(min_length=1, max_length=1000)


AgentLocator = Annotated[
    TextOffsetLocator | HtmlSelectorLocator | PdfPageLocator | ApiFieldLocator,
    Field(discriminator="type")]


class AgentCitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    role: Literal["support", "conversion_benchmark"] = "support"
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    locator: AgentLocator | None = None


class AgentAtomicAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=500)
    subject_id: str | None = Field(default=None, max_length=160)
    predicate: str = Field(min_length=1, max_length=160)
    object: Any
    time: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=1, max_length=160)
    value: float | int | str | None = None
    unit: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, max_length=20)
    period: str | None = Field(default=None, max_length=160)
    statistical_definition: str | None = Field(default=None, max_length=500)
    qualifiers: dict[str, Any] = Field(default_factory=dict)


class AgentAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20_000)
    type: Literal[
        "unspecified", "identity", "regulatory_status", "formal_company_disclosure",
        "company_disclosure", "event", "transaction", "value_chain_relationship",
        "market_size", "market_share", "valuation", "unofficial_statistics",
        "financial", "financial_figure", "technical", "technical_performance",
        "causal", "causality", "forecast", "forecast_estimate", "estimate",
        "investment", "investment_judgment", "opinion",
    ] = "unspecified"
    citations: list[HttpUrl | AgentCitationInput] = Field(min_length=1, max_length=20)
    atomic: AgentAtomicAssertion | None = None

    @model_serializer(mode="wrap")
    def _compact_optional_atomic(self, handler):
        value = handler(self)
        if self.atomic is None:
            value.pop("atomic", None)
        return value


class AgentResultImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    agent_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    summary: str = Field(min_length=1, max_length=100_000)
    assertions: list[AgentAssertion] = Field(min_length=1, max_length=100)
    generation_call_id: str | None = Field(default=None, max_length=160)

    @model_serializer(mode="wrap")
    def _compact_optional_generation_call(self, handler):
        value = handler(self)
        if self.generation_call_id is None:
            value.pop("generation_call_id", None)
        return value


class AgentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assertion_id: str = Field(pattern=r"^aas_[0-9a-f]{24}$")
    decision: Literal["rejected", "opinion", "submitted_for_verification"]
    note: str = Field(default="", max_length=2000)


class CustomAgentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    name: str = Field(min_length=1, max_length=120)
    command: str = Field(min_length=1, max_length=80)
    args: list[str] = Field(default_factory=list, max_length=40)
    executable_path: str | None = Field(default=None, max_length=4096)
    capability_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9._-]{1,80}$")


class AgentCapabilityState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: Literal["agent", "api", "bridge"]
    region: str
    connection: Literal["native_cli", "api", "mcp", "taskpack", "restricted_cli"]
    execution_level: Literal["direct", "handoff", "import_only"]
    auth: str
    web_access: bool | None = None
    structured_output: bool
    schedulable: bool
    docs_url: str
    note: str
    commands: list[str]


class AgentCapabilityPage(BaseModel):
    items: list[AgentCapabilityState]
    total: int = Field(ge=0)


class AgentDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(default="", max_length=32_768)
    selected_executables: list[Annotated[str, Field(max_length=4096)]] = Field(
        default_factory=list, max_length=32)


class AgentDiscoveryState(AgentCapabilityState):
    installed: bool
    authenticated: bool | None = None
    version_verified: bool
    ready: bool
    executable: str
    status: Literal[
        "missing", "detected", "ready", "incompatible", "timeout", "output_limit",
        "auth_failed", "handoff", "import_only", "invalid_configuration",
        "not_configured",
    ]
    failure_code: str | None = None
    version: str = ""
    detail: str


class AgentDiscoveryPage(BaseModel):
    items: list[AgentDiscoveryState]
    total: int = Field(ge=0)


class ExecutableFingerprintState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(max_length=4096)
    canonical_path: str = Field(max_length=4096)
    device: int
    inode: int
    size: int = Field(ge=0)
    mtime_ns: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AgentDiagnosticState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    connection: Literal["native_cli", "api", "mcp", "taskpack", "restricted_cli"]
    execution_level: Literal["direct", "handoff", "import_only"]
    installed: bool
    version_verified: bool
    authenticated: bool | None = None
    ready: bool
    status: Literal[
        "missing", "detected", "ready", "incompatible", "timeout", "output_limit",
        "auth_failed", "handoff", "import_only", "invalid_configuration",
        "not_configured", "busy",
    ]
    failure_code: str | None = None
    executable: str = ""
    resolved_executable: str = ""
    executable_fingerprint: ExecutableFingerprintState | None = None
    version: str = ""
    detail: str


class AgentProfilePage(BaseModel):
    items: list[CustomAgentProfile] = Field(max_length=100)
    total: int = Field(ge=0, le=100)
    limit: Literal[100] = 100


class AgentProfileDeleteState(BaseModel):
    removed: bool


class AgentTaskState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    industry: str
    agenda_id: str
    title: str
    rationale: str
    queries: list[str]
    acceptance: dict[str, Any]
    budget: int
    constraints: dict[str, Any]
    status: str
    created_at: str
    result_artifact_id: str | None = None
    run_id: str | None = None


class AgentTaskPage(BaseModel):
    industry: str
    items: list[AgentTaskState]
    total: int
    offset: int
    limit: int = Field(ge=1, le=100)
    next_offset: int | None = None


class AgentResultContractAtomic(BaseModel):
    subject: Literal["string"]
    subject_id: Literal["canonical-entity-id"]
    predicate: Literal["string"]
    object: Literal["value"]
    time: Literal["ISO-8601 or explicit period"]
    region: Literal["string"]
    value: Literal["number|null"]
    unit: Literal["string|null"]
    currency: Literal["ISO-4217|null"]
    period: Literal["string|null"]
    statistical_definition: Literal["string|null"]
    qualifiers: dict[str, Any]


class AgentResultContractCitation(BaseModel):
    url: Literal["https://..."]
    role: Literal["support|conversion_benchmark"]
    content_hash: Literal["sha256-hex"]
    locator: TextOffsetLocator


class AgentResultContractAssertion(BaseModel):
    text: Literal["string"]
    type: Literal[
        "identity|event|market_size|financial|technical_performance|causal|forecast|opinion"]
    atomic: AgentResultContractAtomic
    citations: list[AgentResultContractCitation]


class AgentResultContract(BaseModel):
    status: Literal["draft_review_required"]
    summary: Literal["string"]
    generation_call_id: Literal["unique-generation-call-id"]
    assertions: list[AgentResultContractAssertion]


class AgentTaskExport(BaseModel):
    schema_version: Literal[1]
    industry: str
    task: AgentTaskState
    result_contract: AgentResultContract


class AgentCitationState(BaseModel):
    id: str
    url: str
    canonical_url: str
    reachability: str
    source_id: str | None = None
    document_id: str | None = None
    snapshot_id: str | None = None
    verified_at: str | None = None


class AgentAssertionState(BaseModel):
    id: str
    text: str
    type: str
    status: AgentAssertionStatus
    claim_id: str | None = None
    verification: "AgentVerificationChecks | None" = None
    citations: list[AgentCitationState]


class AgentResultState(BaseModel):
    result_id: str
    industry: str
    task_id: str
    agent_id: str
    summary: str
    content_sha256: str
    status: AgentResultStatus
    original_file: str
    created_at: str
    assertions: list[AgentAssertionState]
    duplicate: bool = False
    path: str | None = None


class AgentResultPage(BaseModel):
    industry: str
    items: list[AgentResultState]
    total: int
    offset: int
    limit: int = Field(ge=1, le=100)
    next_offset: int | None = None


class AgentLocatorProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    url: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: AgentLocator
    excerpt: str


class AgentGateFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    reason: str
    status_code: int | None = None
    failure_code: Literal["invalid_locator"] | None = None
    invalid_locator_type: str | None = None
    content_hash_present: bool | None = None


class AgentGatePublisher(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    name: str
    domain: str
    owner_cluster: str
    verification_status: str


class AgentGateAtomic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    subject_id: str | None = None
    predicate: str
    object: JsonValue
    time: str
    region: str
    value: int | float | str | None = None
    unit: str | None = None
    currency: str | None = None
    period: str | None = None
    statistical_definition: str | None = None
    qualifiers: dict[str, JsonValue] = Field(default_factory=dict)


class AgentGateConversion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_value: int | float | str | None = None
    target_value: int | float | str | None = None
    formula: str | None = None
    rate: str | None = None
    tolerance: str
    benchmark_source: str
    tolerance_status: Literal["default_unverified"] | None = None


class AgentGateClaimProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: str | None = None
    predicate: str
    object: JsonValue
    qualifiers: dict[str, JsonValue]
    valid_from: str
    valid_to: str


class AgentGateEvidenceProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str
    url: str
    content_hash: str
    role: Literal["support", "conversion_benchmark", "invalid"]
    published_at: str
    excerpt: str
    publisher_cluster: str
    relation: Literal["supports", "qualifies"]
    locator: AgentLocator
    reachable: bool


class AgentResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_count: int
    fetched_bytes: int
    excerpt_bytes: int
    single_excerpt_bytes: int
    approximate_provider_tokens: int
    stored_verification_bytes: int


class AgentBudgetTruncation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_bytes: int
    final_bytes: int
    evidence_id_count: int
    locator_count: int
    failure_count: int


class AgentGateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["passed", "failed", "partial", "unknown", "not_applicable"]
    reason: str
    evidence_ids: list[str]
    locators: list[AgentLocatorProvenance]
    atomic: AgentGateAtomic | None = None
    failures: list[AgentGateFailure] | None = None
    publishers: list[AgentGatePublisher] | None = None
    publication_times: list[str] | None = None
    entity_ids: list[str] | None = None
    expected_entity_id: str | None = None
    generation_call_id: str | None = None
    generator_id: str | None = None
    independent_verifiers: list[str] | None = None
    evaluator_mode: str | None = None
    errors: list[str] | None = None
    retryable: bool | None = None
    conversions: list[AgentGateConversion] | None = None
    declared_type: str | None = None
    inferred_type: str | None = None
    signals: list[str] | None = None
    inconsistent_signals: list[str] | None = None
    independent_assertion_types: list[str] | None = None
    assertion_type: str | None = None
    high_risk_signals: list[str] | None = None
    independent_clusters: list[str] | None = None
    conflicting_claim_ids: list[str] | None = None
    claim: AgentGateClaimProjection | None = None
    evidence: list[AgentGateEvidenceProjection] | None = None
    citation_count: int | None = None
    fetched_bytes: int | None = None
    excerpt_bytes: int | None = None
    approximate_provider_tokens: int | None = None
    limits: AgentResourceLimits | None = None
    budget_truncation: AgentBudgetTruncation | None = None


class AgentSemanticCheck(AgentGateCheck):
    decision: Literal["supported", "partial", "contradicted", "unknown"]


class AgentVerificationChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atomization: AgentGateCheck
    reachability: AgentGateCheck
    publisher_identity: AgentGateCheck
    publication_time: AgentGateCheck
    entity_alignment: AgentGateCheck
    locator_integrity: AgentGateCheck
    generation_provenance: AgentGateCheck
    verifier_independence: AgentGateCheck
    semantic_support: AgentSemanticCheck
    numeric_consistency: AgentGateCheck
    type_classification: AgentGateCheck
    type_policy: AgentGateCheck
    resource_budget: AgentGateCheck
    corroboration: AgentGateCheck
    conflict: AgentGateCheck
    fact_projection: AgentGateCheck


AgentAssertionState.model_rebuild()


class AgentVerificationDecisionState(BaseModel):
    assertion_id: str
    disposition: Literal["candidate", "disputed", "accepted", "rejected"]
    claim_id: str | None = None
    checks: AgentVerificationChecks


class AgentAggregateTruncation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_bytes: int
    final_bytes: int
    decision_count: int


class AgentVerificationState(BaseModel):
    result_id: str
    status: Literal["verified", "partial", "retryable", "no_submitted_assertions"]
    detail: str
    decisions: list[AgentVerificationDecisionState]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=10)
    next_offset: int | None = Field(default=None, ge=0)
    response_truncation: AgentAggregateTruncation | None = None


class ScheduleUpdate(BaseModel):
    enabled: bool = False
    local_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    weekday: int = Field(default=0, ge=0, le=6)
    monthday: int = Field(default=1, ge=1, le=28)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=100)
    catch_up: bool = True
    pipeline_mode: Literal["aggregate", "generate"] = "generate"
    provider: str = Field(default="", max_length=80)


class StoryMergeRequest(BaseModel):
    source_story_id: str = Field(min_length=1, max_length=120)


class StorySplitRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)


class StoryUnlockRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=500)


class StoryIgnoreRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


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


class ChainNodeState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    name: str
    label: str | None = None
    description: str = ""
    order: int = 0
    status: str = "candidate"
    coverage_status: str = "unknown"
    entity_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    evidenced_entities: int = Field(default=0, ge=0)


class ChainEdgeState(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    src_node_id: str
    dst_node_id: str
    src_name: str
    dst_name: str
    relation: str
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float | None = None
    status: str
    effect: str | None = None
    lag_days: int | None = None
    evidence_count: int = Field(default=0, ge=0)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class DirectedGraphState(BaseModel):
    nodes: list[ChainNodeState] = Field(default_factory=list)
    edges: list[ChainEdgeState] = Field(default_factory=list)


class ArtifactVisualizationState(BaseModel):
    model_config = ConfigDict(extra="allow")
    directed_graph: DirectedGraphState | None = None


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
    portable_file: str | None = None
    manifest_file: str | None = None
    quality_file: str | None = None
    quality: dict[str, Any] = Field(default_factory=dict)
    visualization: ArtifactVisualizationState = Field(
        default_factory=ArtifactVisualizationState)


class PeriodicArtifactsState(BaseModel):
    weekly: list[ArtifactState]
    monthly: list[ArtifactState]
    quarterly: list[ArtifactState]


class ProductsState(BaseModel):
    periodic: PeriodicArtifactsState
    reports: list[ArtifactState]
    deep_reports: list[ArtifactState]
    impacts: list[ArtifactState]


class PortableExportState(BaseModel):
    path: str
    status: str
    quality: dict[str, Any] = Field(default_factory=dict)


class AgendaItemState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    question: str | None = None
    title: str | None = None
    rationale: str | None = None
    note: str | None = None
    status: str | None = None


class ResearchEvidenceState(BaseModel):
    nodes: list[Any] = Field(default_factory=list)


class ResearchLabState(BaseModel):
    model_config = ConfigDict(extra="allow")
    evidence: ResearchEvidenceState = Field(default_factory=ResearchEvidenceState)
    scenarios: list[Any] = Field(default_factory=list)


class ResearchTaskState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    title: str | None = None
    status: str | None = None
    budget: int | float | None = None


class ResearchState(BaseModel):
    lab: ResearchLabState
    agenda: list[AgendaItemState]
    tasks: list[ResearchTaskState]
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
    provider: str = ""
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
    last_period_identity: str | None = None
    attempted_period_identity: str | None = None
    runtime_status: Literal[
        "idle", "running", "completed", "partial", "failed", "paused",
        "cancelled", "interrupted"] = "idle"
    pause_reason: str = ""
    max_retries: int = Field(default=5, ge=1, le=100)
    last_origin: str = ""
    last_window_start: str | None = None
    last_window_end: str | None = None
    last_window_timezone: str | None = None
    last_success_boundary: str | None = None


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
    document_count: int
    publisher_count: int


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


class StoryClaimEvidenceState(BaseModel):
    relation: str
    document_title: str | None = None
    document_url: str | None = None


class StoryClaimState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    predicate: str
    object: Any
    status: str
    evidence: list[StoryClaimEvidenceState]


class StoryDetailState(StorySummaryState):
    metadata: dict[str, Any] = Field(default_factory=dict)
    documents: list[StoryDocumentState]
    corroborated: bool
    reviews: list[StoryReviewState]
    claims: list[StoryClaimState]


class MomentumDeltaState(BaseModel):
    rank: int
    score: float
    independent_publishers: int
    evidence_strength: float


class MomentumObservationState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    intelligence_date: str
    observed_at: str | None = None
    rank: int = Field(ge=1)
    score: float
    independent_publishers: int = Field(ge=0)
    evidence_strength: float = Field(ge=0)
    classification: str
    algorithm_version: str
    status: Literal["new", "heating", "tracking", "cooling", "unresolved"]
    deltas: MomentumDeltaState | None = None
    missing_days: int = Field(ge=0)
    algorithm_segment_started: bool
    seven_day_trend: MomentumDeltaState
    raw_observation_link: str


class StoryMomentumState(BaseModel):
    story_id: str
    status: Literal["new", "heating", "tracking", "cooling", "unresolved"]
    first_appearance: str | None = None
    last_observation: str | None = None
    timeline: list[MomentumObservationState]
    raw_observation_links: list[str]


class StoryMomentumBatchState(BaseModel):
    items: list[StoryMomentumState]
    total: int = Field(ge=0)


class DriftMetricState(BaseModel):
    metric: str
    window_days: Literal[7, 30]
    algorithm_version: str
    dimensions: dict[str, Any]
    value: float | None = None
    numerator: float
    denominator: float
    baseline: float | None = None
    baseline_denominator: float
    delta: float | None = None
    threshold: float
    status: Literal["stable", "degraded", "insufficient_data"]
    raw_observation_links: list[str]
    diagnosis: str


class DriftSegmentState(BaseModel):
    algorithm_version: str
    metric: str
    dimensions: dict[str, Any]
    start: str
    end: str
    observation_count: int = Field(ge=1)


class ColumnarPrototypeState(BaseModel):
    prototype_recommended: bool
    triggers: dict[str, bool]
    authority: Literal["sqlite"]
    write_path: Literal["sqlite_only"]
    prototype_policy: str


class QualityDriftState(BaseModel):
    as_of: str
    metrics: list[DriftMetricState]
    segments: list[DriftSegmentState]
    alert_count: int = Field(ge=0)
    columnar_prototype: ColumnarPrototypeState


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


SourceCampaignStatus = Literal["planned", "running", "paused", "converged", "failed"]
SourceCandidateStatus = Literal[
    "candidate", "manual_review", "active", "reserve", "rejected"]


class SourceCampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[str] = Field(min_length=1, max_length=9)
    budget: int = Field(default=120, ge=1, le=10_000)


class SourceCandidateReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["manual_review", "active", "reserve", "rejected"]
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)


class SourceReassessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["active", "manual", "reserve", "rejected"]
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)


class SourceCampaignExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str | None = Field(default=None, min_length=1, max_length=80)


class CoverageExpansionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Round number and history are derived from the repository; clients cannot forge them.
    pass


class CoverageExpansionExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str | None = Field(default=None, min_length=1, max_length=80)


class EntityCandidateReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "manual_review", "rejected"]
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)


class SourceQueryState(BaseModel):
    id: str
    campaign_id: str
    round_no: int
    language: str
    family: str
    dimensions: dict[str, Any]
    query: str
    outcome: dict[str, Any]
    created_at: str


class SourceReviewState(BaseModel):
    model_config = ConfigDict(extra="allow")
    actor: str = ""
    reason: str = ""
    decision: str = ""


class SourceCandidateState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    campaign_id: str
    name: str
    url: str
    canonical_url: str
    category: str
    score: float
    status: SourceCandidateStatus
    selection_reason: str = ""
    status_reason: str = ""
    query_ids: list[str] = Field(default_factory=list)
    review: SourceReviewState | None = None


class SourceCandidatePage(BaseModel):
    items: list[SourceCandidateState]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    next_offset: int | None = Field(default=None, ge=0)


class SourceGapState(BaseModel):
    category: str
    current: int = Field(ge=0)
    target: int = Field(ge=1)
    gap: int = Field(ge=0)
    query_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    rejection_reasons: dict[str, int]
    explanation: str


class SourceCampaignState(BaseModel):
    id: str
    industry_id: str
    targets: list[str]
    status: SourceCampaignStatus
    rounds: int = Field(ge=0)
    budget: int = Field(ge=1)
    stopping_reason: str
    created_at: str
    updated_at: str


class SourceCampaignPage(BaseModel):
    items: list[SourceCampaignState]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    next_offset: int | None = Field(default=None, ge=0)


class OperationLogState(BaseModel):
    model_config = ConfigDict(extra="allow")
    at: str
    level: str = "info"
    message: str


class CampaignRoundHistoryState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    round_no: int = Field(ge=1)
    status: str
    outcome: dict[str, Any] = Field(default_factory=dict)
    log: list[OperationLogState]


class SourceCampaignDetail(SourceCampaignState):
    candidate_page: SourceCandidatePage
    query_ledger: list[SourceQueryState]
    source_gaps: list[SourceGapState]
    round_history: list[CampaignRoundHistoryState]


class SourceReassessmentState(BaseModel):
    source_id: str
    state: Literal["active", "manual", "reserve", "rejected"]
    review: dict[str, str]


class RelationEvidenceState(BaseModel):
    edge_id: str
    relation: str
    evidence_count: int = Field(ge=0)


class EntityCoverageCellState(BaseModel):
    id: str
    source_type: str
    subdomain: str
    chain_stage: str
    entity_type: str
    region: Literal["china", "foreign"]
    current: int = Field(ge=0)
    target: int = Field(ge=1)
    gap: int = Field(ge=0)
    status: str
    high_value: bool
    priority: int
    explanation: str
    relation_evidence: list[RelationEvidenceState]


class EntityCoverageMatrixState(BaseModel):
    industry: str
    completeness_proven: bool
    gap_count: int = Field(ge=0)
    algorithm_version: str
    cells: list[EntityCoverageCellState]


class CoverageFrontierState(BaseModel):
    round_id: str
    round_no: int = Field(ge=1)
    status: Literal["planned", "running", "paused", "completed", "converged", "failed"]
    cells: list[dict[str, Any]]
    entity_queries: list[dict[str, Any]]
    relation_queries: list[dict[str, Any]]
    stopping_reason: str | None = None


class CoverageQueryState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    kind: Literal["entity", "relation"] | None = None
    query: str
    status: str


class CoverageRoundState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    industry_id: str
    round_no: int = Field(ge=1)
    status: Literal["planned", "running", "paused", "completed", "converged", "failed"]
    frontier: list[dict[str, Any]]
    outcome: dict[str, Any]
    log: list[OperationLogState]
    queries: list[CoverageQueryState] = Field(default_factory=list)
    stopping_reason: str
    created_at: str
    updated_at: str


class CoverageCandidateState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    industry_id: str
    round_id: str
    query_id: str
    cell_id: str
    canonical_key: str
    payload: dict[str, Any]
    status: Literal["candidate", "manual_review", "accepted", "rejected"]
    status_reason: str
    created_at: str
    updated_at: str
    document_id: str | None = None
    assertion_id: str | None = None
    entity_id: str | None = None


class CoverageReviewQueueState(BaseModel):
    entities: list[CoverageCandidateState]
    relations: list[CoverageCandidateState]


class EntityCandidateReviewState(BaseModel):
    candidate_id: str
    decision: Literal["created", "merged", "manual_review", "rejected"]
    reason: str
    entity_id: str | None = None
    review: dict[str, str]


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


class WorkflowSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str | None = Field(default=None, min_length=1, max_length=80)
    execution_mode: Literal["taskpack", "direct"] | None = None
    pipeline_mode: Literal["aggregate", "generate"] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one workflow setting is required")
        return self


class WorkflowSettingsState(BaseModel):
    provider: str
    execution_mode: Literal["taskpack", "direct"]
    pipeline_mode: Literal["aggregate", "generate"]
    provenance: dict[str, str]
    layers: list[dict[str, Any]]


class BackgroundServiceState(BaseModel):
    installed: bool
    enabled: bool
    platform: str
    interval_minutes: int = Field(default=15, ge=5, le=1440)
    error_category: str = ""


class WorkerWakeupState(BaseModel):
    id: str
    owner: str
    origin: str
    started_at: str
    finished_at: str | None = None
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)


class BackgroundPermissionState(BaseModel):
    folder: str
    provider: str
    operation: str
    allowed: bool
    granted_by: str = ""
    granted_at: str = ""
    revoked_by: str | None = None
    revoked_at: str | None = None
    updated_at: str


class BackgroundPermissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder: str = Field(min_length=1, max_length=80)
    provider: str = Field(min_length=1, max_length=80)
    operation: str = Field(min_length=1, max_length=80)
    allowed: bool
    reason: str = Field(default="User changed background permission", max_length=1000)


class BackgroundPermissionMutation(BaseModel):
    folder: str
    provider: str
    operation: str
    allowed: bool
    affected_run_ids: list[str] = Field(default_factory=list)
    updated_at: str


class BackgroundScheduleErrorState(BaseModel):
    folder: str
    action: str
    runtime_status: str
    error: str
    pause_reason: str
    retry_after: str | None = None


class BackgroundState(BaseModel):
    service: BackgroundServiceState
    last_wakeup: WorkerWakeupState | None = None
    next_run_at: str | None = None
    permissions: list[BackgroundPermissionState]
    schedule_errors: list[BackgroundScheduleErrorState]
    email_delivery: Literal[False] = False


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
    auth_type: Literal["bearer", "api_key_header"]
    auth_configurable: bool = False
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


class EntityAliasState(BaseModel):
    model_config = ConfigDict(extra="allow")
    alias: str
    language: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


class EntityRoleState(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    chain: str
    status: str
    confidence: float | None = None
    evidence_count: int = 0
    valid_from: str | None = None
    valid_to: str | None = None


class EntityRelationState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    predicate: str
    src_entity_id: str
    dst_entity_id: str
    src_name: str
    dst_name: str
    confidence: float | None = None
    valid_from: str | None = None
    valid_to: str | None = None


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
    aliases: list[EntityAliasState]
    roles: list[EntityRoleState]
    relations: list[EntityRelationState]
    claims: list[StoryClaimState]
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


class OverviewIndustryState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    name: str | None = None
    name_en: str | None = None
    description: str | None = None
    status: str | None = None
    references: list[Any] = Field(default_factory=list)


class OverviewStatsState(BaseModel):
    model_config = ConfigDict(extra="allow")
    sources: int = Field(ge=0)
    documents: int = Field(ge=0)
    entities: int = Field(ge=0)
    candidate_entities: int = Field(default=0, ge=0)
    relations: int = Field(ge=0)
    claims: int = Field(default=0, ge=0)
    verified_claims: int = Field(default=0, ge=0)
    evidence: int = Field(default=0, ge=0)
    events: int = Field(default=0, ge=0)
    chain_nodes: int = Field(default=0, ge=0)
    empty_chain_nodes: int = Field(default=0, ge=0)


class OverviewState(BaseModel):
    industry: OverviewIndustryState
    stats: OverviewStatsState
    chain: list[ChainNodeState]
    chain_edges: list[ChainEdgeState]
    entities: list[KnowledgeEntitySummary]
    source_categories: dict[str, int]
    latest_document_date: str | None = None


class DailyState(BaseModel):
    items: list[DailyItemState]
    total: int
    next_cursor: str | None = None
    selection_scope: Literal["current_page"]
    dates: list[str]
    counts: dict[str, int]
    origins: dict[str, int]
    window_start: str
    window_end: str
    timezone: str
    window_reason: Literal["previous_local_day_04_to_now"]


class CountState(BaseModel):
    deleted: int | bool


class SourceMutationState(BaseModel):
    added: bool


class SourceHealthState(BaseModel):
    model_config = ConfigDict(extra="allow")
    adapter: str | None = None
    status: str
    last_checked_at: str | None = None
    last_success_at: str | None = None
    last_good_at: str | None = None
    retry_after: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    error_code: str | None = None
    error_message: str | None = None


class SourceItemState(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    category: str
    name: str
    url: str
    note: str | None = None
    selection_reason: str | None = None
    tier: str | None = None
    publisher_country: str | None = None
    origin: str | None = None
    health: SourceHealthState | None = None
    monitoring_status: str | None = None
    governance_role: str | None = None
    governance_reason: str | None = None
    governance_score: float | None = None


class SourcesState(BaseModel):
    industry: str
    categories: dict[str, list[SourceItemState]]


class JobTimeWindowState(BaseModel):
    start: str | None = None
    end: str | None = None
    timezone: str | None = None


class JobState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    title: str = ""
    status: str
    updated_at: str = ""
    stalled: bool = False
    active: bool = False
    stage: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    progress_mode: Literal["determinate", "indeterminate"] = "indeterminate"
    elapsed_seconds: int = Field(default=0, ge=0)
    result_kind: Literal["artifact", "local_data", "task_package", "unknown"] = "unknown"
    artifact_path: str | None = None
    parent_run_id: str | None = None
    operation: str | None = None
    error: str | None = None
    error_category: str = ""
    origin: Literal["app", "manual", "system_schedule", "background_worker"] = "app"
    provider: str = "local"
    model: str = ""
    time_window: JobTimeWindowState = Field(default_factory=JobTimeWindowState)
    heartbeat_at: str | None = None
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    request_dispatched_at: str | None = None
    recovery_actions: list[Literal["cancel", "retry", "resume"]] = Field(
        default_factory=list)


class JobOutputState(BaseModel):
    run_id: str
    output: str


class CancelState(BaseModel):
    cancelled: bool


class ShutdownState(BaseModel):
    status: Literal["stopping"]
