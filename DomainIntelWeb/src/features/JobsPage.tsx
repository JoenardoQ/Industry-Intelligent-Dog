import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, RefreshCw, RotateCcw, Square } from 'lucide-react'
import { api, artifactUrl, type Job } from '../api'
import { Empty, Header } from './shared'

export default function JobsPage() {
  const [rows, setRows] = useState<Job[]>([]); const [selected, setSelected] = useState<Job | null>(null); const [output, setOutput] = useState(''); const [error, setError] = useState('')
  const load = useCallback(() => api<Job[]>('/jobs').then(value => { setRows(value); setError('') }).catch(e => setError(String(e))), [])
  useEffect(() => { void load(); const timer = setInterval(load, 3000); return () => clearInterval(timer) }, [load])
  useEffect(() => { if (selected) api<{ output: string }>(`/jobs/${selected.run_id}/output`).then(value => setOutput(value.output)) }, [selected, rows])
  const cancel = async () => { if (!selected || !confirm('取消这个正在运行的任务？已写入的中间产物不会被静默删除。')) return; await api(`/jobs/${selected.run_id}/cancel`,{method:'POST'}); await load() }
  const retry = async () => { if (!selected) return; const result=await api<{run_id:string}>(`/jobs/${selected.run_id}/retry`,{method:'POST'}); await load(); setSelected(rows.find(row=>row.run_id===result.run_id)||null) }
  return <><Header eyebrow="OPERATIONS" title="任务中心" body="状态以持久化任务记录为准；运行、停滞、失败、部分完成和取消不会互相覆盖。" actions={<button className="button secondary" onClick={load}><RefreshCw/>刷新</button>}/>
    {error ? <Empty title="任务中心不可用" body={error}/> : <div className="reader-layout"><section className="section-card job-list">{rows.map(row => { const status = row.stalled ? 'stalled' : row.status; const progress=Math.round((row.progress||0)*100); return <button key={row.run_id} className={selected?.run_id === row.run_id ? 'active' : ''} onClick={() => setSelected(row)}><span className={`job-dot ${status}`}/><span><strong>{row.title}</strong><small>{row.stage||'等待阶段信息'} · {progress}%<br/>{row.updated_at} · {row.run_id.slice(0,12)}</small></span><em>{status}</em></button> })}</section><section className="section-card log-view"><div className="section-title"><div><h2>{selected?.title || '选择一个任务'}</h2>{selected?.parent_run_id&&<p className="subtle">重试自 {selected.parent_run_id.slice(0,12)}</p>}</div><div className="section-actions">{selected?.active&&<button className="button danger" onClick={()=>void cancel()}><Square/>取消</button>}{selected&&['failed','partial','cancelled','interrupted'].includes(selected.status)&&<button className="button secondary" onClick={()=>void retry()}><RotateCcw/>安全重试</button>}{selected?.artifact_path&&<a className="button secondary" href={artifactUrl(selected.artifact_path)} target="_blank" rel="noreferrer"><ExternalLink/>打开产物</a>}{selected&&<span className={`status-pill ${selected.stalled ? 'stalled' : selected.status}`}>{selected.stalled ? 'stalled' : selected.status}</span>}</div></div>{selected&&<div className="job-progress"><span style={{width:`${Math.max(0,Math.min(100,(selected.progress||0)*100))}%`}}/></div>}<pre>{selected ? output || '暂无代表性日志。' : '选择左侧任务查看阶段、进度、警告、产物路径和终态。'}</pre></section></div>}
  </>
}
