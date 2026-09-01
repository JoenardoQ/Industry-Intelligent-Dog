import { CheckCircle2, RefreshCw, Square } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api, type GenerateResult, type Job, type OverviewPayload } from '../../api'

export type ActiveBootstrap={folder:string;runId:string;provider:string}

export default function BootstrapStep({active,onChange,onComplete}:{active:ActiveBootstrap;onChange:(value:ActiveBootstrap)=>void;onComplete:()=>void}) {
  const [job,setJob]=useState<Job|null>(null);const [overview,setOverview]=useState<OverviewPayload|null>(null);const [error,setError]=useState('')
  const load=useCallback(async()=>{try{const [jobs,current]=await Promise.all([api<Job[]>('/jobs'),api<OverviewPayload>(`/industries/${active.folder}/overview`)]);setJob(jobs.find(item=>item.run_id===active.runId)||null);setOverview(current);setError('')}catch(reason){setError(String(reason))}},[active.folder,active.runId])
  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(),2500);return()=>window.clearInterval(timer)},[load])
  const cancel=async()=>{await api(`/jobs/${active.runId}/cancel`,{method:'POST'});await load()}
  const retry=async()=>{const next=await api<GenerateResult>(`/jobs/${active.runId}/retry`,{method:'POST'});const value={...active,runId:next.run_id};localStorage.setItem('intdog.onboarding.active',JSON.stringify(value));onChange(value)}
  const counts=overview?.stats
  const gates=[{label:'信息源门槛',current:counts?.sources||0,target:8},{label:'产业链门槛',current:counts?.chain_nodes||0,target:1},{label:'实体门槛',current:counts?.entities||0,target:1}]
  const terminal=Boolean(job&&['completed','partial','failed','paused','cancelled','interrupted'].includes(job.status))
  return <section className="setup-step" aria-labelledby="bootstrap-title"><div><span className="eyebrow">STEP 4 / 4</span><h2 id="bootstrap-title">建立首轮行业知识</h2><p>任务状态、阶段和三道门槛保留在这里；关闭后再次打开会继续恢复本次进度。</p></div>
    <div className="bootstrap-status"><strong>{job?.title||'正在读取任务'}</strong><span className={`status-pill ${job?.status||'running'}`}>{job?.status||'loading'}</span><progress max="100" value={job?.progress||0}/><p>{job?.stage||'等待首个检查点'} · {job?.progress||0}%</p></div>
    <div className="gate-list">{gates.map(gate=><article key={gate.label}><CheckCircle2/><div><strong>{gate.label}</strong><span>{gate.current} / {gate.target}</span></div><em>{gate.current>=gate.target?'通过':'继续收集'}</em></article>)}</div>
    {job?.checkpoint&&Object.keys(job.checkpoint).length?<pre className="bootstrap-log">{JSON.stringify(job.checkpoint,null,2)}</pre>:null}
    {error&&<p className="field-error" role="alert">{error}</p>}
    <footer>{job?.active&&<button className="button secondary" onClick={()=>void cancel()}><Square/>取消首次研究</button>}{terminal&&job?.status!=='completed'&&<button className="button secondary" onClick={()=>void retry()}><RefreshCw/>恢复并重试</button>}<button className="button primary" onClick={onComplete}>进入行业概览</button></footer>
  </section>
}
