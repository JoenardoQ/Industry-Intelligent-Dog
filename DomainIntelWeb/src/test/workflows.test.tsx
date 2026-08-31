import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => vi.fn())
vi.mock('../api', async importOriginal => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, api: apiMock }
})

import DailyPage from '../features/DailyPage'
import JobsPage from '../features/JobsPage'
import ResearchPage from '../features/ResearchPage'
import SystemPage from '../features/SystemPage'
import SetupWizard from '../features/SetupWizard'

const notify = vi.fn()

beforeEach(() => {
  apiMock.mockReset(); notify.mockReset()
  vi.stubGlobal('confirm', vi.fn(() => true))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('critical workbench workflows', () => {
  it('lets a fresh install enter model-free task-package mode without claiming an agent connection', async () => {
    const complete=vi.fn()
    render(<SetupWizard setup={{runtime_ready:true,data_root:'/data',taskpack_ready:true,
      privacy_note:'不读取私有登录数据',mcp_command:['intdog','mcp-serve'],mcp_configs:[{id:'generic',name:'Generic MCP',format:'json',value:{mcpServers:{intdog:{command:'intdog',args:['mcp-serve']}}}}],agent_profiles:[],api_providers:[],agents:[{
        id:'codex',name:'Codex CLI',region:'international',commands:['codex'],connection:'cli',
        execution:'native',docs_url:'https://example.test',note:'local',installed:false,
        authenticated:null,ready:false,executable:'',detail:'missing',schedulable:true}]}}
      onRefresh={async()=>{}} onComplete={complete}/>)
    fireEvent.click(screen.getByRole('button',{name:'进入工作台'}))
    expect(complete).toHaveBeenCalledWith('taskpack')
    expect(screen.getByText('未安装')).toBeInTheDocument()
    expect(screen.getByText('Generic MCP 连接配置')).toBeInTheDocument()
  })

  it('creates the first industry and queues a model-free bootstrap from onboarding', async () => {
    apiMock.mockResolvedValueOnce([]).mockResolvedValueOnce({folder:'AI',name:'人工智能'}).mockResolvedValueOnce({run_id:'r1',status:'queued',title:'init'})
    const complete=vi.fn()
    render(<SetupWizard hasIndustry={false} setup={{runtime_ready:true,data_root:'/data',taskpack_ready:true,
      privacy_note:'privacy',mcp_command:['intdog','mcp-serve'],mcp_configs:[{id:'generic',name:'Generic MCP',format:'json',value:{}}],agent_profiles:[],api_providers:[],agents:[]}}
      onRefresh={async()=>{}} onComplete={complete}/>)
    fireEvent.change(screen.getByPlaceholderText('例如：人工智能'),{target:{value:'人工智能'}})
    fireEvent.change(screen.getByPlaceholderText('例如：AI'),{target:{value:'AI'}})
    fireEvent.click(screen.getByRole('button',{name:'创建并开始研究'}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledTimes(3))
    expect(JSON.parse(String(apiMock.mock.calls[2][1]?.body)).provider).toBe('')
    expect(complete).toHaveBeenCalledWith('taskpack','AI')
  })
  it('selects the loaded daily scope and moves exactly those rows to recoverable deletion', async () => {
    apiMock.mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') return Promise.resolve({ deleted: 2 })
      return Promise.resolve({ items: [
        { id:'1',title:'Alpha',url:'https://a.test',category:'news',date:'2026-08-30',display_source:'Source A',origin:'china',identity:{date:'2026-08-30',category:'news',key:'1'} },
        { id:'2',title:'Beta',url:'https://b.test',category:'papers',date:'2026-08-30',display_source:'Author B',origin:'global',identity:{date:'2026-08-30',category:'papers',key:'2'} },
      ], total:2,next_cursor:null,selection_scope:'current_page',dates:['2026-08-30'],counts:{},origins:{} })
    })
    render(<DailyPage industry="AI" notify={notify}/>)
    await screen.findByText('Alpha')
    fireEvent.click(screen.getByRole('button',{name:'全选已加载'}))
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
      if (path.includes('/automation')) return Promise.resolve({email_delivery:false,schedules:[]})
      if (path.endsWith('/preview')) return Promise.resolve({id:'t1',kind:'daily',folder:'AI',restorable:true,restore_count:2,skip_count:1,collisions:['1 条重复文档']})
      if (init?.method==='POST') return Promise.resolve({restored:2,skipped:1})
      throw new Error(path)
    })
    render(<SystemPage industry="AI" notify={notify}/>)
    fireEvent.click(await screen.findByRole('button',{name:/恢复/}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/trash/t1/preview'))
    const previewIndex=apiMock.mock.calls.findIndex(call=>call[0].endsWith('/preview'))
    const restoreIndex=apiMock.mock.calls.findIndex(call=>call[0].endsWith('/restore'))
    expect(previewIndex).toBeGreaterThan(-1); expect(restoreIndex).toBeGreaterThan(previewIndex)
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
})
