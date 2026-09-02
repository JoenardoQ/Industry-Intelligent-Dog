import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SetupPayload } from '../api'

const apiMock = vi.hoisted(() => vi.fn())
vi.mock('../api', async importOriginal => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, api: apiMock }
})

import OverviewPage from '../features/OverviewPage'
import SetupWizard from '../features/SetupWizard'
import SystemPage from '../features/SystemPage'

const setup: SetupPayload = {
  runtime_ready:true, data_root:'/data', taskpack_ready:true,
  privacy_note:'不读取私有登录数据', mcp_command:['intdog','mcp-serve'],
  mcp_configs:[{id:'generic',name:'Generic MCP',format:'json',value:{mcpServers:{intdog:{command:'intdog'}}}}],
  agent_profiles:[],
  agents:[{id:'codex',name:'Codex CLI',region:'international',commands:['codex'],connection:'cli',execution:'native',docs_url:'',note:'本机 CLI',installed:true,authenticated:false,ready:false,executable:'codex',detail:'需要登录',schedulable:true}],
  api_providers:[{id:'deepseek',name:'DeepSeek API',region:'china',configured:false,ready:false,model:'',api_base:'https://api.deepseek.com',key_env:'DEEPSEEK_API_KEY',default_model:'deepseek-chat',docs_url:'',auth_type:'bearer',auth_configurable:false,web_search:false,schedulable:true}],
}

beforeEach(() => { apiMock.mockReset(); localStorage.clear(); vi.stubGlobal('confirm',vi.fn(()=>true)) })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

describe('first-run and industry overview loop', () => {
  it('diagnoses four connection modes and keeps bootstrap gates in the wizard until confirmed', async () => {
    apiMock.mockImplementation((path:string, init?:RequestInit) => {
      if(path==='/industries') return Promise.resolve([])
      if(path==='/industries'&&init?.method==='POST') return Promise.resolve({folder:'AI',name:'人工智能'})
      if(path==='/settings/global/*'&&init?.method==='PUT') return Promise.resolve({provider:'taskpack',execution_mode:'taskpack'})
      if(path==='/industries/AI/generate') return Promise.resolve({run_id:'run-1',status:'queued',title:'行业初始化'})
      if(path==='/jobs') return Promise.resolve([{run_id:'run-1',title:'行业初始化',status:'running',updated_at:'now',stalled:false,active:true,stage:'entity_gate',progress:70,artifact_path:null,parent_run_id:null,operation:'bootstrap',error:null,error_category:'',origin:'app',provider:'public_sources',model:'',time_window:{},heartbeat_at:'now',heartbeat_age_seconds:0,lease_owner:'app',lease_expires_at:'later',checkpoint:{},recovery_actions:['cancel'],log_tail:[]}])
      if(path==='/industries/AI/overview') return Promise.resolve({industry:{name:'人工智能'},stats:{sources:8,documents:20,entities:12,candidate_entities:0,relations:1,claims:0,verified_claims:0,evidence:0,events:0,chain_nodes:3,empty_chain_nodes:0},chain:[],chain_edges:[],entities:[],source_categories:{official:8},latest_document_date:'2026-09-01'})
      throw new Error(`${path} ${String(init?.method)}`)
    })
    const complete=vi.fn()
    render(<SetupWizard setup={setup} hasIndustry={false} onRefresh={async()=>{}} onComplete={complete}/>)
    expect(screen.getByText('无模型模式')).toBeInTheDocument()
    expect(screen.getByText('CLI')).toBeInTheDocument()
    expect(screen.getByText('API')).toBeInTheDocument()
    expect(screen.getByText('MCP')).toBeInTheDocument()
    expect(screen.getByText(/需要登录/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'继续：选择连接'}))
    fireEvent.click(screen.getByRole('button',{name:'继续：选择行业'}))
    fireEvent.change(screen.getByLabelText('行业名称'),{target:{value:'人工智能'}})
    fireEvent.change(screen.getByLabelText('数据文件夹'),{target:{value:'AI'}})
    fireEvent.click(screen.getByRole('button',{name:'创建并开始研究'}))
    expect(await screen.findByText('信息源门槛')).toBeInTheDocument()
    expect(await screen.findByText('8 / 8')).toBeInTheDocument()
    expect(screen.getByText('3 / 1')).toBeInTheDocument()
    expect(screen.getByText('12 / 1')).toBeInTheDocument()
    expect(complete).not.toHaveBeenCalled()
    expect(localStorage.getItem('intdog.onboarding.active')).toContain('run-1')
    fireEvent.click(screen.getByRole('button',{name:'进入行业概览'}))
    expect(complete).toHaveBeenCalledWith('taskpack','AI')
    expect(localStorage.getItem('intdog.onboarding.active')).toBeNull()
  })

  it('renders persisted directed edges and linked assertion/fact counts', async () => {
    apiMock.mockImplementation((path:string) => {
      if(path.startsWith('/industries/AI/knowledge/entities')) return Promise.resolve({items:[],total:0,offset:0,limit:50,next_offset:null})
      if(path==='/industries/AI/overview') return Promise.resolve({industry:{name:'人工智能'},stats:{sources:9,documents:30,entities:4,candidate_entities:1,relations:2,claims:7,verified_claims:3,evidence:8,events:0,chain_nodes:2,empty_chain_nodes:0},chain:[{id:'a',name:'基础模型',description:'',order:1,status:'accepted',coverage_status:'covered',evidence_count:1,entity_count:2,evidenced_entities:2},{id:'b',name:'推理部署',description:'',order:2,status:'accepted',coverage_status:'covered',evidence_count:1,entity_count:2,evidenced_entities:2}],chain_edges:[{id:'e',src_node_id:'a',dst_node_id:'b',src_name:'基础模型',dst_name:'推理部署',relation:'enables',valid_from:null,valid_to:null,confidence:.8,status:'collected',effect:'positive',lag_days:null,evidence_count:1,evidence:[]}],entities:[],source_categories:{official:9},latest_document_date:'2026-09-01'})
      throw new Error(path)
    })
    render(<OverviewPage industry="AI" navigate={vi.fn()}/>)
    expect(await screen.findByText('enables')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:/断言.*7/})).toBeInTheDocument()
    expect(screen.getByRole('button',{name:/正式事实.*3/})).toBeInTheDocument()
  })

  it('exposes import/export beside recoverable archive and restore', async () => {
    apiMock.mockImplementation((path:string) => {
      if(path==='/health') return Promise.resolve({status:'ready',data_root:'/data',database:true,active_jobs:0,automation_running:false,session_required:true})
      if(path==='/trash') return Promise.resolve({items:[],total:0,permanent_delete_available:false})
      if(path==='/trash/audits/recent') return Promise.resolve([])
      if(path==='/industries/AI/automation') return Promise.resolve({email_delivery:false,schedules:[]})
      if(path==='/background') return Promise.resolve({service:{installed:false,enabled:false,platform:'linux',interval_minutes:15,error_category:''},last_wakeup:null,next_run_at:null,permissions:[],schedule_errors:[],email_delivery:false})
      throw new Error(path)
    })
    render(<SystemPage industry="AI" notify={vi.fn()} setup={setup}/>)
    expect(await screen.findByRole('button',{name:'导出当前行业'})).toBeInTheDocument()
    expect(screen.getByLabelText('导入行业包')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'归档当前行业'})).toBeInTheDocument()
    expect(screen.getByText(/恢复优先/)).toBeInTheDocument()
  })
})
