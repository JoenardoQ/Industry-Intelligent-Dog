import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

const apiMock=vi.hoisted(()=>vi.fn())
const apiTextMock=vi.hoisted(()=>vi.fn())
vi.mock('../api',async importOriginal=>{
  const actual=await importOriginal<typeof import('../api')>()
  return {...actual,api:apiMock,apiText:apiTextMock}
})

import DailyPage from '../features/DailyPage'
import KnowledgePage from '../features/KnowledgePage'
import ProductsPage from '../features/ProductsPage'
import ArtifactReader from '../features/artifacts/ArtifactReader'
import ArtifactWorkbench from '../features/research/ArtifactWorkbench'
import { ConfirmDialog } from '../features/shared'

const notify=vi.fn()
const dailyItem=(key:string,title:string,category:string,source:string)=>({
  id:`doc-${key}`,identity:{date:'2026-09-02',category,key},date:'2026-09-02',
  category,title,url:`https://example.com/${key}`,abstract:`${title} 的具体中文摘要`,
  display_source:source,origin:'rss',published_at:'2026-09-02T08:00:00+08:00',
})
const dailyPage=(items:ReturnType<typeof dailyItem>[],next_cursor:string|null,total=items.length)=>({
  items,total,next_cursor,selection_scope:'current_page' as const,dates:['2026-09-02'],
  counts:{},origins:{rss:items.length},window_start:'2026-09-01T04:00:00+08:00',
  window_end:'2026-09-02T12:00:00+08:00',timezone:'Asia/Shanghai',
  window_reason:'previous_local_day_04_to_now' as const,
})

beforeEach(()=>{apiMock.mockReset();apiTextMock.mockReset();notify.mockReset();vi.stubGlobal('confirm',vi.fn(()=>true))})
afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear()})

