import { FileText, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api, type GenerateResult, type HistoryCoveragePayload, type ProductItem, type ProductsPayload } from '../api'
import ArtifactReader from './artifacts/ArtifactReader'
import { Empty, Header, Loading, RunFeedback, type Toast } from './shared'

const periods=[
  {horizon:'weekly',label:'周报',window:'7 天',action:'weekly',kind:''},
  {horizon:'monthly',label:'月报',window:'30 天',action:'monthly',kind:''},
  {horizon:'quarterly',label:'季报',window:'90 天',action:'quarterly',kind:''},
  {horizon:'semiannual',label:'半年技术报告',window:'183 天',action:'report',kind:'tech_6m'},
  {horizon:'biennial',label:'两年热点报告',window:'730 天',action:'report',kind:'popular_2y'},
  {horizon:'fiveyear',label:'五年趋势报告',window:'1,826 天',action:'report',kind:'trend_5y'},
] as const

export default function ProductsPage({industry,notify}:{industry:string;notify:(value:Toast)=>void}) {
  const [data,setData]=useState<ProductsPayload|null>(null);const [history,setHistory]=useState<HistoryCoveragePayload|null>(null);const [active,setActive]=useState<ProductItem|null>(null);const [busy,setBusy]=useState('');const [runId,setRunId]=useState('');const [error,setError]=useState('')
  const load=useCallback(async()=>{try{const [products,coverage]=await Promise.all([api<ProductsPayload>(`/industries/${industry}/products`),api<HistoryCoveragePayload>(`/industries/${industry}/history`)]);setData(products);setHistory(coverage);const all=[...Object.values(products.periodic).flat(),...products.reports,...products.deep_reports,...products.impacts];setActive(current=>current&&all.some(item=>item.id===current.id)?current:all[0]||null);setError('')}catch(reason){setError(String(reason));notify({kind:'error',text:String(reason)})}},[industry,notify])
  useEffect(()=>{setData(null);setActive(null);void load()},[load])
  const generate=async(period:typeof periods[number])=>{setBusy(period.horizon);try{const body={action:period.action,kind:period.kind};const result=await api<GenerateResult>(`/industries/${industry}/generate`,{method:'POST',body:JSON.stringify(body)});setRunId(result.run_id);notify({kind:'ok',text:`${period.label}任务已进入队列 · ${result.run_id.slice(0,12)}`})}catch(reason){notify({kind:'error',text:String(reason)})}finally{setBusy('')}}
  const groups=data?[{label:'每周',rows:data.periodic.weekly},{label:'每月',rows:data.periodic.monthly},{label:'每季',rows:data.periodic.quarterly},{label:'行业报告',rows:data.reports},{label:'深度研究',rows:data.deep_reports},{label:'影响分析',rows:data.impacts}]:[]
  const productCount=groups.reduce((total,group)=>total+group.rows.length,0)
  const lastFor=(period:typeof periods[number])=>period.horizon==='weekly'?data?.periodic.weekly[0]:period.horizon==='monthly'?data?.periodic.monthly[0]:period.horizon==='quarterly'?data?.periodic.quarterly[0]:data?.reports.find(item=>item.slug?.includes(period.kind)||item.name?.includes(period.kind))
  return <><Header eyebrow="RESEARCH PRODUCTS" title="研究产物" body="六个周期直接生成；每份产物在同一安全阅读器中显示状态、元数据、引用、限制与可视化。"/>
    <section className="period-launcher" aria-label="周期产物直接生成">{periods.map(period=>{const gate=history?.items.find(item=>item.horizon===period.horizon);const recent=lastFor(period);return <button key={period.horizon} disabled={Boolean(busy)} onClick={()=>void generate(period)}><span><strong>{period.label}</strong><small>{period.window}</small></span><em>{gate?`${gate.admitted_total.toLocaleString()} / ${gate.target.toLocaleString()} 条`:'等待覆盖数据'}</em><small>{recent?`最近成功：${recent.generated_at||recent.window_end||'已生成'}`:'尚无成功产物'}</small>{busy===period.horizon?<RefreshCw className="spin"/>:<span className={`status-pill ${gate?.ready?'completed':'partial'}`}>{gate?.ready?'可生成':'可回填'}</span>}</button>})}</section>
    <RunFeedback runId={runId}/>
    {error&&<p className="field-error" role="alert">{error}</p>}
    <div className="reader-layout"><section className="section-card product-index">{!data?<Loading label="正在载入研究产物…"/>:<>{productCount===0&&<Empty title="暂无研究产物" body="选择上方周期生成第一份可审核、可导出的研究产物。" compact/>}{groups.map(group=><div key={group.label}><h3>{group.label}<span>{group.rows.length}</span></h3>{group.rows.map((row,index)=><button className={active===row?'active':''} key={row.id||row._key||row.name||index} onClick={()=>setActive(row)}><FileText/><span><strong>{row.title||row.name||row._key||'未命名产物'}</strong><small>{row.generated_at||row.window_end||row.status||'时间未知'}</small></span></button>)}</div>)}</>}</section><section className="section-card markdown-reader"><ArtifactReader artifact={active}/></section></div>
  </>
}
