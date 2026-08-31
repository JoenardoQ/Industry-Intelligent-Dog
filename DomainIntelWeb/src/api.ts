import type { ApiPath, AuditState, HealthState, RestorePreviewState } from './generated/openapi'

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const capability = sessionStorage.getItem('intdog.session') || ''
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json',
      ...(capability ? { 'X-IntDog-Session': capability } : {}),
      ...(init?.headers || {}) },
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try { detail = (await response.json()).detail || detail } catch { /* keep HTTP detail */ }
    throw new Error(detail)
  }
  const value: unknown = await response.json()
  validateResponse(path, init?.method || 'GET', value)
  return value as T
}

export type ContractPath = ApiPath

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireKeys(path: string, value: unknown, keys: string[]) {
  if (!record(value) || keys.some(key => !(key in value))) {
    throw new Error(`API contract mismatch at ${path}: expected ${keys.join(', ')}`)
  }
}

function validateResponse(path: string, method: string, value: unknown) {
  const route = path.split('?', 1)[0]
  if (method.toUpperCase() !== 'GET') return
  if (route === '/industries' || route === '/jobs') {
    if (!Array.isArray(value)) throw new Error(`API contract mismatch at ${route}: expected array`)
    return
  }
  if (route === '/health') return requireKeys(route, value, ['status', 'data_root', 'database', 'active_jobs'])
  if (route === '/setup') return requireKeys(route, value, ['runtime_ready', 'data_root', 'taskpack_ready', 'agents', 'api_providers'])
  if (route.endsWith('/overview')) return requireKeys(route, value, ['industry', 'stats', 'chain', 'entities', 'source_categories'])
  if (route.endsWith('/daily')) return requireKeys(route, value, ['items', 'total', 'next_cursor', 'selection_scope'])
  if (route.endsWith('/products')) return requireKeys(route, value, ['periodic', 'reports', 'deep_reports', 'impacts'])
  if (route.endsWith('/sources')) return requireKeys(route, value, ['industry', 'categories'])
  if (route.endsWith('/research')) return requireKeys(route, value, ['lab', 'agenda', 'tasks', 'impacts'])
  if (route.endsWith('/history')) return requireKeys(route, value, ['items'])
  if (/^\/jobs\/[^/]+\/output$/.test(route)) return requireKeys(route, value, ['run_id', 'output'])
}

export type Industry = { folder: string; name: string; periodic_enabled: boolean }
export type PageKey = 'overview' | 'daily' | 'products' | 'sources' | 'research' | 'jobs' | 'system'

export type DailyItem = {
  id: string; title: string; url: string; abstract?: string; category: string;
  date: string; published_at?: string; display_source: string; origin: string;
  identity: { date: string; category: string; key: string };
}

export type DailyPage = {
  items: DailyItem[]
  total: number
  next_cursor: string | null
  selection_scope: 'current_page'
  dates: string[]
  counts: Record<string, number>
  origins: Record<string, number>
}

export type ChainNode = {
  id?: string; name: string; label?: string; description?: string;
  entity_count?: number; coverage_status?: string
}
export type Entity = {
  id: string; name: string; kind: string; chain?: string; role?: string;
  country?: string; confidence?: number
}
export type KnowledgeEntityPage = { items: Entity[]; total: number; offset: number;
  limit: number; next_offset: number | null }
export type KnowledgeEntityDetail = {
  id:string; canonical_name:string; name_en?:string; kind:string; country?:string;
  role?:string; chain?:string; status:string; confidence?:number;
  aliases:{alias:string}[]; roles:{role:string;chain:string;status:string}[];
  relations:{id:string;predicate:string;src_entity_id:string;dst_entity_id:string;
    src_name:string;dst_name:string;confidence?:number}[];
  claims:{id:string;predicate:string;object:unknown;status:string;
    evidence:{document_title?:string;document_url?:string;relation:string}[]}[];
  evidence_count:number
}
export type OverviewPayload = {
  industry: { name?: string; description?: string }
  stats: { sources: number; documents: number; entities: number; relations: number }
  chain: ChainNode[]; entities: Entity[]; source_categories: Record<string, number>
  latest_document_date?: string | null
}
export type Visualization = { directed_graph?: { nodes: ChainNode[] } }
export type ProductItem = {
  id?: string; _key?: string; name?: string; title?: string;
  generated_at?: string; window_end?: string; status?: string;
  report_file?: string; path?: string; _file?: string; summary?: string;
  visualization?: Visualization
}
export type ProductsPayload = {
  periodic: { weekly: ProductItem[]; monthly: ProductItem[]; quarterly: ProductItem[] }
  reports: ProductItem[]; deep_reports: ProductItem[]; impacts: ProductItem[]
}
export type SourceHealth = {
  adapter?: string | null; status: string; last_checked_at?: string | null;
  last_success_at?: string | null; last_good_at?: string | null;
  retry_after?: string | null; consecutive_failures: number;
  error_code?: string | null; error_message?: string | null
}
export type SourceItem = {
  id?: string; category: string; name: string; url: string; note?: string;
  selection_reason?: string; tier?: string; publisher_country?: string;
  origin?: string; health?: SourceHealth; monitoring_status?: string;
  governance_role?: string; governance_reason?: string; governance_score?: number
}
export type SourcesPayload = { industry: string; categories: Record<string, SourceItem[]> }
export type AgendaItem = {
  id: string; question?: string; title?: string; rationale?: string;
  note?: string; status?: string
}
export type AgentTask = { id:string; title?:string; rationale?:string; status:string;
  queries?:string[]; budget?:number; result_artifact_id?:string }
