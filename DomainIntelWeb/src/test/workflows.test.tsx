import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, expectTypeOf, it, vi } from 'vitest'
import type {
  AgentProfile, AgentState, ApiProviderState, McpConfig, SetupPayload,
} from '../api'
import type {
  AgentGateCheck, AgentResultState, AgentVerificationChecks,
  AgentState as GeneratedAgentState, ApiProviderState as GeneratedApiProviderState,
  CustomAgentProfile, McpConfigState, SetupState,
} from '../generated/openapi'

const apiMock = vi.hoisted(() => vi.fn())
vi.mock('../api', async importOriginal => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, api: apiMock }
})

import DailyPage from '../features/DailyPage'
import AgentReviewPanel from '../features/research/AgentReviewPanel'
import JobsPage from '../features/JobsPage'
import ResearchPage from '../features/ResearchPage'
import SourcesPage from '../features/SourcesPage'
import SystemPage from '../features/SystemPage'
import SetupWizard from '../features/SetupWizard'
import { Generate } from '../features/shared'
import WorkflowSettingsPanel from '../features/settings/WorkflowSettingsPanel'

const notify = vi.fn()

const gate = (overrides: Partial<AgentGateCheck> = {}): AgentGateCheck => ({
  status: 'passed', reason: '门槛已通过', evidence_ids: ['cit_1'], locators: [], ...overrides,
})

const verification: AgentVerificationChecks = {
  atomization: gate(), reachability: gate(), publisher_identity: gate(),
  publication_time: gate(), entity_alignment: gate(), locator_integrity: gate({
    status: 'failed', reason: '缺少可复现定位',
    failures: [{evidence_id:'cit_1',reason:'归档端点暂时不可达',status_code:503}],
    locators: [{
      evidence_id: 'cit_1', url: 'https://official.example/report',
      content_hash: 'a'.repeat(64),
      locator: { type: 'text_offset', start: 4, end: 20 },
      excerpt: '政策原文明确支持该断言',
    }],
  }), generation_provenance: gate(), verifier_independence: gate(),
  semantic_support: { ...gate(), decision: 'supported' },
  numeric_consistency: gate(), type_classification: gate(), type_policy: gate(),
  resource_budget: gate(), corroboration: gate(), conflict: gate(),
  fact_projection: gate(),
}

const reviewResult: AgentResultState = {
  result_id: 'agr_1234567890abcdef12345678', industry: 'AI', task_id: 'tsk_market',
  agent_id: 'research-agent', summary: '芯片出口规则与市场影响核验',
  content_sha256: 'b'.repeat(64), status: 'draft_review_required',
  original_file: '/data/AI/result.json', created_at: '2026-09-01T02:03:04Z',
  assertions: [
    {
      id: 'aas_111111111111111111111111', text: '新规则于 9 月 1 日生效。',
      type: 'regulatory_status', status: 'candidate', claim_id: null,
      citations: [{ id: 'cit_1', url: 'https://official.example/report',
        canonical_url: 'https://official.example/report', reachability: 'reachable' }],
      verification,
    },
    {
      id: 'aas_222222222222222222222222', text: '供应链交付周期将缩短。',
      type: 'forecast', status: 'draft_review_required', claim_id: null,
      citations: [
        { id: 'cit_2', url: 'https://journal.example/paper',
          canonical_url: 'https://journal.example/paper', reachability: 'unknown' },
        { id: 'cit_3', url: 'javascript:alert(1)',
          canonical_url: 'javascript:alert(1)', reachability: 'unknown' },
      ],
      verification: null,
    },
  ],
}

const resultAt = (index: number): AgentResultState => ({
  ...reviewResult,
  result_id: `agr_${String(index).padStart(24,'0')}`,
  summary: `第 ${index} 份结果`,
  assertions: [],
})

const reviewPanelProps = {
  industry: 'AI', next_offset: null, loading: false, loadError: '',
  onLoadMore: async () => {}, onResultChanged: () => {},
}

const submittedResult: AgentResultState = {
  ...reviewResult,
  status: 'submitted_for_verification',
  assertions: [
    reviewResult.assertions[0],
    {...reviewResult.assertions[1],status:'submitted_for_verification'},
  ],
}

function StatefulReviewPanel() {
  const [items,setItems]=useState<AgentResultState[]>([reviewResult])
  return <AgentReviewPanel {...reviewPanelProps} items={items} total={1}
    onResultChanged={updated=>setItems(current=>current.map(
      item=>item.result_id===updated.result_id?updated:item))}/>
}

beforeEach(() => {
  apiMock.mockReset(); notify.mockReset()
  vi.stubGlobal('confirm', vi.fn(() => true))
})
afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); localStorage.clear()
  delete (window as Window&{intdogDesktop?:unknown}).intdogDesktop
})

