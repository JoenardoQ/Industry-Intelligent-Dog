import { useEffect, useRef, useState } from 'react'
import { ArrowRight, BookOpen, Play, RefreshCw } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, apiText, type ChainEdge, type ChainNode, type GenerateResult, type Job } from '../api'

export type Toast = { kind: 'ok' | 'error'; text: string } | null

export function ConfirmDialog({open,title,body,confirmLabel='确认',cancelLabel='取消',danger=false,returnFocus,onConfirm,onCancel}:{open:boolean;title:string;body:string;confirmLabel?:string;cancelLabel?:string;danger?:boolean;returnFocus?:HTMLElement|null;onConfirm:()=>void;onCancel:()=>void}) {
  const cancelRef=useRef<HTMLButtonElement>(null)
  const confirmRef=useRef<HTMLButtonElement>(null)
  useEffect(()=>{if(open)cancelRef.current?.focus();else returnFocus?.focus()},[open,returnFocus])
  if(!open)return null
  return <div className="confirm-overlay" onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onCancel()}else if(event.key==='Tab'){const next=event.shiftKey?confirmRef.current:cancelRef.current;if((event.shiftKey&&document.activeElement===cancelRef.current)||(!event.shiftKey&&document.activeElement===confirmRef.current)){event.preventDefault();next?.focus()}}}}>
    <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-body">
      <h2 id="confirm-title">{title}</h2><p id="confirm-body">{body}</p>
      <footer><button ref={cancelRef} className="button secondary" onClick={onCancel}>{cancelLabel}</button><button ref={confirmRef} className={`button ${danger?'danger':'primary'}`} onClick={onConfirm}>{confirmLabel}</button></footer>
    </section>
  </div>
}

export function Header({ eyebrow, title, body, actions }: { eyebrow: string; title: string; body: string; actions?: React.ReactNode }) {
  return <div className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{body}</p></div>{actions && <div className="header-actions">{actions}</div>}</div>
}

export function ChainGraph({ nodes, edges=[] }: { nodes: ChainNode[]; edges?: ChainEdge[] }) {
  if (!nodes.length) return <Empty title="产业链尚未建立" body="初始化研究后，产业环节会按上下游顺序显示在这里。" compact/>
  const byId=new Map(nodes.map(node=>[node.id,node]))
  if(edges.length) return <div className="chain-viewport directed-chain" role="list" aria-label="持久化产业链有向关系">{edges.map(edge=>{
    const src=byId.get(edge.src_node_id);const dst=byId.get(edge.dst_node_id)
    return <div className="chain-edge" role="listitem" key={edge.id}><div className="chain-node"><strong>{src?.name||edge.src_name}</strong><small>{src?.description||`${src?.entity_count||0} 个实体`}</small></div><div className="edge-label"><ArrowRight className="chain-arrow"/><strong>{edge.relation}</strong><small>{edge.status} · {edge.evidence_count} 条证据</small></div><div className="chain-node"><strong>{dst?.name||edge.dst_name}</strong><small>{dst?.description||`${dst?.entity_count||0} 个实体`}</small></div></div>})}</div>
  return <div className="chain-viewport unlinked-chain" aria-label="尚无已保存产业链关系">{nodes.map((node,index)=><div className="chain-node" key={node.id||node.name}><span>{index+1}</span><strong>{node.name}</strong><small>{node.description||`${node.entity_count||0} 个实体`} · 顺序待证</small><em className={`coverage coverage-${node.coverage_status||'unknown'}`}>{node.coverage_status||'unknown'}</em></div>)}</div>
}

export function Markdown({ path, fallback }: { path?: string; fallback: string }) {
  const [text, setText] = useState(fallback)
  useEffect(() => { setText(fallback); if (path) apiText(`/artifact?path=${encodeURIComponent(path)}`).then(setText).catch(() => setText(fallback)) }, [path, fallback])
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>
}

export function Generate({ industry, action, label, notify }: { industry: string; action: string; label: string; notify: (t: Toast) => void }) {
  const [busy, setBusy] = useState(false);const [runId,setRunId]=useState('')
  const run = async () => { setBusy(true); try { const result = await api<GenerateResult>(`/industries/${industry}/generate`, { method:'POST', body:JSON.stringify({action}) }); setRunId(result.run_id);notify({kind:'ok',text:`任务已进入队列 · ${result.run_id.slice(0,12)}`}) } catch(e) { notify({kind:'error',text:String(e)}) } finally { setBusy(false) } }
  return <div className="inline-run"><button className="button primary" disabled={busy} onClick={run}>{busy ? <RefreshCw className="spin"/> : <Play/>}{busy ? '正在创建任务' : label}</button><RunFeedback runId={runId}/></div>
}

export function RunFeedback({runId}:{runId:string}) {
  const [job,setJob]=useState<Job|null>(null)
  useEffect(()=>{if(!runId){setJob(null);return}let current=true
    const load=()=>api<Job[]>('/jobs').then(rows=>{if(current)setJob(rows.find(row=>row.run_id===runId)||null)}).catch(()=>{})
    void load();const timer=setInterval(load,2500);return()=>{current=false;clearInterval(timer)}
  },[runId])
  if(!runId)return null
  const status=job?.status||'queued';const progress=job?.progress_mode==='determinate'?` · ${job.progress}%`:''
  return <div className={`inline-run-status ${status}`} role="status" aria-live="polite"><span>{job?.stage||'已进入任务队列'}{progress}</span><small>{runId.slice(0,12)} · {job?.elapsed_seconds||0} 秒</small><a href="#/jobs">查看任务详情</a></div>
}

export function Loading({ label }: { label: string }) { return <div className="loading"><span/><p>{label}</p></div> }
export function Empty({ title, body, compact=false }: { title: string; body: string; compact?: boolean }) { return <div className={`empty ${compact ? 'compact' : ''}`}><BookOpen/><h2>{title}</h2><p>{body}</p></div> }
