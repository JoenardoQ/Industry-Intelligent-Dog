import { Cable, Copy, ExternalLink, KeyRound, PlugZap, RotateCcw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api, type SetupPayload } from '../../api'
import type { AgentDiagnosticState, AgentDiscoveryPage, AgentProbeState, ApiProviderProbeState } from '../../generated/openapi'

type CredentialStatus={secureStorage:boolean;configured:boolean;provider:string;model:string;apiBase:string;authType:string}
type DesktopBridge={
  credentialStatus:()=>Promise<CredentialStatus>
  saveProvider:(value:Record<string,string>)=>Promise<unknown>
  clearProvider:()=>Promise<unknown>
  selectAgentExecutable:()=>Promise<{canceled:boolean;path:string}>
  relaunch:()=>Promise<boolean>
}

export default function ConnectionStep({setup,selected,setSelected,onBack,onNext,onRefresh,onUseSelected,onRepair}:{
  setup:SetupPayload;selected:string;setSelected:(value:string)=>void;onBack:()=>void;onNext:()=>void;onRefresh:()=>Promise<void>;onUseSelected?:()=>void;onRepair?:()=>Promise<void>
}) {
  const [error,setError]=useState('');const [saving,setSaving]=useState(false);const [copied,setCopied]=useState(false)
  const [diagnostic,setDiagnostic]=useState<AgentDiagnosticState|null>(null)
  const [probe,setProbe]=useState<AgentProbeState|null>(null);const [agentBusy,setAgentBusy]=useState(false)
  const [apiProbe,setApiProbe]=useState<ApiProviderProbeState|null>(null)
  const bridge=(window as Window&{intdogDesktop?:DesktopBridge}).intdogDesktop
  const agent=useMemo(()=>setup.agents.find(item=>item.id===selected),[setup.agents,selected])
  const provider=useMemo(()=>setup.api_providers.find(item=>item.id===selected),[setup.api_providers,selected])
  const profile=(setup.agent_profiles||[]).find(item=>item.capability_id===selected)
  const profileId=profile?.id||(diagnostic?`binding-${diagnostic.id}`:'')
  const agentReady=diagnostic?.id===selected?diagnostic.ready:Boolean(agent?.ready)
  const ready=selected==='taskpack'||agentReady||Boolean(provider?.ready)
  const config=setup.mcp_configs.find(item=>item.id===selected)||setup.mcp_configs.find(item=>item.id==='generic')
  const configText=config?(typeof config.value==='string'?config.value:JSON.stringify(config.value,null,2)):''
  const copy=async()=>{try{await navigator.clipboard.writeText(configText);setCopied(true)}catch{setError('无法访问剪贴板，请手动复制配置')}}
  const chooseAgent=async()=>{
    setError('');setProbe(null);setAgentBusy(true)
    try{
      let selectedPath=''
      if(bridge?.selectAgentExecutable){const selectedFile=await bridge.selectAgentExecutable();if(selectedFile.canceled||!selectedFile.path)return;selectedPath=selectedFile.path}
      const discovery=await api<AgentDiscoveryPage>('/agent-bridge/discover',{method:'POST',body:JSON.stringify({selected_executables:selectedPath?[selectedPath]:[]})})
      const found=selectedPath
        ? discovery.items.find(item=>item.installed&&item.executable===selectedPath)
        : discovery.items.find(item=>item.id===selected&&item.installed&&(item.execution_level==='direct'||item.native_session_implemented))
          ||discovery.items.find(item=>item.installed&&(item.execution_level==='direct'||item.native_session_implemented))
      if(!found||found.id.startsWith('selected-'))throw new Error(selectedPath?'无法识别这个命令；请选择受支持 Agent 的 CLI 可执行文件':'没有在当前系统 PATH 中发现可连接的 Agent')
      if(found.execution_level!=='direct'&&!found.native_session_implemented)throw new Error(`${found.name} 已识别，但当前仅支持 MCP 或任务包交接`)
      const id=`binding-${found.id}`
      await api('/agent-bridge/profiles',{method:'POST',body:JSON.stringify({id,name:found.name,command:found.commands[0],args:[],executable_path:found.executable,capability_id:found.id})})
      const checked=await api<AgentDiagnosticState>(`/agent-bridge/profiles/${id}/diagnose`,{method:'POST'})
      if(!checked.version_verified){await api(`/agent-bridge/profiles/${id}`,{method:'DELETE'});throw new Error(checked.detail)}
      setSelected(found.id);setDiagnostic(checked);await onRefresh()
    }catch(reason){setError(String(reason))}finally{setAgentBusy(false)}
  }
  const testConnection=async()=>{
    if(!profileId)return;setAgentBusy(true);setError('');setProbe(null)
    try{setProbe(await api<AgentProbeState>(`/agent-bridge/profiles/${profileId}/probe`,{method:'POST'}))}
    catch(reason){setError(String(reason))}finally{setAgentBusy(false)}
  }
  const restoreAutomatic=async()=>{
    if(!profileId)return;setAgentBusy(true);setError('');setProbe(null)
    try{await api(`/agent-bridge/profiles/${profileId}`,{method:'DELETE'});setDiagnostic(null);await onRefresh()}
    catch(reason){setError(String(reason))}finally{setAgentBusy(false)}
  }
  const saveApi=async(event:React.FormEvent<HTMLFormElement>)=>{event.preventDefault();setSaving(true);setError('');const values=Object.fromEntries(new FormData(event.currentTarget)) as Record<string,string>;try{if(!bridge)throw new Error('浏览器开发模式不能保存密钥；请使用桌面应用或环境变量');await bridge.saveProvider({provider:selected,model:values.model,['apiKey']:values.apiKey,apiBase:values.apiBase,authType:values.authType});await bridge.relaunch()}catch(reason){setError(String(reason))}finally{setSaving(false)}}
  const testApi=async()=>{if(!provider)return;setSaving(true);setError('');setApiProbe(null);try{setApiProbe(await api<ApiProviderProbeState>(`/providers/${provider.id}/probe`,{method:'POST'}))}catch(reason){setError(String(reason))}finally{setSaving(false)}}
  const clearApi=async()=>{if(!bridge)return setError('浏览器开发模式不能清除桌面密钥');if(!confirm('清除当前 API 配置？之后需要重新填写 API Key。'))return;setSaving(true);setError('');try{await bridge.clearProvider();await bridge.relaunch()}catch(reason){setError(String(reason))}finally{setSaving(false)}}
  const repair=async()=>{if(!onRepair)return;setSaving(true);setError('');try{await onRepair()}catch(reason){setError(String(reason))}finally{setSaving(false)}}
  const status=diagnostic?.id===selected?diagnostic:null
  return <section className="setup-step" aria-labelledby="connection-title">
    <div><span className="eyebrow">STEP 2 / 4</span><h2 id="connection-title">选择研究连接</h2><p>IntDog 先自动检测同一系统中的 Agent。没有找到时，选择它的 CLI 命令文件即可；无需填写命令或跨系统路径。</p></div>
    <div className="agent-options">
      <label className={selected==='taskpack'?'selected':''}><input type="radio" name="provider" checked={selected==='taskpack'} onChange={()=>setSelected('taskpack')}/><span><b>无模型任务包 / MCP</b><small>公开来源、可审计任务包和通用 MCP 配置。</small></span><em className="ready">可用</em></label>
      {setup.agents.map(item=>{const current=status?.id===item.id?status:item;const conversational=item.native_session_implemented;const label=current.ready?(item.execution==='native'?'可以直接使用':conversational?'可对话 · 任务交接':'可交接'):current.installed?(current.authenticated===false?'需要登录':'需要检测'):'未安装';return <label key={item.id} className={selected===item.id?'selected':''}><input type="radio" name="provider" checked={selected===item.id} onChange={()=>setSelected(item.id)}/><span><b>{item.name}</b><small>{conversational?`${item.session_protocol} · ${item.session_level} 会话；任务执行按 ${(item.fallbacks||['taskpack']).join(' / ')} 回退。`:item.note}</small><code>{current.executable||item.commands.join(' / ')}</code>{status?.id===item.id&&<small>{status.version} · {status.detail}</small>}</span><em className={current.ready?'ready':'missing'}>{label}</em>{item.docs_url&&<a href={item.docs_url} target="_blank" rel="noreferrer" aria-label={`${item.name} 文档`}><ExternalLink/></a>}</label>})}
      {setup.api_providers.map(item=><label key={item.id} className={selected===item.id?'selected':''}><input type="radio" name="provider" checked={selected===item.id} onChange={()=>setSelected(item.id)}/><span><b>{item.name}</b><small>密钥只由桌面安全存储管理。</small></span><em className={item.ready?'ready':'missing'}>{item.ready?'已配置':'待配置'}</em></label>)}
    </div>
    <section className="agent-connection-tools" aria-label="本机 Agent 连接工具"><div><Cable/><span><strong>本机 Agent 没被识别？</strong><small>{bridge?'请选择 Codex、Claude、Gemini、Qwen、Kimi、CodeBuddy 等受支持 CLI 的命令文件。IntDog 会验证身份、版本和可用接口。':'源码模式会重新扫描当前系统 PATH，并验证 Agent 的身份、版本和可用接口。'}</small></span></div><div className="section-actions"><button className="button secondary" onClick={()=>void chooseAgent()} disabled={agentBusy}>{agentBusy?'正在检测…':bridge?'选择已安装的 Agent':'自动检测本机 Agent'}</button>{profileId&&agent?.execution==='native'&&<button className="button secondary" onClick={()=>void testConnection()} disabled={agentBusy||!agentReady}><PlugZap/>测试真实连接</button>}{profileId&&<button className="button tertiary" onClick={()=>void restoreAutomatic()} disabled={agentBusy}><RotateCcw/>恢复自动检测</button>}</div>{probe&&<p className={probe.ready?'connection-result ready':'connection-result missing'}>{probe.detail} · {probe.latency_ms} ms</p>}</section>
    {(selected==='taskpack'||Boolean(agent&&agent.execution!=='native'))&&config&&<section className="mcp-config"><div><h3>{config.name} 连接配置</h3><p>MCP 保持只读，写回结果仍需人工复核。</p></div><pre>{configText}</pre><button className="button secondary" onClick={()=>void copy()}><Copy/>{copied?'已复制':'复制配置'}</button></section>}
    {provider&&<form className="api-key-form" onSubmit={saveApi}><div><h3>{provider.configured?'编辑 API 配置':'配置 API'}</h3><p>{provider.configured?'留空 API Key 会保留桌面安全存储中的现有密钥。':'填写供应商提供的精确模型 ID；Provider 名称不是模型 ID。'}</p></div><label><span>模型</span><input name="model" required defaultValue={provider.model||provider.default_model} placeholder="输入精确模型 ID"/></label><label><span>API Base（可选）</span><input name="apiBase" type="url" defaultValue={provider.api_base}/></label>{provider.auth_configurable?<label><span>认证方式</span><select name="authType" defaultValue={provider.auth_type}><option value="bearer">Bearer Token</option><option value="api_key_header">API Key Header</option></select></label>:<input type="hidden" name="authType" value={provider.auth_type}/>}<label><span>API Key</span><input name="apiKey" type="password" required={!provider.configured} autoComplete="off" placeholder={provider.configured?'留空以保留现有密钥':''}/></label><div className="section-actions"><button className="button primary" disabled={saving}><KeyRound/>{saving?'处理中…':'保存配置并重启'}</button>{provider.configured&&<button type="button" className="button secondary" disabled={saving} onClick={()=>void testApi()}><PlugZap/>测试 API 连接</button>}{provider.configured&&<button type="button" className="button tertiary" disabled={saving} onClick={()=>void clearApi()}>清除 API 配置</button>}</div>{apiProbe&&<p className={apiProbe.ready?'connection-result ready':'connection-result missing'}>{apiProbe.detail} · {apiProbe.latency_ms} ms{apiProbe.request_id?` · ${apiProbe.request_id}`:''}</p>}</form>}
    {error&&<p className="field-error" role="alert">{error}</p>}
    <footer><button className="button secondary" onClick={onBack}>{onRepair?'返回原任务':'返回诊断'}</button>{!onRepair&&onUseSelected&&<button className="button secondary" disabled={!ready} onClick={onUseSelected}>设为全局默认并返回工作台</button>}{onRepair?<button className="button primary" disabled={!ready||saving} onClick={()=>void repair()}>{saving?'正在恢复任务…':'保存连接并重试原任务'}</button>:<button className="button primary" disabled={!ready} onClick={onNext}>继续：选择行业</button>}</footer>
  </section>
}
