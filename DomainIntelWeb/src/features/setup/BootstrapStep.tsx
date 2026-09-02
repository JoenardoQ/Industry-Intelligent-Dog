import { AlertTriangle, CheckCircle2, CircleDashed, LoaderCircle, RefreshCw, Square } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type GenerateResult, type Job } from '../../api'

export type ActiveBootstrap={folder:string;runId:string;provider:string}
type StageState='waiting'|'running'|'passed'|'partial'|'failed'|'skipped'

const STAGES=[['sources','信息源门槛'],['value_chain','产业链门槛'],['entities','实体覆盖门槛']] as const
const STATE_LABEL:Record<StageState,string>={waiting:'等待中',running:'执行中',passed:'已通过',partial:'部分完成',failed:'失败',skipped:'未执行'}
const JOB_LABEL:Record<string,string>={queued:'排队中',running:'执行中',completed:'已完成',partial:'部分完成',failed:'失败',paused:'已暂停',cancelled:'已取消',interrupted:'已中断',cancelling:'正在取消'}
const STAGE_LABEL:Record<string,string>={provider_preflight:'检查研究连接',source_request:'检索权威信息源',source_gate:'审查信息源门槛',value_chain_request:'梳理产业链',value_chain_gate:'审查产业链门槛',entity_request:'检索实体与研究组',entity_gate:'审查实体覆盖门槛',persisting:'保存首轮知识',completed:'首轮研究完成'}
const FAILURE_LABEL:Record<string,string>={sources:'信息源门槛',value_chain:'产业链门槛',entities:'实体覆盖门槛'}

function checkpointState(job:Job|null,key:string):StageState {
  const checkpoint=job?.checkpoint as {stage_states?:Record<string,unknown>}|undefined
  const value=checkpoint?.stage_states?.[key]
  if(typeof value==='string'&&value in STATE_LABEL)return value as StageState
  if(job?.result_kind==='task_package')return 'skipped'
  if(job?.status==='completed')return 'passed'
  return 'waiting'
}

export default function BootstrapStep({active,onChange,onComplete,onEditConnection}:{
  active:ActiveBootstrap;onChange:(value:ActiveBootstrap)=>void;onComplete:()=>void;onEditConnection?:()=>void
}) {
  const [job,setJob]=useState<Job|null>(null);const [error,setError]=useState('')
  const load=useCallback(async()=>{try{const jobs=await api<Job[]>('/jobs');setJob(jobs.find(item=>item.run_id===active.runId)||null);setError('')}catch(reason){setError(String(reason))}},[active.runId])
  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(),2500);return()=>window.clearInterval(timer)},[load])
  const cancel=async()=>{await api(`/jobs/${active.runId}/cancel`,{method:'POST'});await load()}
  const retry=async()=>{const next=await api<GenerateResult>(`/jobs/${active.runId}/retry`,{method:'POST'});const value={...active,runId:next.run_id};localStorage.setItem('intdog.onboarding.active',JSON.stringify(value));onChange(value)}
  const terminal=Boolean(job&&['completed','partial','failed','paused','cancelled','interrupted'].includes(job.status))
  const packageOnly=job?.result_kind==='task_package'
  const checkpoint=job?.checkpoint as {gate_failures?:unknown}|undefined
  const failures=useMemo(()=>Array.isArray(checkpoint?.gate_failures)?checkpoint.gate_failures.filter(item=>typeof item==='string') as string[]:[],[checkpoint])
  const connectionFailure=['authentication','configuration','invalid_model','unsupported_tool','permission','quota'].includes(job?.error_category||'')
  return <section className="setup-step" aria-labelledby="bootstrap-title"><div><span className="eyebrow">STEP 4 / 4</span><h2 id="bootstrap-title">建立首轮行业知识</h2><p>三道门槛按顺序自动执行。通过门槛只会生成待复核草稿，不会把模型输出直接变成正式事实。</p></div>
    <div className="bootstrap-status" aria-live="polite"><strong>{job?.title||'正在读取任务'}</strong><span className={`status-pill ${job?.status||'running'}`}>{JOB_LABEL[job?.status||'']||'读取中'}</span><progress max="100" value={job?.progress||0}/><p>{job?.stage?(STAGE_LABEL[job.stage]||'正在推进当前阶段'):'等待首个检查点'} · {job?.progress||0}%{job?.elapsed_seconds?` · 已用 ${job.elapsed_seconds} 秒`:''}</p></div>
    {packageOnly&&job?.status==='completed'&&<p className="inline-notice">任务包已创建，尚未执行研究。请交给兼容 Agent 执行并导回结果。</p>}
    <div className="gate-list">{STAGES.map(([key,label])=>{const state=checkpointState(job,key);const Icon=state==='passed'?CheckCircle2:state==='running'?LoaderCircle:state==='partial'||state==='failed'?AlertTriangle:CircleDashed;return <article key={key}><Icon className={state==='running'?'spin':''}/><div><strong>{label}</strong><span>{STATE_LABEL[state]}</span></div><em>{state}</em></article>})}</div>
    {failures.length>0&&<p className="field-error" role="alert">未通过检查：{failures.map(value=>FAILURE_LABEL[value]||value).join('、')}</p>}
    {job?.error&&<p className="field-error" role="alert">{job.error_category?`${job.error_category} · `:''}{job.error}</p>}
    {error&&<p className="field-error" role="alert">{error}</p>}
    <footer>{job?.active&&<button className="button secondary" onClick={()=>void cancel()}><Square/>取消首次研究</button>}{connectionFailure&&onEditConnection&&<button className="button secondary" onClick={onEditConnection}>编辑研究连接</button>}{terminal&&job?.status!=='completed'&&<button className="button secondary" onClick={()=>void retry()}><RefreshCw/>恢复并重试</button>}{job&&['completed','partial'].includes(job.status)&&<button className="button primary" onClick={onComplete}>{packageOnly?'返回工作台':job.status==='partial'?'查看已保留内容':'进入行业概览'}</button>}</footer>
  </section>
}
