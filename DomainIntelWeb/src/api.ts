export { api, apiText } from './api/client'
export { artifactUrl } from './api/client'
export type { ClientPath, SessionRequestInit } from './api/client'

import type {
  AgentResultPage,
  AgentResultState,
  AgentState as GeneratedAgentState,
  AgentTaskState,
  AgendaItemState,
  ApiPath,
  ApiProviderState as GeneratedApiProviderState,
  ArtifactState,
  ArtifactVisualizationState,
  AuditState,
  AutomationState,
  BackgroundState,
  ChainEdgeState,
  ChainNodeState,
  CoverageCandidateState,
  CoverageCellState,
  CoverageReviewQueueState,
  CoverageRoundState,
  CoverageState,
  CustomAgentProfile,
  DailyItemState,
  DailyState,
  EntityCoverageCellState,
  EntityCoverageMatrixState,
  HealthState,
  HistoryCoverageState,
  HistoryHorizonState,
  IndustryBundleState,
  IndustryImportState,
  IndustryState,
  JobAccepted,
  JobState,
  KnowledgeEntityDetail as GeneratedKnowledgeEntityDetail,
  KnowledgeEntityPage as GeneratedKnowledgeEntityPage,
  KnowledgeEntitySummary,
  McpConfigState,
  OverviewState,
  ProductsState,
  ResearchState,
  RestorePreviewState,
  ScheduleState,
  SetupState,
  SourceCampaignDetail as GeneratedSourceCampaignDetail,
  SourceCampaignPage as GeneratedSourceCampaignPage,
  SourceCampaignState,
  SourceCandidateState,
  SourceItemState,
  SourcesState,
  StoryDetailState,
  StoryDocumentState,
  StorySummaryState,
  TrashItemState,
  WorkflowSettingsState,
} from './generated/openapi'

export type ContractPath = ApiPath
export type PageKey = 'overview' | 'daily' | 'knowledge' | 'products' | 'sources' | 'research' | 'jobs' | 'system'

export type Industry = IndustryState
export type IndustryBundle = IndustryBundleState
export type IndustryImportResult = IndustryImportState
export type DailyItem = DailyItemState
export type DailyPage = DailyState
export type ChainNode = ChainNodeState
export type ChainEdge = ChainEdgeState
export type Entity = KnowledgeEntitySummary
export type KnowledgeEntityPage = GeneratedKnowledgeEntityPage
export type KnowledgeEntityDetail = GeneratedKnowledgeEntityDetail
export type OverviewPayload = OverviewState
export type Visualization = ArtifactVisualizationState
export type ProductItem = ArtifactState
export type ProductsPayload = ProductsState
export type SourceItem = SourceItemState
export type SourcesPayload = SourcesState
export type SourceCampaignStatus = SourceCampaignState['status']
export type SourceCandidateStatus = SourceCandidateState['status']
export type SourceCampaign = SourceCampaignState
export type SourceCandidate = SourceCandidateState
export type SourceCampaignPage = GeneratedSourceCampaignPage
export type SourceCampaignDetail = GeneratedSourceCampaignDetail
export type EntityCoverageCell = EntityCoverageCellState
export type EntityCoverageMatrix = EntityCoverageMatrixState
export type CoverageRound = CoverageRoundState
export type CoverageCandidate = CoverageCandidateState
export type CoverageReviewQueue = CoverageReviewQueueState
export type AgendaItem = AgendaItemState
export type AgentTask = AgentTaskState
export type AgentResult = AgentResultState
export type AgentResultsPage = AgentResultPage
export type ResearchPayload = ResearchState
export type Job = JobState
export type HealthPayload = HealthState
export type AgentState = GeneratedAgentState
export type ApiProviderState = GeneratedApiProviderState
export type McpConfig = McpConfigState
export type SetupPayload = SetupState
export type AgentProfile = CustomAgentProfile
export type GenerateResult = JobAccepted
export type StorySummary = StorySummaryState
export type StoryDocument = StoryDocumentState
export type StoryDetail = StoryDetailState
export type CoverageCell = CoverageCellState
export type CoveragePayload = CoverageState
export type HistoryHorizon = HistoryHorizonState
export type HistoryCoveragePayload = HistoryCoverageState
export type Schedule = ScheduleState
export type AutomationPayload = AutomationState
export type BackgroundPayload = BackgroundState
export type TrashItem = TrashItemState
export type RestorePreview = RestorePreviewState
export type AuditRow = AuditState
export type WorkflowSettings = WorkflowSettingsState
