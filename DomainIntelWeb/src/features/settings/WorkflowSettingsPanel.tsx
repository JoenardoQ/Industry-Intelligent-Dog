import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Save } from 'lucide-react'
import { api, type ClientPath, type SetupPayload, type WorkflowSettings } from '../../api'
import { type Toast } from '../shared'

const operations=[['*','所有任务'],['bootstrap','行业初始化'],['daily','每日情报'],['coverage','覆盖检索'],['history','历史回填'],['report','行业报告'],['deep_report','深度研究'],['impact','影响分析'],['lab','Intelligence Lab']] as const

export default function WorkflowSettingsPanel({industry,setup,notify}:{industry:string;setup:SetupPayload|null;notify:(value:Toast)=>void}){
  const [operation,setOperation]=useState('*');const [scope,setScope]=useState<'global'|'industry'>('global')
  const [state,setState]=useState<WorkflowSettings|null>(null);const [provider,setProvider]=useState('taskpack');const [pipeline,setPipeline]=useState<'aggregate'|'generate'>('generate');const [busy,setBusy]=useState(false)
  const load=useCallback(async()=>{if(!industry)return;try{const value=await api<WorkflowSettings>(`/settings/effective?folder=${encodeURIComponent(industry)}&operation=${encodeURIComponent(operation)}`);setState(value);setProvider(value.provider);setPipeline(value.pipeline_mode)}catch(error){notify({kind:'error',text:String(error)})}},[industry,operation,notify])
  useEffect(()=>{void load()},[load])
  const settingsPath=()=>((scope==='global'?`/settings/global/${operation}`:`/industries/${encodeURIComponent(industry)}/settings/${operation}`) as ClientPath)
  const save=async()=>{setBusy(true);try{await api(settingsPath(),{method:'PUT',body:JSON.stringify({provider,execution_mode:provider==='taskpack'?'taskpack':'direct',pipeline_mode:pipeline})});dispatchEvent(new Event('intdog:settings-changed'));notify({kind:'ok',text:scope==='global'?'全局默认已保存；行业自定义保持不变':'当前行业自定义设置已保存'});await load()}catch(error){notify({kind:'error',text:String(error)})}finally{setBusy(false)}}
  const reset=async()=>{setBusy(true);try{await api(settingsPath(),{method:'DELETE'});dispatchEvent(new Event('intdog:settings-changed'));notify({kind:'ok',text:'已恢复继承设置'});await load()}catch(error){notify({kind:'error',text:String(error)})}finally{setBusy(false)}}
  const hasIndustryOverride=Object.values(state?.provenance||{}).some(value=>value==='industry'||value==='industry_task')
  const providers=[{id:'taskpack',name:'通用任务包（手动交给任意 Agent）'},...(setup?.agents||[]).filter(item=>item.execution==='native').map(item=>({id:item.id,name:item.name})),...(setup?.api_providers||[]).map(item=>({id:item.id,name:item.name}))]
  return <section className="section-card workflow-settings" id="workflow-settings"><div className="section-title"><div><h2>智能体与任务默认设置</h2><p className="subtle">所有行业默认共享同一设置；行业自定义只覆盖当前行业，后续全局修改不会替换它。</p></div><button className="button secondary" onClick={()=>void load()}><RefreshCw/>重新读取</button></div>
    {hasIndustryOverride&&<p className="inheritance-note">当前行业保留自定义设置；带有行业来源的字段不会被全局默认覆盖。</p>}
    <div className="workflow-settings-form">
      <label><span>应用范围</span><select aria-label="应用范围" value={scope} onChange={event=>setScope(event.target.value as typeof scope)}><option value="global">全局默认</option><option value="industry">仅当前行业</option></select></label>
      <label><span>任务</span><select aria-label="任务范围" value={operation} onChange={event=>setOperation(event.target.value)}>{operations.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <label><span>默认智能体</span><select aria-label="默认智能体" value={provider} onChange={event=>setProvider(event.target.value)}>{providers.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label><span>周期产物</span><select aria-label="周期产物模式" value={pipeline} onChange={event=>setPipeline(event.target.value as typeof pipeline)}><option value="generate">采集并生成报告</option><option value="aggregate">仅聚合已有情报</option></select></label>
      <button className="button primary" disabled={busy||!industry} onClick={()=>void save()}><Save/>{busy?'正在保存':scope==='global'?'保存全局默认':'保存行业自定义'}</button>
      <button className="button tertiary" disabled={busy||!industry} onClick={()=>void reset()}>恢复继承</button>
    </div>
    <small className="settings-provenance">当前有效：{state?.provider||'读取中'} · 来源 {state?.provenance.provider||'system'}。采集规模由产品策略统一控制：来源和常规情报为旧基线的 1.5 倍，论文为 2 倍。</small>
  </section>
}
