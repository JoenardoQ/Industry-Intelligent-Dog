import { useEffect, useState } from 'react'
import { ArrowRight, BookOpen, Play, RefreshCw } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, artifactUrl, type ChainNode, type GenerateResult } from '../api'

export type Toast = { kind: 'ok' | 'error'; text: string } | null

export function Header({ eyebrow, title, body, actions }: { eyebrow: string; title: string; body: string; actions?: React.ReactNode }) {
  return <div className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{body}</p></div>{actions && <div className="header-actions">{actions}</div>}</div>
}

export function ChainGraph({ nodes }: { nodes: ChainNode[] }) {
  if (!nodes.length) return <Empty title="产业链尚未建立" body="初始化研究后，产业环节会按上下游顺序显示在这里。" compact/>
  return <div className="chain-viewport">{nodes.map((node, index) => <div className="chain-step" key={node.id || node.name}>
    <div className="chain-node"><span>{index + 1}</span><strong>{node.name}</strong><small>{node.description || `${node.entity_count || 0} 个实体`}</small><em className={`coverage coverage-${node.coverage_status || 'unknown'}`}>{node.coverage_status || 'unknown'}</em></div>
    {index < nodes.length - 1 && <ArrowRight className="chain-arrow"/>}
  </div>)}</div>
}

export function Markdown({ path, fallback }: { path?: string; fallback: string }) {
  const [text, setText] = useState(fallback)
  useEffect(() => { setText(fallback); if (path) fetch(artifactUrl(path)).then(r => r.text()).then(setText).catch(() => setText(fallback)) }, [path, fallback])
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>
}

export function Generate({ industry, action, label, notify }: { industry: string; action: string; label: string; notify: (t: Toast) => void }) {
  const [busy, setBusy] = useState(false)
  const run = async () => { setBusy(true); try { const result = await api<GenerateResult>(`/industries/${industry}/generate`, { method:'POST', body:JSON.stringify({action}) }); notify({kind:'ok',text:`任务已进入队列 · ${result.run_id.slice(0,12)}`}); location.hash='/jobs' } catch(e) { notify({kind:'error',text:String(e)}) } finally { setBusy(false) } }
  return <button className="button primary" disabled={busy} onClick={run}>{busy ? <RefreshCw className="spin"/> : <Play/>}{busy ? '正在创建任务' : label}</button>
}

export function Loading({ label }: { label: string }) { return <div className="loading"><span/><p>{label}</p></div> }
export function Empty({ title, body, compact=false }: { title: string; body: string; compact?: boolean }) { return <div className={`empty ${compact ? 'compact' : ''}`}><BookOpen/><h2>{title}</h2><p>{body}</p></div> }
