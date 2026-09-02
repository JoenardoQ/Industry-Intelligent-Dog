import { BarChart3, FileText, Network, Play, RefreshCw, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type GenerateResult, type Job, type ProductItem } from '../../api'
import { ChainGraph, RunFeedback, type Toast } from '../shared'
import ArtifactReader from '../artifacts/ArtifactReader'

const actions=[
  {label:'行业研究报告',action:'report',kind:'tech_6m',icon:BarChart3},
  {label:'产业链深度研究',action:'deep_report',kind:'chain',icon:Network},
  {label:'竞争格局报告',action:'deep_report',kind:'landscape',icon:BarChart3},
  {label:'运行 Intelligence Lab',action:'lab',kind:'',icon:Sparkles},
] as const

export default function ArtifactWorkbench({industry,artifacts,notify,onTerminal}:{industry:string;artifacts:ProductItem[];notify:(value:Toast)=>void;onTerminal?:(job:Job)=>void}) {
  const [busy,setBusy]=useState('');const [event,setEvent]=useState('');const [runId,setRunId]=useState('')
  const [active,setActive]=useState<ProductItem|null>(artifacts[0]||null)
  useEffect(()=>setActive(current=>current&&artifacts.includes(current)?current:artifacts[0]||null),[artifacts])
  const run=async(action:string,kind='',eventText='')=>{const id=`${action}:${kind}`;setBusy(id);try{const result=await api<GenerateResult>(`/industries/${industry}/generate`,{method:'POST',body:JSON.stringify({action,kind,event:eventText})});setRunId(result.run_id);notify({kind:'ok',text:`任务已进入队列 · ${result.run_id.slice(0,12)}`})}catch(reason){notify({kind:'error',text:String(reason)})}finally{setBusy('')}}
  const graph=artifacts.find(item=>(item.visualization?.directed_graph?.nodes??[]).length)?.visualization?.directed_graph
  const graphNodes=graph?.nodes??[];const graphEdges=graph?.edges??[]
  return <section className="section-card artifact-workbench"><div className="section-title"><div><h2>研究与图表工作台</h2><p className="subtle">直接生成、选择并安全阅读产物；任务保留 Provider、证据、限制和运行状态。</p></div></div><div className="direct-action-grid">{actions.map(({label,action,kind,icon:Icon})=><button key={label} className="direct-action" disabled={Boolean(busy)} onClick={()=>void run(action,kind)}><Icon/><span><strong>{label}</strong><small>{action==='lab'?'证据网络、场景与优先级':'文字报告 + 可视化 sidecar'}</small></span>{busy===`${action}:${kind}`?<RefreshCw className="spin"/>:<Play/>}</button>)}</div><form className="impact-direct" onSubmit={form=>{form.preventDefault();void run('impact','',event)}}><label><span>事件影响分析</span><input value={event} onChange={change=>setEvent(change.target.value)} required placeholder="输入政策、技术、融资或供应链事件"/></label><button className="button primary" disabled={!event.trim()||Boolean(busy)}><Play/>生成影响分析与有向图</button></form><RunFeedback runId={runId} onTerminal={onTerminal}/>{artifacts.length?<div className="workbench-reader"><nav aria-label="研究产物">{artifacts.map((item,index)=><button key={item.id||item._key||index} className={active===item?'active':''} onClick={()=>setActive(item)}><FileText/><span>{item.title||item.name||item._key||'未命名产物'}</span></button>)}</nav><div className="markdown-reader"><ArtifactReader artifact={active||artifacts[0]}/></div></div>:null}{graphNodes.length?<div className="embedded-chain"><span className="eyebrow">LATEST RESEARCH GRAPH</span><ChainGraph nodes={graphNodes} edges={graphEdges}/></div>:null}</section>
}
