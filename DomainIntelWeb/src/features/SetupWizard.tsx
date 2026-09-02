import { useState } from 'react'
import { api, type GenerateResult, type SetupPayload } from '../api'
import BootstrapStep, { type ActiveBootstrap } from './setup/BootstrapStep'
import ConnectionStep from './setup/ConnectionStep'
import DiagnosticsStep from './setup/DiagnosticsStep'
import IndustryStep from './setup/IndustryStep'

const ACTIVE_KEY='intdog.onboarding.active'

function savedBootstrap():ActiveBootstrap|null {
  try {
    const value=JSON.parse(localStorage.getItem(ACTIVE_KEY)||'null') as ActiveBootstrap|null
    return value?.folder&&value?.runId&&value?.provider?value:null
  } catch { return null }
}

export default function SetupWizard({setup,onRefresh,onComplete,hasIndustry=true}:{
  setup:SetupPayload;onRefresh:()=>Promise<void>;
  onComplete:(provider:string,folder?:string)=>void|Promise<void>;hasIndustry?:boolean
}) {
  const resumed=savedBootstrap()
  const readyAgent=setup.agents.find(item=>item.ready&&item.execution==='native')
  const [step,setStep]=useState<1|2|3|4>(resumed?4:1)
  const [selected,setSelected]=useState(localStorage.getItem('intdog.provider')||readyAgent?.id||'taskpack')
  const [active,setActive]=useState<ActiveBootstrap|null>(resumed)

  const provider=()=>selected==='taskpack'||setup.agents.some(item=>item.id===selected&&item.execution==='native')||setup.api_providers.some(item=>item.id===selected)?selected:'taskpack'
  const remember=async(value:string)=>{await api('/settings/global/*',{method:'PUT',body:JSON.stringify({provider:value,execution_mode:value==='taskpack'?'taskpack':'direct'})});localStorage.setItem('intdog.provider',value);localStorage.setItem('intdog.agent',selected);dispatchEvent(new Event('intdog:settings-changed'))}
  const returnToWorkbench=()=>{const value=provider();void remember(value).then(()=>{localStorage.setItem('intdog.onboarding.v1','complete');return onComplete(value)})}
  const begin=async(folder:string)=>{const value=provider();await remember(value);const result=await api<GenerateResult>(`/industries/${encodeURIComponent(folder)}/generate`,{method:'POST',body:JSON.stringify({action:'bootstrap'})});const next={folder,runId:result.run_id,provider:value};localStorage.setItem(ACTIVE_KEY,JSON.stringify(next));setActive(next);setStep(4)}
  const finish=()=>{if(!active)return;localStorage.removeItem(ACTIVE_KEY);localStorage.setItem('intdog.industry',active.folder);localStorage.setItem('intdog.onboarding.v1','complete');void onComplete(active.provider,active.folder)}
  const repair=async()=>{if(!active)return;const value=provider();await remember(value);const result=await api<GenerateResult>(`/jobs/${active.runId}/retry`,{method:'POST',body:JSON.stringify({provider:value,execution_mode:value==='taskpack'?'taskpack':'direct'})});const next={...active,provider:value,runId:result.run_id};localStorage.setItem(ACTIVE_KEY,JSON.stringify(next));setActive(next);setStep(4)}

  return <div className="setup-overlay"><section className="setup-dialog" role="dialog" aria-modal="true" aria-labelledby="setup-title">
    <header><div className="eyebrow">FIRST RUN · 首次启动</div><h1 id="setup-title">建立可恢复的研究工作区</h1><p>四步完成环境诊断、连接、行业和首轮知识门槛；任何一步都不会读取其他桌面应用的私有登录数据。</p></header>
    <ol className="setup-progress" aria-label="首次引导进度">{['环境诊断','研究连接','行业','首轮结果'].map((label,index)=><li key={label} className={step===index+1?'active':step>index+1?'complete':''}><span>{index+1}</span>{label}</li>)}</ol>
    {step===1&&<DiagnosticsStep setup={setup} onRefresh={onRefresh} onNext={()=>setStep(2)} onReturn={hasIndustry?returnToWorkbench:undefined}/>}
    {step===2&&<ConnectionStep setup={setup} selected={selected} setSelected={setSelected}
      onBack={()=>setStep(active?4:1)} onNext={()=>setStep(3)} onRefresh={onRefresh}
      onUseSelected={hasIndustry&&!active?returnToWorkbench:undefined}
      onRepair={active?repair:undefined}/>}
    {step===3&&<IndustryStep onBack={()=>setStep(2)} onStart={begin}/>}
    {step===4&&active&&<BootstrapStep active={active} onChange={setActive} onComplete={finish}
      onEditConnection={()=>setStep(2)}/>}
  </section></div>
}