describe('reader-facing intelligence workflows',()=>{
  it('defaults to title sorting and selects every filtered Daily page before recoverable deletion',async()=>{
    const first=[dailyItem('1','Alpha 芯片发布','news','Reuters'),dailyItem('2','Beta 开源更新','github','open-source-dev')]
    const second=[dailyItem('3','Gamma 论文','papers','Li Ming, Ada Chen')]
    apiMock.mockImplementation((path:string,init?:RequestInit)=>{
      if(path.includes('/daily?')&&path.includes('cursor=next'))return Promise.resolve(dailyPage(second,null,3))
      if(path.includes('/daily?'))return Promise.resolve(dailyPage(first,'next',3))
      if(path==='/industries/AI/daily'&&init?.method==='DELETE')return Promise.resolve({deleted:3})
      if(path==='/industries/AI/generate')return Promise.resolve({run_id:'run-1',status:'queued'})
      throw new Error(path)
    })
    render(<DailyPage industry="AI" notify={notify}/>)
    expect(await screen.findByText('Alpha 芯片发布')).toBeInTheDocument()
    expect(apiMock.mock.calls[0][0]).toContain('sort=title')
    expect(screen.getByRole('option',{name:'按类别'})).toBeInTheDocument()
    expect(screen.getByRole('option',{name:'按来源'})).toBeInTheDocument()
    expect(screen.getByRole('option',{name:'按发布时间'})).toBeInTheDocument()
    expect(screen.getByText(/2026-09-01T04:00:00/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'全选当前筛选'}))
    expect(await screen.findByText('Gamma 论文')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:/一键删除 3/})).toBeEnabled()
    fireEvent.click(screen.getByRole('button',{name:/一键删除 3/}))
    await waitFor(()=>expect(apiMock).toHaveBeenCalledWith('/industries/AI/daily',expect.objectContaining({method:'DELETE'})))
    const deletion=apiMock.mock.calls.find(call=>call[0]==='/industries/AI/daily')
    expect(JSON.parse(String(deletion?.[1]?.body)).items).toHaveLength(3)
  })

  it('renders GFM in the shared reader without executing raw HTML or javascript URLs',async()=>{
    apiTextMock.mockResolvedValue('# 报告\n\n| 项目 | 状态 |\n| --- | --- |\n| 证据 | partial |\n\n<script>alert(1)</script>\n\n[危险](javascript:alert(2))\n\n```js\nconst safe = true\n```')
    const {container}=render(<ArtifactReader artifact={{id:'a1',title:'半导体周报',status:'partial',report_file:'/data/report.md',limitations:['来源覆盖不足'],references:[{title:'官方披露',url:'https://official.example/report'}],visualization:{}}}/>)
    expect(await screen.findByRole('heading',{name:'报告'})).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull()
    expect(screen.getByText(/来源覆盖不足/)).toBeInTheDocument()
    expect(screen.getByRole('link',{name:'官方披露'})).toHaveAttribute('href','https://official.example/report')
    expect((await axe(container)).violations).toEqual([])
  })

  it('keeps artifact metadata and summary readable when the body cannot be loaded',async()=>{
    apiTextMock.mockRejectedValue(new Error('文件不存在'))
    render(<ArtifactReader artifact={{id:'a2',title:'产业报告',status:'failed',summary:'已保存的摘要',provider:'codex',model:'gpt-test',report_file:'/data/missing.md',visualization:{}}}/>)
    expect(await screen.findByText('读取失败')).toBeInTheDocument()
    expect(screen.getByText('已保存的摘要')).toBeInTheDocument()
    expect(screen.getByText(/codex \/ gpt-test/)).toBeInTheDocument()
  })

  it('exposes the offline single-file artifact and machine-readable quality failures',async()=>{
    apiTextMock.mockResolvedValue('# 简报\n\n正文')
    render(<ArtifactReader artifact={{id:'portable-1',title:'离线周报',status:'partial',report_file:'/data/report.md',portable_file:'/data/report.portable.html',quality:{passed:false,failures:[{code:'claim_without_evidence'}]},visualization:{}}}/>)
    expect(await screen.findByRole('link',{name:/离线单文件/})).toHaveAttribute('href',expect.stringContaining('report.portable.html'))
    expect(screen.getByText('成品质量门未通过')).toBeInTheDocument()
    expect(screen.getByText('claim_without_evidence')).toBeInTheDocument()
  })

  it('shows the persisted chain and filtered entity detail with evidence',async()=>{
    apiMock.mockImplementation((path:string)=>{
      if(path.endsWith('/overview'))return Promise.resolve({industry:{name:'AI'},stats:{sources:8,documents:12,entities:1,relations:1},source_categories:{},latest_document_date:null,chain:[{id:'n1',name:'算力',description:'基础设施',entity_count:1}],chain_edges:[],entities:[]})
      if(path.includes('/knowledge/entities?'))return Promise.resolve({items:[{id:'e1',name:'寒武纪',name_en:'Cambricon',kind:'company',country:'CN',chain:'算力',role:'芯片',status:'accepted',evidence_count:2}],total:1,offset:0,limit:50,next_offset:null})
      if(path.endsWith('/knowledge/entities/e1'))return Promise.resolve({id:'e1',kind:'company',canonical_name:'寒武纪',name_en:'Cambricon',country:'CN',status:'accepted',aliases:[],roles:[{role:'芯片',chain:'算力',status:'accepted',evidence_count:2}],relations:[{id:'r1',predicate:'supplies',src_entity_id:'e1',dst_entity_id:'e2',src_name:'寒武纪',dst_name:'云服务商'}],claims:[{id:'c1',predicate:'develops',object:{product:'MLU'},status:'accepted',evidence:[{relation:'supports',document_url:'https://official.example/cambricon',document_title:'官方披露'}]}],evidence_count:2})
      throw new Error(path)
    })
    const {container}=render(<KnowledgePage industry="AI"/>)
    for(const kind of ['government_institution','investment_institution','standard','policy'])
      expect(await screen.findByRole('option',{name:kind})).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button',{name:/寒武纪/}))
    expect(await screen.findByRole('dialog')).toHaveTextContent('官方披露')
    expect(screen.queryByText('产业链尚未建立')).not.toBeInTheDocument()
    expect((await axe(container)).violations).toEqual([])
  })

  it('presents all six periods as direct parallel actions',async()=>{
    apiMock.mockImplementation((path:string)=>{
      if(path.endsWith('/products'))return Promise.resolve({periodic:{weekly:[],monthly:[],quarterly:[]},reports:[],deep_reports:[],impacts:[]})
      if(path.endsWith('/history'))return Promise.resolve({items:[]})
      throw new Error(path)
    })
    render(<ProductsPage industry="AI" notify={notify}/>)
    await screen.findByText('每周')
    for(const label of ['周报','月报','季报','半年','两年','五年'])expect(screen.getByRole('button',{name:new RegExp(label)})).toBeInTheDocument()
  })

  it('keeps existing products readable when history coverage is unavailable',async()=>{
    apiTextMock.mockResolvedValue('# 已有周报')
    apiMock.mockImplementation((path:string)=>{
      if(path.endsWith('/products'))return Promise.resolve({periodic:{weekly:[{id:'weekly-1',title:'已有周报',status:'completed',report_file:'/data/weekly.md',visualization:{}}],monthly:[],quarterly:[]},reports:[],deep_reports:[],impacts:[]})
      if(path.endsWith('/history'))return Promise.reject(new Error('history unavailable'))
      throw new Error(path)
    })
    render(<ProductsPage industry="AI" notify={notify}/>)
    expect(await screen.findAllByText('已有周报')).not.toHaveLength(0)
    expect(screen.getByText('历史覆盖暂时无法读取')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'重试历史覆盖'})).toBeInTheDocument()
    expect(screen.queryByText('研究产物不可用')).not.toBeInTheDocument()
  })

  it('uses one research workbench for direct generation and existing artifact reading',async()=>{
    apiTextMock.mockResolvedValue('# 行业报告\n\n这是可核验的长中文与 English evidence summary。')
    const artifact={id:'report-1',title:'人工智能行业报告',status:'completed',report_file:'/data/report.md',visualization:{}}
    render(<ArtifactWorkbench industry="AI" artifacts={[artifact]} notify={notify}/>)
    for(const label of ['行业研究报告','产业链深度研究','竞争格局报告','运行 Intelligence Lab'])
      expect(screen.getByRole('button',{name:new RegExp(label)})).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:/人工智能行业报告/}))
    expect(await screen.findByRole('heading',{name:'行业报告'})).toBeInTheDocument()
  })

  it('confirms destructive lifecycle actions accessibly and restores trigger focus',async()=>{
    const confirm=vi.fn();const cancel=vi.fn();const trigger=document.createElement('button')
    trigger.textContent='退出 IntDog';document.body.append(trigger);trigger.focus()
    const {container,rerender}=render(<ConfirmDialog open title="安全退出 IntDog" body="停止本地服务？" confirmLabel="退出并停止" returnFocus={trigger} onConfirm={confirm} onCancel={cancel}/>)
    expect(screen.getByRole('dialog',{name:'安全退出 IntDog'})).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'取消'})).toHaveFocus()
    fireEvent.keyDown(screen.getByRole('dialog'),{key:'Escape'})
    expect(cancel).toHaveBeenCalled()
    expect((await axe(container)).violations).toEqual([])
    rerender(<ConfirmDialog open={false} title="安全退出 IntDog" body="停止本地服务？" confirmLabel="退出并停止" returnFocus={trigger} onConfirm={confirm} onCancel={cancel}/>)
    expect(trigger).toHaveFocus()
  })
})