export type AgentResult = { task_id:string; agent_id:string; summary:string;
  assertions:{text:string;citations:string[]}[]; status:string; duplicate?:boolean; path?:string;
  result_id:string; created_at:string; review?:{decision:string;note:string;reviewed_at:string} }
export type AgentResultsPage = {items:AgentResult[];total:number;offset:number;limit:number;next_offset:number|null}
export type ResearchPayload = {
  lab?: { evidence?: { nodes?: unknown[] }; scenarios?: unknown[] }
  agenda: AgendaItem[]; tasks: AgentTask[]; impacts: unknown[]
}
export type Job = {
  run_id: string; title: string; status: string; updated_at: string;
  stalled?: boolean; active?: boolean; stage?: string; progress?: number;
  artifact_path?: string; parent_run_id?: string; operation?: string; error?: string
}
export type HealthPayload = HealthState
export type AgentState = {
  id:string; name:string; region:string; commands:string[]; connection:string;
  execution:string; docs_url:string; note:string; installed:boolean;
  authenticated:boolean|null; ready:boolean; executable:string; detail:string; schedulable:boolean
}
export type ApiProviderState = { id:string; name:string; region:string;
  configured:boolean; ready:boolean; model:string; api_base:string; key_env:string;
  default_model:string; docs_url:string; web_search:boolean; schedulable:boolean }
export type McpConfig = { id:string; name:string; format:string; value:string|Record<string,unknown> }
export type SetupPayload = { runtime_ready:boolean; data_root:string;
  taskpack_ready:boolean; agents:AgentState[]; api_providers:ApiProviderState[];
  mcp_command:string[]; mcp_configs:McpConfig[]; agent_profiles:AgentProfile[]; privacy_note:string }
export type AgentProfile = { id:string;name:string;command:string;args:string[] }
export type GenerateResult = { run_id: string; status: string; title: string }

export type StorySummary = {
  id: string; canonical_title: string; story_family: string; status: string;
  first_seen_at: string; last_seen_at: string; document_count: number;
  publisher_count: number; clustering_version: string
}
export type StoryDocument = {
  id: string; title: string; url: string; abstract?: string; published_at?: string;
  observed_date: string; category: string; publisher_cluster?: string;
  editorially_locked?: boolean
}
export type StoryDetail = StorySummary & {
  documents: StoryDocument[]; corroborated: boolean;
  reviews: { action: string; actor: string; occurred_at: string; details: Record<string, unknown> }[];
  claims: {id:string;predicate:string;object:unknown;status:string;
    evidence:{relation:string;document_title?:string;document_url?:string}[]}[]
}
export type CoverageCell = {
  id: string; dimensions: Record<string, string>; priority: number; status: string;
  rationale: string; attempts: number; source_yield: number; entity_yield: number;
  attempt_history?: { id: string; query: string; status: string; source_yield: number;
    entity_yield: number; stopping_reason: string }[]
}
export type CoveragePayload = { cells: CoverageCell[]; summary: {
  total: number; gaps: number; source_yield: number; entity_yield: number
} }
export type HistoryHorizon = {
  horizon:'weekly'|'monthly'|'quarterly'|'semiannual'|'biennial'|'fiveyear';
  window_start:string; window_end:string; target:number; target_range:number[];
  required_total:number; admitted_total:number; buckets_total:number;
  buckets_covered:number; required_buckets:number; publisher_count:number;
  ready:boolean; status:string; updated_at?:string; attempts:number
}
export type HistoryCoveragePayload = { items: HistoryHorizon[] }
export type Schedule = {
  action: 'daily'|'weekly'|'monthly'|'quarterly'; enabled: boolean;
  local_time: string; weekday: number; monthday: number; timezone: string;
  catch_up: boolean; last_period_key?: string; last_attempt_at?: string;
  last_success_at?: string; last_error?: string; next_run_at?: string;
  pipeline_mode: 'aggregate'|'generate'; provider: string;
  attempted_period_key?: string; retry_count: number; retry_after?: string;
  last_job_run_id?: string; last_artifact_path?: string
}
export type AutomationPayload = { email_delivery: false; schedules: Schedule[] }
export type TrashItem = { id: string; kind: 'industry'|'daily'; folder: string;
  name: string; created_at: string; item_count: number }
export type RestorePreview = RestorePreviewState
export type AuditRow = AuditState

export function artifactUrl(path: string) {
  return `/api/artifact?path=${encodeURIComponent(path)}`
}
