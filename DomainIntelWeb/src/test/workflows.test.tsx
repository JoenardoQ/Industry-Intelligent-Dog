import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

const notify = vi.fn()

beforeEach(() => {
  apiMock.mockReset(); notify.mockReset()
  vi.stubGlobal('confirm', vi.fn(() => true))
})
afterEach(() => vi.unstubAllGlobals())

describe('critical workbench workflows', () => {
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
})
