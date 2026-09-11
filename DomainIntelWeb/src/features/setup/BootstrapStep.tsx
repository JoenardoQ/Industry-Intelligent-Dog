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
  const gates=[{label:'已保存来源',current:counts?.sources||0},{label:'已保存产业链节点',current:counts?.chain_nodes||0},{label:'已保存实体',current:counts?.entities||0}]
  const terminal=Boolean(job&&['completed','partial','failed','paused','cancelled','interrupted'].includes(job.status))
  return <section className="setup-step" aria-labelledby="bootstrap-title"><div><span className="eyebrow">STEP 4 / 4</span><h2 id="bootstrap-title">建立首轮行业知识</h2><p>任务状态、阶段和三道门槛保留在这里；关闭后再次打开会继续恢复本次进度。</p></div>
    <div className="bootstrap-status"><strong>{job?.title||'正在读取任务'}</strong><span className={`status-pill ${job?.status||'running'}`}>{job?.status||'loading'}</span><progress max="100" value={job?.progress_mode==='determinate'?(job.progress||0):undefined}/><p>{job?.stage||'等待首个检查点'} · {job?.progress_mode==='determinate'?`${job.progress||0}%`:'进度暂不可估算'} · 已用 {job?.elapsed_seconds||0} 秒</p></div>
    <div className="gate-list">{gates.map(gate=><article key={gate.label}><CheckCircle2/><div><strong>{gate.label}</strong><span>{gate.current}</span></div></article>)}</div>
    <p>数量不代表核验通过。来源发现完成后，请进入「信息源」，核实并采用候选，再点击「继续生成产业链与实体」。失败重试会复用仍有效的已完成阶段。</p>
    {job?.checkpoint&&Object.keys(job.checkpoint).length?<pre className="bootstrap-log">{JSON.stringify(job.checkpoint,null,2)}</pre>:null}
    {error&&<p className="field-error" role="alert">{error}</p>}
    {job?.error&&<p className="field-error" role="alert">{job.error}</p>}
    <footer>{job?.active&&<button className="button secondary" onClick={()=>void cancel().catch(reason=>setError(String(reason)))}><Square/>取消首次研究</button>}{terminal&&job?.status!=='completed'&&<button className="button secondary" onClick={()=>void retry().catch(reason=>setError(String(reason)))}><RefreshCw/>恢复并重试</button>}<button className="button primary" onClick={onComplete}>进入行业概览</button></footer>
  </section>
}