describe('critical workbench workflows', () => {
  it('keeps one-click generation on the current page and shows the authoritative job state', async () => {
    window.location.hash='#/daily'
    apiMock.mockImplementation((path:string, options?:RequestInit) => {
      if(path==='/industries/AI/generate'&&options?.method==='POST')
        return Promise.resolve({run_id:'run-inline-123456789',status:'queued',title:'Daily',action:'daily'})
      if(path==='/jobs')return Promise.resolve([{run_id:'run-inline-123456789',title:'Daily',
        status:'running',updated_at:'now',stage:'正在检索权威来源',progress:0,
        progress_mode:'indeterminate',elapsed_seconds:3,result_kind:'local_data',recovery_actions:['cancel']}])
      return Promise.resolve({})
    })
    render(<Generate industry="AI" action="daily" label="抓取最新情报" notify={notify}/>)
    fireEvent.click(screen.getByRole('button',{name:/抓取最新情报/}))
    expect(await screen.findByText(/正在检索权威来源/)).toBeInTheDocument()
    expect(window.location.hash).toBe('#/daily')
    expect(screen.getByRole('link',{name:/查看任务详情/})).toHaveAttribute('href','#/jobs')
  })

  it('edits shared defaults without silently replacing an industry override', async () => {
    apiMock.mockImplementation((path:string, options?:RequestInit) => {
      if(path==='/settings/effective?folder=AI&operation=*')return Promise.resolve({
        provider:'codex',execution_mode:'direct',pipeline_mode:'generate',
        provenance:{provider:'industry'},layers:[{scope_key:'global',provider:'claude'},{scope_key:'industry:AI',provider:'codex'}],
      })
      if(path==='/settings/global/*'&&options?.method==='PUT')return Promise.resolve({})
      return Promise.resolve({})
    })
    render(<WorkflowSettingsPanel industry="AI" setup={{agents:[{id:'codex',name:'Codex',execution:'native',ready:true},{id:'claude',name:'Claude Code',execution:'native',ready:true}],api_providers:[]} as unknown as SetupPayload} notify={notify}/>)
    expect(await screen.findByText(/当前行业保留自定义设置/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('默认智能体'),{target:{value:'claude'}})
    fireEvent.click(screen.getByRole('button',{name:'保存全局默认'}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/settings/global/*',expect.objectContaining({method:'PUT'})))
    expect(JSON.parse(String(apiMock.mock.calls.find(call=>call[0]==='/settings/global/*'&&call[1]?.method==='PUT')?.[1]?.body))).toMatchObject({provider:'claude',execution_mode:'direct'})
  })

  it('runs the source-campaign review and entity-coverage workbench with explanations', async () => {
    const campaign={id:'scp_1',industry_id:'ind_1',targets:['official','news'],status:'paused',
      rounds:2,budget:20,stopping_reason:'http_429',created_at:'now',updated_at:'now'}
    const candidates=[
      {id:'src-c1',campaign_id:'scp_1',name:'Candidate A',url:'https://a.example',canonical_url:'https://a.example',
        category:'official',score:90,status:'candidate',selection_reason:'补足官方来源缺口',status_reason:'',query_ids:['q1']},
      {id:'src-c2',campaign_id:'scp_1',name:'Candidate B',url:'https://b.example',canonical_url:'https://b.example',
        category:'news',score:80,status:'manual_review',selection_reason:'媒体必须人工复核',status_reason:'等待编辑判断',query_ids:['q1']},
    ]
    apiMock.mockImplementation((path:string,init?:RequestInit) => {
      if(path==='/industries/AI/sources') return Promise.resolve({industry:'AI',categories:{official:[
        {id:'src-live',category:'official',name:'Active Authority',url:'https://active.example',monitoring_status:'active'},
      ]}})
      if(path==='/industries/AI/source-campaigns?limit=20&offset=0') return Promise.resolve({
        items:[campaign,{...campaign,id:'scp_2',status:'converged',stopping_reason:'two zero rounds'}],
        total:2,offset:0,limit:20,next_offset:null,
      })
      if(path==='/industries/AI/source-campaigns/scp_1?limit=20&offset=0') return Promise.resolve({
        ...campaign,candidate_page:{items:candidates,total:21,offset:0,limit:20,next_offset:20},
        query_ledger:[{id:'q1',round_no:1,language:'zh',family:'authoritative_baseline',
          dimensions:{source_type:'official'},query:'AI 官方来源',outcome:{status:'completed'},created_at:'now'}],
        source_gaps:[{category:'official',current:1,target:8,gap:7,query_count:1,candidate_count:1,
          rejection_reasons:{},explanation:'official 当前 1 / 8；缺口 7；已执行 1 条查询'}],
        round_history:[{id:'scr1',round_no:1,status:'completed',outcome:{},
          log:[{at:'now',level:'info',message:'18 logical queries persisted'}]}],
      })
      if(path==='/industries/AI/source-campaigns/scp_1?limit=20&offset=20') return Promise.resolve({
        ...campaign,candidate_page:{items:[{...candidates[0],id:'src-c3',name:'Candidate C',status:'rejected'}],
        total:21,offset:20,limit:20,next_offset:null},query_ledger:[],source_gaps:[],round_history:[],
      })
      if(path==='/industries/AI/coverage-matrix') return Promise.resolve({
        industry:'AI',completeness_proven:false,gap_count:1,algorithm_version:'entity-coverage-v1',cells:[{
          id:'ecv_1',source_type:'entity_evidence',subdomain:'Models',chain_stage:'Models',
          entity_type:'research_group',region:'china',current:2,target:8,gap:6,status:'gap',
          high_value:true,priority:95,explanation:'当前 2，目标 8，缺口 6；完整性未证明',
          relation_evidence:[{edge_id:'edge1',relation:'supplies',evidence_count:1}],
        }]})
      if(path==='/industries/AI/coverage-expansions'&&(!init||!init.method)) return Promise.resolve([])
      if(path==='/industries/AI/coverage-review-queue') return Promise.resolve({entities:[],relations:[]})
      if(path==='/industries/AI/source-candidates/src-c1/review'&&init?.method==='POST')
        return Promise.resolve({...candidates[0],status:'reserve',review:{actor:'analyst',reason:'同 owner 重复'}})
      if(path==='/industries/AI/coverage-expansions'&&init?.method==='POST')
        return Promise.resolve({cells:[],entity_queries:[],relation_queries:[],stopping_reason:null})
      throw new Error(`${path} ${String(init?.method)}`)
    })
    render(<SourcesPage industry="AI" notify={notify}/>)
    expect(await screen.findByText('Active Authority')).toBeInTheDocument()
    expect(await screen.findByText('AI 官方来源')).toBeInTheDocument()
    for(const state of ['待审核','采用','人工阅读','备用','不采用','已暂停','本轮完成'])
      expect(screen.getAllByText(state).length).toBeGreaterThan(0)
    expect(screen.getByText('Models')).toBeInTheDocument()
    expect(screen.getByText('research_group')).toBeInTheDocument()
    expect(screen.getByText('china')).toBeInTheDocument()
    expect(screen.getByText('2 / 8')).toBeInTheDocument()
    expect(screen.getByText('缺口 6')).toBeInTheDocument()
    expect(screen.getAllByText(/完整性未证明/).length).toBeGreaterThan(0)
    expect(screen.getByText(/supplies · 1 条证据/)).toBeInTheDocument()
    const explanation=screen.getByLabelText('候选复核说明 · Candidate A')
    fireEvent.change(explanation,{target:{value:'同 owner 重复'}})
    fireEvent.click(screen.getByRole('button',{name:'备用 · Candidate A'}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith(
      '/industries/AI/source-candidates/src-c1/review',{
        method:'POST',body:JSON.stringify({decision:'reserve',actor:'local-user',reason:'同 owner 重复'}),
      }))
    fireEvent.click(screen.getByRole('button',{name:'下一页候选'}))
    expect(await screen.findByText('Candidate C')).toBeInTheDocument()
  })

  it('derives Agent setup DTOs from the generated OpenAPI contract', () => {
    expectTypeOf<AgentState>().toEqualTypeOf<GeneratedAgentState>()
    expectTypeOf<ApiProviderState>().toEqualTypeOf<GeneratedApiProviderState>()
    expectTypeOf<McpConfig>().toEqualTypeOf<McpConfigState>()
    expectTypeOf<SetupPayload>().toEqualTypeOf<SetupState>()
    expectTypeOf<AgentProfile>().toEqualTypeOf<CustomAgentProfile>()
  })

  it('lets a fresh install enter model-free task-package mode without claiming an agent connection', async () => {
    apiMock.mockResolvedValue({provider:'taskpack',execution_mode:'taskpack'})
    const complete=vi.fn()
    render(<SetupWizard setup={{runtime_ready:true,data_root:'/data',taskpack_ready:true,
      privacy_note:'不读取私有登录数据',mcp_command:['intdog','mcp-serve'],mcp_configs:[{id:'generic',name:'Generic MCP',format:'json',value:{mcpServers:{intdog:{command:'intdog',args:['mcp-serve']}}}}],agent_profiles:[],api_providers:[],agents:[{
        id:'codex',name:'Codex CLI',region:'international',commands:['codex'],connection:'cli',
        execution:'native',docs_url:'https://example.test',note:'local',installed:false,
        authenticated:null,ready:false,executable:'',detail:'missing',schedulable:true}]}}
      onRefresh={async()=>{}} onComplete={complete}/>)
    expect(screen.getByText(/Codex CLI：missing/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'继续：选择连接'}))
    expect(screen.getByText('未安装')).toBeInTheDocument()
    expect(screen.getByText('Generic MCP 连接配置')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'返回诊断'}))
    fireEvent.click(screen.getByRole('button',{name:'进入工作台'}))
    await waitFor(()=>expect(complete).toHaveBeenCalledWith('taskpack'))
  })

  it('passes generic compatible authentication type through the desktop save request', async () => {
    const saveProvider=vi.fn().mockResolvedValue({configured:true})
    const relaunch=vi.fn().mockResolvedValue(true)
    Object.defineProperty(window,'intdogDesktop',{configurable:true,value:{
      credentialStatus:vi.fn().mockResolvedValue({secureStorage:true,configured:false,
        provider:'',model:'',apiBase:'',authType:''}),saveProvider,
      clearProvider:vi.fn(),relaunch,
    }})
    const setup={runtime_ready:true,data_root:'/data',taskpack_ready:true,
      privacy_note:'privacy',mcp_command:['intdog','mcp-serve'],mcp_configs:[],
      agent_profiles:[],agents:[],api_providers:[{
        id:'compatible_api',name:'Generic Compatible API',region:'international',
        configured:false,ready:false,model:'',api_base:'',key_env:'INTDOG_LLM_API_KEY',
        default_model:'',docs_url:'',web_search:false,schedulable:true,
        auth_type:'bearer',auth_configurable:true,
    }]} as SetupPayload
    render(<SetupWizard setup={setup} onRefresh={async()=>{}} onComplete={()=>{}}/>)
    fireEvent.click(screen.getByRole('button',{name:'继续：选择连接'}))
    fireEvent.click(screen.getByRole('radio',{name:/Generic Compatible API/}))
    fireEvent.change(screen.getByLabelText('模型'),{target:{value:'custom-model'}})
    fireEvent.change(screen.getByLabelText('API Base（可选）'),
      {target:{value:'https://models.example/v1'}})
    fireEvent.change(screen.getByLabelText('认证方式'),{target:{value:'api_key_header'}})
    fireEvent.change(screen.getByLabelText('API Key'),{target:{value:'desktop-secret'}})
    fireEvent.click(screen.getByRole('button',{name:'安全保存并重启'}))
    await waitFor(()=>expect(saveProvider).toHaveBeenCalledWith({
      provider:'compatible_api',model:'custom-model',apiKey:'desktop-secret',
      apiBase:'https://models.example/v1',authType:'api_key_header',
    }))
    expect(relaunch).toHaveBeenCalled()
    expect(screen.queryByText(/Key 仅进入.*后端进程环境/)).not.toBeInTheDocument()
  })

  it('creates the first industry and queues a model-free bootstrap from onboarding', async () => {
    apiMock.mockImplementation((path:string,init?:RequestInit)=>{
      if(path==='/industries')return Promise.resolve([])
      if(path==='/industries'&&init?.method==='POST')return Promise.resolve({folder:'AI',name:'人工智能'})
      if(path==='/settings/global/*'&&init?.method==='PUT')return Promise.resolve({provider:'taskpack',execution_mode:'taskpack'})
      if(path==='/industries/AI/generate')return Promise.resolve({run_id:'r1',status:'queued',title:'init'})
      throw new Error(`${path} ${String(init?.method)}`)
    })
    const complete=vi.fn()
    render(<SetupWizard hasIndustry={false} setup={{runtime_ready:true,data_root:'/data',taskpack_ready:true,
      privacy_note:'privacy',mcp_command:['intdog','mcp-serve'],mcp_configs:[{id:'generic',name:'Generic MCP',format:'json',value:{}}],agent_profiles:[],api_providers:[],agents:[]}}
      onRefresh={async()=>{}} onComplete={complete}/>)
    fireEvent.click(screen.getByRole('button',{name:'继续：选择连接'}))
    fireEvent.click(screen.getByRole('button',{name:'继续：选择行业'}))
    fireEvent.change(screen.getByPlaceholderText('例如：人工智能'),{target:{value:'人工智能'}})
    fireEvent.change(screen.getByPlaceholderText('例如：AI'),{target:{value:'AI'}})
    fireEvent.click(screen.getByRole('button',{name:'创建并开始研究'}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/settings/global/*',{
      method:'PUT',body:JSON.stringify({provider:'taskpack',execution_mode:'taskpack'}),
    }))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/industries/AI/generate',expect.objectContaining({method:'POST'})))
    const generateCall=apiMock.mock.calls.find(call=>call[0]==='/industries/AI/generate')
    expect(JSON.parse(String(generateCall?.[1]?.body))).toEqual({action:'bootstrap'})
    expect(complete).not.toHaveBeenCalled()
    expect(localStorage.getItem('intdog.onboarding.active')).toContain('r1')
  })
  it('selects the complete current Daily filter and moves exactly those rows to recoverable deletion', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') return Promise.resolve({ deleted: 2 })
      return Promise.resolve({ items: [
        { id:'1',title:'Alpha',url:'https://a.test',category:'news',date:'2026-08-30',display_source:'Source A',origin:'china',identity:{date:'2026-08-30',category:'news',key:'1'} },
        { id:'2',title:'Beta',url:'https://b.test',category:'papers',date:'2026-08-30',display_source:'Author B',origin:'global',identity:{date:'2026-08-30',category:'papers',key:'2'} },
      ], total:2,next_cursor:null,selection_scope:'current_page',dates:['2026-08-30'],counts:{},origins:{} })
    })
    render(<DailyPage industry="AI" notify={notify}/>)
    await screen.findByText('Alpha')
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'全选当前筛选'}))
    fireEvent.click(screen.getByRole('button',{name:/删除 2/}))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/industries/AI/daily', expect.objectContaining({method:'DELETE'})))
    const deletion=apiMock.mock.calls.find(call=>call[1]?.method==='DELETE')
    expect(deletion).toBeDefined()
    const body=JSON.parse(String(deletion?.[1]?.body))
    expect(body.items).toHaveLength(2)
  })

  it('previews restore collisions before sending the restore mutation', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path==='/health') return Promise.resolve({status:'ready',data_root:'/data',database:true,active_jobs:0,automation_running:true,session_required:true})
      if (path==='/trash') return Promise.resolve({items:[{id:'t1',kind:'daily',folder:'AI',name:'batch',created_at:'now',item_count:3}]})
      if (path==='/trash/audits/recent') return Promise.resolve([])
      if (path==='/background') return Promise.resolve({service:{installed:false,enabled:false,platform:'test',interval_minutes:15,error_category:''},last_wakeup:null,next_run_at:null,permissions:[],schedule_errors:[],email_delivery:false})
      if (path.includes('/automation')) return Promise.resolve({email_delivery:false,schedules:[]})
      if (path.endsWith('/preview')) return Promise.resolve({id:'t1',kind:'daily',folder:'AI',restorable:true,restore_count:2,skip_count:1,collisions:['1 条重复文档']})
      if (init?.method==='POST') return Promise.resolve({restored:2,skipped:1})
      throw new Error(path)
    })
    render(<SystemPage industry="AI" notify={notify}/>)
    fireEvent.click(await screen.findByRole('button',{name:'恢复'}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/trash/t1/preview'))
    expect(await screen.findByRole('dialog',{name:'恢复“batch”'})).toHaveTextContent('1 条重复文档')
    fireEvent.click(screen.getByRole('button',{name:'确认恢复'}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/trash/t1/restore',expect.objectContaining({method:'POST'})))
    const previewIndex=apiMock.mock.calls.findIndex(call=>call[0].endsWith('/preview'))
    const restoreIndex=apiMock.mock.calls.findIndex(call=>call[0].endsWith('/restore'))
    expect(previewIndex).toBeGreaterThan(-1); expect(restoreIndex).toBeGreaterThan(previewIndex)
  })

  it('does not call first-run insufficient observations drift', async () => {
    apiMock.mockImplementation((path:string) => {
      if(path==='/health')return Promise.resolve({status:'ready',data_root:'/data',database:true,active_jobs:0,automation_running:true,session_required:true})
      if(path==='/trash')return Promise.resolve({items:[]})
      if(path==='/trash/audits/recent')return Promise.resolve([])
      if(path==='/background')return Promise.resolve({service:{installed:false,enabled:false,platform:'test',interval_minutes:15,error_category:''},last_wakeup:null,next_run_at:null,permissions:[],schedule_errors:[],email_delivery:false})
      if(path.includes('/automation'))return Promise.resolve({email_delivery:false,schedules:[]})
      if(path.endsWith('/quality-drift'))return Promise.resolve({alert_count:0,metrics:[
        {metric:'source_success_rate',window_days:7,status:'insufficient_data',value:null,diagnosis:'need baseline'},
      ]})
      throw new Error(path)
    })
    render(<SystemPage industry="AI" notify={notify}/>)
    expect(await screen.findByText('未发现漂移')).toBeInTheDocument()
    expect(screen.getByText(/数据不足以判断趋势/)).toBeInTheDocument()
    expect(document.querySelector('.drift-panel details')).not.toHaveAttribute('open')
  })

  it('uses the accessible shutdown dialog and delegates Desktop window lifecycle', async()=>{
    const close=vi.fn().mockResolvedValue(true)
    Object.defineProperty(window,'intdogDesktop',{configurable:true,value:{
      credentialStatus:vi.fn(),saveProvider:vi.fn(),clearProvider:vi.fn(),
      backgroundStatus:vi.fn(),requestBackgroundInstall:vi.fn().mockResolvedValue({nonce:'test-nonce'}),installBackground:vi.fn(),removeBackground:vi.fn(),
      relaunch:vi.fn(),close,
    }})
    apiMock.mockImplementation((path:string,init?:RequestInit)=>{
      if(path==='/health')return Promise.resolve({status:'ready',data_root:'/data',database:true,active_jobs:0,automation_running:true,session_required:true})
      if(path==='/trash')return Promise.resolve({items:[]})
      if(path==='/trash/audits/recent')return Promise.resolve([])
      if(path==='/background')return Promise.resolve({service:{installed:false,enabled:false,platform:'test',interval_minutes:15,error_category:''},last_wakeup:null,next_run_at:null,permissions:[],schedule_errors:[],email_delivery:false})
      if(path.includes('/automation'))return Promise.resolve({email_delivery:false,schedules:[]})
      if(path==='/shutdown'&&init?.method==='POST')return Promise.resolve({status:'stopping'})
      throw new Error(path)
    })
    render(<SystemPage industry="AI" notify={notify}/>)
    fireEvent.click(await screen.findByRole('button',{name:'退出 IntDog'}))
    expect(screen.getByRole('dialog',{name:'安全退出 IntDog'})).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'退出并停止'}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/shutdown',{method:'POST'}))
    expect(close).toHaveBeenCalledOnce()
  })

  it('exposes safe retry only for retryable durable jobs', async () => {
    apiMock.mockImplementation((path:string, init?:RequestInit) => {
      if (path==='/jobs') return Promise.resolve([{run_id:'r1',title:'Failed research',status:'failed',updated_at:'now',stage:'validate',progress:.5}])
      if (path.endsWith('/output')) return Promise.resolve({run_id:'r1',output:'failure detail'})
      if (path.endsWith('/retry') && init?.method==='POST') return Promise.resolve({run_id:'r2'})
      return Promise.resolve({})
    })
    render(<JobsPage/>)
    fireEvent.click(await screen.findByRole('button',{name:/Failed research/}))
    fireEvent.click(await screen.findByRole('button',{name:/安全重试/}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/jobs/r1/retry',{method:'POST'}))
  })

  it('shows indeterminate work without inventing a zero-percent completion signal', async () => {
    apiMock.mockImplementation((path:string) => {
      if(path==='/jobs')return Promise.resolve([{run_id:'r-live',title:'Live research',
        status:'running',updated_at:'now',stage:'检索论文',progress:0,
        progress_mode:'indeterminate',elapsed_seconds:12,result_kind:'artifact',
        recovery_actions:['cancel']}])
      if(path.endsWith('/output'))return Promise.resolve({run_id:'r-live',output:'正在检索'})
      return Promise.resolve({})
    })
    render(<JobsPage/>);fireEvent.click(await screen.findByRole('button',{name:/Live research/}))
    expect(screen.getAllByText(/进度暂不可估算/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/检索论文 · 0%/)).not.toBeInTheDocument()
  })

  it('shows authoritative task provenance, window, provider and recovery metadata', async () => {
    apiMock.mockImplementation((path:string) => {
      if (path==='/jobs') return Promise.resolve([{run_id:'r-bg',title:'Background daily',
        status:'partial',updated_at:'2026-09-02T08:01:00Z',stage:'verify',progress:65,
        origin:'background_worker',provider:'public_sources',model:'',
        heartbeat_at:'2026-09-02T08:00:30Z',error_category:'partial',
        error:'one source timed out',recovery_actions:['retry','cancel'],time_window:{
          start:'2026-09-01T04:00:00+08:00',end:'2026-09-02T08:00:00+08:00',
          timezone:'Asia/Shanghai'}}])
      if (path.endsWith('/output')) return Promise.resolve({run_id:'r-bg',output:'partial log'})
      return Promise.resolve({})
    })
    render(<JobsPage/>); fireEvent.click(await screen.findByRole('button',{name:/Background daily/}))
    expect(screen.getByText('后台 Worker')).toBeInTheDocument()
    expect(screen.getByText('public_sources')).toBeInTheDocument()
    expect(screen.getByText(/2026-09-01T04:00:00/)).toBeInTheDocument()
    expect(screen.getAllByText('partial').length).toBeGreaterThan(0)
    expect(screen.getByText(/2026-09-02T08:00:30Z/)).toBeInTheDocument()
    expect(screen.getByRole('button',{name:/安全重试/})).toBeInTheDocument()
  })

  it('shows background service wakeups, permissions and uses only Desktop IPC to install', async () => {
    const installBackground=vi.fn().mockResolvedValue({installed:true})
    Object.defineProperty(window,'intdogDesktop',{configurable:true,value:{
      backgroundStatus:vi.fn().mockResolvedValue({installed:false,enabled:false,platform:'linux'}),
      requestBackgroundInstall:vi.fn().mockResolvedValue({nonce:'test-nonce'}),installBackground,removeBackground:vi.fn(),credentialStatus:vi.fn(),saveProvider:vi.fn(),
      clearProvider:vi.fn(),relaunch:vi.fn(),
    }})
    apiMock.mockImplementation((path:string) => {
      if(path==='/health') return Promise.resolve({status:'ready',data_root:'/data',database:true,
        active_jobs:0,automation_running:true,session_required:true})
      if(path==='/trash') return Promise.resolve({items:[]})
      if(path==='/trash/audits/recent') return Promise.resolve([])
      if(path.includes('/automation')) return Promise.resolve({email_delivery:false,schedules:[]})
      if(path==='/background') return Promise.resolve({email_delivery:false,next_run_at:'2026-09-03T08:00:00+08:00',
        service:{installed:false,enabled:false,platform:'linux',interval_minutes:15,error_category:''},
        last_wakeup:{status:'completed',started_at:'2026-09-02T08:00:00Z',finished_at:'2026-09-02T08:01:00Z',
          summary:{claimed:2,completed:2,paused:0,failed:0},error:{}},
        permissions:[{folder:'AI',provider:'openai',operation:'weekly',allowed:true,
          updated_at:'2026-09-01T00:00:00Z'}],schedule_errors:[]})
      throw new Error(path)
    })
    render(<SystemPage industry="AI" notify={notify}/>)
    expect(await screen.findByText('最近唤醒：completed')).toBeInTheDocument()
    expect(screen.getByText(/openai · weekly/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'启用后台运行'}))
    await waitFor(()=>expect(installBackground).toHaveBeenCalledWith({intervalMinutes:15,nonce:'test-nonce'}))
    expect(apiMock.mock.calls.some(call=>String(call[0]).includes('install'))).toBe(false)
  })

  it('distinguishes the report generation threshold from the aspirational history target', async () => {
    apiMock.mockImplementation((path:string) => {
      if (path.endsWith('/research')) return Promise.resolve({agenda:[],lab:{},tasks:[],impacts:[]})
      if (path.endsWith('/coverage')) return Promise.resolve({cells:[],summary:{total:0,gaps:0,source_yield:0,entity_yield:0}})
      if (path.endsWith('/history')) return Promise.resolve({items:[{
        horizon:'biennial', window_start:'2024-09-01', window_end:'2026-08-31',
        target:2800, target_range:[2400,3200], required_total:2100,
        admitted_total:2785, buckets_total:105, buckets_covered:98,
        required_buckets:84, publisher_count:721, ready:true, status:'ready', attempts:105,
      }]})
      if (path.includes('/agent-bridge/results')) return Promise.resolve({items:[],total:0,offset:0,limit:50,next_offset:null})
      throw new Error(path)
    })
    render(<ResearchPage industry="AI" notify={notify}/>)
    expect(await screen.findByText('已过生成门槛')).toBeInTheDocument()
    expect(screen.getByText(/目标 2,800/)).toBeInTheDocument()
    expect(screen.getByText(/生成门槛 2,100/)).toBeInTheDocument()
    const progress=screen.getByRole('progressbar',{name:'两年证据目标进度'})
    expect(progress).toHaveAttribute('max','2800')
    expect(progress).toHaveAttribute('value','2785')
  })

  it('imports an external agent result into the review-required bridge', async () => {
    apiMock.mockImplementation((path:string,init?:RequestInit) => {
      if(path.endsWith('/research')) return Promise.resolve({agenda:[],lab:{},tasks:[{id:'tsk_1',title:'Verify models',status:'ready',budget:5}],impacts:[]})
      if(path.endsWith('/coverage')) return Promise.resolve({cells:[],summary:{total:0,gaps:0,source_yield:0,entity_yield:0}})
      if(path.endsWith('/history')) return Promise.resolve({items:[]})
      if(path.includes('/agent-bridge/results?')) return Promise.resolve({items:[],total:0,offset:0,limit:50,next_offset:null})
      if(path.endsWith('/agent-bridge/results')&&init?.method==='POST') return Promise.resolve({task_id:'tsk_1',agent_id:'other',summary:'done',assertions:[],status:'draft_review_required',duplicate:false,path:'/data/result.json'})
      throw new Error(path)
    })
    render(<ResearchPage industry="AI" notify={notify}/>)
    expect(await screen.findByText('Verify models')).toBeInTheDocument()
    const payload={task_id:'tsk_1',agent_id:'other',summary:'done',assertions:[{text:'claim',citations:['https://example.com']}]}
    fireEvent.change(screen.getByLabelText('粘贴 Agent 结果 JSON'),{target:{value:JSON.stringify(payload)}})
    fireEvent.click(screen.getByRole('button',{name:'校验并导入待复核区'}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/industries/AI/agent-bridge/results',expect.objectContaining({method:'POST'})))
    expect(notify).toHaveBeenCalledWith({kind:'ok',text:'结果已进入待复核区'})
  })

  it('does not report an empty review queue while the initial result page is loading', async () => {
    render(<AgentReviewPanel {...reviewPanelProps} items={[]} total={0} loading/>)
    expect(screen.getByText('正在读取 Agent 结果…')).toBeInTheDocument()
    expect(screen.queryByText('尚未导入 Agent 结果。')).not.toBeInTheDocument()
  })

  it('distinguishes a review queue load error from a successfully loaded empty page', () => {
    const {rerender}=render(<AgentReviewPanel {...reviewPanelProps} items={[]} total={0}
      loadError="Agent 结果索引损坏"/>)
    expect(screen.getByRole('alert')).toHaveTextContent('Agent 结果索引损坏')
    expect(screen.queryByText('尚未导入 Agent 结果。')).not.toBeInTheDocument()
    rerender(<AgentReviewPanel {...reviewPanelProps} items={[]} total={0}/>)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('尚未导入 Agent 结果。')).toBeInTheDocument()
  })

  it('loads the fifty-first review result through the typed queue pagination control', async () => {
    const firstPage=Array.from({length:50},(_,index)=>resultAt(index+1))
    apiMock.mockImplementation((path:string) => {
      if(path.endsWith('/research')) return Promise.resolve({agenda:[],lab:{},tasks:[],impacts:[]})
      if(path.endsWith('/coverage')) return Promise.resolve({cells:[],summary:{total:0,gaps:0,source_yield:0,entity_yield:0}})
      if(path.endsWith('/history')) return Promise.resolve({items:[]})
      if(path.includes('/agent-bridge/results?limit=50&offset=0')) return Promise.resolve({
        industry:'AI',items:firstPage,total:51,offset:0,limit:50,next_offset:50,
      })
      if(path.includes('/agent-bridge/results?limit=50&offset=50')) return Promise.resolve({
        industry:'AI',items:[resultAt(51)],total:51,offset:50,limit:50,next_offset:null,
      })
      throw new Error(path)
    })
    render(<ResearchPage industry="AI" notify={notify}/>)
    fireEvent.click(await screen.findByRole('button',{name:'加载更多结果（50 / 51）'}))
    expect(await screen.findByText('第 51 份结果')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/industries/AI/agent-bridge/results?limit=50&offset=50',
      expect.objectContaining({signal:expect.anything()}),
    )
    expect(screen.getByText('51 份结果')).toBeInTheDocument()
  })

  it('ignores every stale response when a slow industry is replaced by a fast industry', async () => {
    const pending=new Map<string,(value:unknown)=>void>()
    apiMock.mockImplementation((path:string,init?:RequestInit) => {
      if(path.includes('/industries/slow/')) return new Promise(resolve=>pending.set(path,resolve))
      if(path.endsWith('/research')) return Promise.resolve({agenda:[],lab:{},tasks:[],impacts:[]})
      if(path.endsWith('/coverage')) return Promise.resolve({cells:[],summary:{total:0,gaps:0,source_yield:0,entity_yield:0}})
      if(path.endsWith('/history')) return Promise.resolve({items:[]})
      if(path.includes('/agent-bridge/results?limit=50&offset=0')) return Promise.resolve({
        industry:'fast',items:[{...resultAt(1),summary:'fast industry result'}],
        total:1,offset:0,limit:50,next_offset:null,
      })
      throw new Error(`${path} ${String(init?.signal)}`)
    })
    const {rerender}=render(<ResearchPage industry="slow" notify={notify}/>)
    await waitFor(()=>expect(pending.size).toBe(4))
    rerender(<ResearchPage industry="fast" notify={notify}/>)
    expect(await screen.findByText('fast industry result')).toBeInTheDocument()
    const slowCalls=apiMock.mock.calls.filter(call=>String(call[0]).includes('/industries/slow/'))
    expect(slowCalls).toHaveLength(4)
    slowCalls.forEach(call=>expect((call[1] as RequestInit|undefined)?.signal?.aborted).toBe(true))
    pending.forEach((resolve,path)=>{
      if(path.endsWith('/research')) resolve({agenda:[],lab:{},tasks:[],impacts:[]})
      else if(path.endsWith('/coverage')) resolve({cells:[],summary:{total:0,gaps:0,source_yield:0,entity_yield:0}})
      else if(path.endsWith('/history')) resolve({items:[]})
      else resolve({industry:'slow',items:[{...resultAt(2),summary:'stale slow result'}],total:1,offset:0,limit:50,next_offset:null})
    })
    await waitFor(()=>expect(screen.queryByText('stale slow result')).not.toBeInTheDocument())
    expect(screen.getByText('fast industry result')).toBeInTheDocument()
  })

  it('renders assertion evidence, review explanation, gate failures and safe external citations', () => {
    render(<AgentReviewPanel {...reviewPanelProps} items={[reviewResult]} total={1}/>)
    expect(screen.getByText('芯片出口规则与市场影响核验')).toBeInTheDocument()
    expect(screen.getByText(/research-agent/)).toBeInTheDocument()
    expect(screen.getByText(/tsk_market/)).toBeInTheDocument()
    expect(screen.getByText(/2026/)).toBeInTheDocument()
    expect(screen.getByText('新规则于 9 月 1 日生效。')).toBeInTheDocument()
    expect(screen.getByText('缺少可复现定位')).toBeInTheDocument()
    expect(screen.getByText(/text_offset/)).toBeInTheDocument()
    const locatorGate=screen.getByText('证据定位').closest('article')
    expect(locatorGate).not.toBeNull()
    const failures=within(locatorGate!).getByRole('list',{name:'门槛失败明细'})
    expect(within(failures).getByText('归档端点暂时不可达')).toBeInTheDocument()
    expect(within(failures).getByText('cit_1')).toBeInTheDocument()
    expect(within(failures).getByText('HTTP 503')).toBeInTheDocument()
    expect(screen.getByLabelText('复核说明 · 供应链交付周期将缩短。')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'驳回'})).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'保留为观点'})).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'提交核验'})).toBeInTheDocument()
    const official=screen.getAllByRole('link',{name:/official\.example/})
    expect(official).toHaveLength(2)
    official.forEach(link => {
      expect(link).toHaveAttribute('target','_blank')
      expect(link).toHaveAttribute('rel','noopener noreferrer external')
    })
    expect(screen.queryByRole('link',{name:/javascript/})).not.toBeInTheDocument()
  })

  it('submits the assertion action and follows verification pagination with controls disabled', async () => {
    let finishReview: ((value: unknown) => void) | undefined
    const onResultChanged=vi.fn()
    apiMock.mockImplementation((path:string,init?:RequestInit) => {
      if(path.endsWith('/review')) return new Promise(resolve => { finishReview=resolve })
      if(path.includes('/verify?limit=10&offset=0')) return Promise.resolve({
        result_id:reviewResult.result_id,status:'partial',detail:'first page',
        decisions:Array.from({length:10},(_,index)=>({assertion_id:`aas_${index}`,disposition:'candidate',checks:{}})),
        total:11,offset:0,limit:10,next_offset:10,
      })
      if(path.includes('/verify?limit=10&offset=10')) return Promise.resolve({
        result_id:reviewResult.result_id,status:'partial',detail:'second page',
        decisions:[{assertion_id:'aas_10',disposition:'candidate',checks:{}}],
        total:11,offset:10,limit:10,next_offset:null,
      })
      if(path.endsWith(`/agent-bridge/results/${reviewResult.result_id}`) && !init) return Promise.resolve({
        ...reviewResult,status:'candidate',assertions:[
          reviewResult.assertions[0],
          {...reviewResult.assertions[1],status:'candidate'},
        ],
      })
      throw new Error(`${path} ${String(init?.method)}`)
    })
    render(<AgentReviewPanel {...reviewPanelProps} items={[reviewResult]} total={1}
      onResultChanged={onResultChanged}/>)
    fireEvent.change(screen.getByLabelText('复核说明 · 供应链交付周期将缩短。'),{
      target:{value:'请核对交付周期的统计口径'},
    })
    fireEvent.click(screen.getByRole('button',{name:'提交核验'}))
    expect(screen.getByRole('button',{name:'正在提交…'})).toBeDisabled()
    expect(apiMock).toHaveBeenCalledWith(
      `/industries/AI/agent-bridge/results/${reviewResult.result_id}/review`,
      {method:'POST',body:JSON.stringify({
        assertion_id:'aas_222222222222222222222222',
        decision:'submitted_for_verification',note:'请核对交付周期的统计口径',
      })},
    )
    finishReview?.({...reviewResult,assertions:[
      reviewResult.assertions[0],
      {...reviewResult.assertions[1],status:'submitted_for_verification'},
    ]})
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith(
      `/industries/AI/agent-bridge/results/${reviewResult.result_id}/verify?limit=10&offset=10`,
      {method:'POST'},
    ))
    await waitFor(()=>expect(onResultChanged).toHaveBeenCalledWith(
      expect.objectContaining({result_id:reviewResult.result_id,status:'candidate'}),
    ))
  })

  it('keeps the review explanation and shows a recoverable request error', async () => {
    apiMock.mockRejectedValue(new Error('核验服务暂不可用'))
    render(<AgentReviewPanel {...reviewPanelProps} items={[reviewResult]} total={1}/>)
    const explanation=screen.getByLabelText('复核说明 · 供应链交付周期将缩短。')
    fireEvent.change(explanation,{target:{value:'不要丢失这段人工说明'}})
    fireEvent.click(screen.getByRole('button',{name:'提交核验'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('核验服务暂不可用')
    expect(explanation).toHaveValue('不要丢失这段人工说明')
  })

  it('keeps the submitted state when verification fails after a successful review', async () => {
    apiMock.mockImplementation((path:string) => {
      if(path.endsWith('/review')) return Promise.resolve(submittedResult)
      if(path.includes('/verify?')) return Promise.reject(new Error('核验网络暂时不可用'))
      throw new Error(path)
    })
    render(<StatefulReviewPanel/>)
    fireEvent.click(screen.getByRole('button',{name:'提交核验'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('核验网络暂时不可用')
    expect(screen.getAllByText('待自动核验')).toHaveLength(2)
    expect(screen.queryByRole('button',{name:'提交核验'})).not.toBeInTheDocument()
    expect(screen.queryByRole('button',{name:'驳回'})).not.toBeInTheDocument()
    expect(screen.queryByRole('button',{name:'保留为观点'})).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:'重试自动核验'})).toBeInTheDocument()
  })

  it('rejects non-monotonic verification pagination as a recoverable contract error', async () => {
    apiMock.mockImplementation((path:string) => {
      if(path.endsWith('/review')) return Promise.resolve(submittedResult)
      if(path.includes('/verify?limit=10&offset=0')) return Promise.resolve({
        result_id:reviewResult.result_id,status:'partial',detail:'broken page',
        decisions:[{assertion_id:'aas_1',disposition:'candidate',checks:{}}],
        total:2,offset:0,limit:10,next_offset:0,
      })
      throw new Error(path)
    })
    render(<StatefulReviewPanel/>)
    fireEvent.click(screen.getByRole('button',{name:'提交核验'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('核验分页合同异常')
    expect(screen.getAllByText('待自动核验')).toHaveLength(2)
    expect(screen.getByRole('button',{name:'重试自动核验'})).toBeInTheDocument()
  })
})
