import { Copy, ExternalLink, KeyRound } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { SetupPayload } from '../../api'

type CredentialStatus={secureStorage:boolean;configured:boolean;provider:string;model:string;apiBase:string;authType:string}
type DesktopBridge={credentialStatus:()=>Promise<CredentialStatus>;saveProvider:(value:{provider:string;model:string;apiKey:string;apiBase:string;authType:string})=>Promise<unknown>;clearProvider:()=>Promise<unknown>;relaunch:()=>Promise<boolean>}

export default function ConnectionStep({setup,selected,setSelected,onBack,onNext}:{
  setup:SetupPayload;selected:string;setSelected:(value:string)=>void;onBack:()=>void;onNext:()=>void
}) {
  const [error,setError]=useState(''); const [saving,setSaving]=useState(false); const [copied,setCopied]=useState(false)
  const bridge=(window as Window&{intdogDesktop?:DesktopBridge}).intdogDesktop
  const agent=useMemo(()=>setup.agents.find(item=>item.id===selected),[setup.agents,selected])
  const provider=useMemo(()=>setup.api_providers.find(item=>item.id===selected),[setup.api_providers,selected])
  const ready=selected==='taskpack'||Boolean(agent?.ready)||Boolean(provider?.ready)
  const config=setup.mcp_configs.find(item=>item.id===selected)||setup.mcp_configs.find(item=>item.id==='generic')
  const configText=config?(typeof config.value==='string'?config.value:JSON.stringify(config.value,null,2)):''
  const copy=async()=>{try{await navigator.clipboard.writeText(configText);setCopied(true)}catch{setError('无法访问剪贴板，请手动复制配置')}}
  const saveApi=async(event:React.FormEvent<HTMLFormElement>)=>{event.preventDefault();setSaving(true);setError('');const values=Object.fromEntries(new FormData(event.currentTarget)) as Record<string,string>;try{if(!bridge)throw new Error('浏览器开发模式不能保存密钥；请使用桌面应用或环境变量');await bridge.saveProvider({provider:selected,model:values.model,apiKey:values.apiKey,apiBase:values.apiBase,authType:values.authType});await bridge.relaunch()}catch(reason){setError(String(reason))}finally{setSaving(false)}}
  return <section className="setup-step" aria-labelledby="connection-title">
    <div><span className="eyebrow">STEP 2 / 4</span><h2 id="connection-title">选择研究连接</h2><p>无模型模式始终可用；CLI、API 和 MCP 只是增强执行能力。</p></div>
    <div className="agent-options">
      <label className={selected==='taskpack'?'selected':''}><input type="radio" name="provider" checked={selected==='taskpack'} onChange={()=>setSelected('taskpack')}/><span><b>无模型任务包 / MCP</b><small>公开来源、可审计任务包和通用 MCP 配置。</small></span><em className="ready">可用</em></label>
      {setup.agents.map(item=><label key={item.id} className={selected===item.id?'selected':''}><input type="radio" name="provider" checked={selected===item.id} onChange={()=>setSelected(item.id)}/><span><b>{item.name}</b><small>{item.note}</small><code>{item.executable||item.commands.join(' / ')}</code></span><em className={item.ready?'ready':'missing'}>{item.ready?'可连接':item.installed?'需登录':'未安装'}</em>{item.docs_url&&<a href={item.docs_url} target="_blank" rel="noreferrer" aria-label={`${item.name} 文档`}><ExternalLink/></a>}</label>)}
      {setup.api_providers.map(item=><label key={item.id} className={selected===item.id?'selected':''}><input type="radio" name="provider" checked={selected===item.id} onChange={()=>setSelected(item.id)}/><span><b>{item.name}</b><small>密钥只由桌面安全存储管理。</small></span><em className={item.ready?'ready':'missing'}>{item.ready?'已配置':'待配置'}</em></label>)}
    </div>
    {(selected==='taskpack'||agent?.execution!=='native')&&config&&<section className="mcp-config"><div><h3>{config.name} 连接配置</h3><p>MCP 保持只读，写回结果仍需人工复核。</p></div><pre>{configText}</pre><button className="button secondary" onClick={()=>void copy()}><Copy/>{copied?'已复制':'复制配置'}</button></section>}
    {provider&&!provider.ready&&<form className="api-key-form" onSubmit={saveApi}><label><span>模型</span><input name="model" required placeholder={provider.default_model||'输入模型 ID'}/></label><label><span>API Base（可选）</span><input name="apiBase" type="url" placeholder={provider.api_base}/></label>{provider.auth_configurable?<label><span>认证方式</span><select name="authType" defaultValue={provider.auth_type}><option value="bearer">Bearer Token</option><option value="api_key_header">API Key Header</option></select></label>:<input type="hidden" name="authType" value={provider.auth_type}/>}<label><span>API Key</span><input name="apiKey" type="password" required autoComplete="off"/></label><button className="button primary" disabled={saving}><KeyRound/>{saving?'正在安全保存…':'安全保存并重启'}</button></form>}
    {error&&<p className="field-error" role="alert">{error}</p>}
    <footer><button className="button secondary" onClick={onBack}>返回诊断</button><button className="button primary" disabled={!ready} onClick={onNext}>继续：选择行业</button></footer>
  </section>
}
