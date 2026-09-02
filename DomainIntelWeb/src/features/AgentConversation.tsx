import { FormEvent, useEffect, useRef, useState } from 'react'
import { Bot, ChevronLeft, ChevronRight, LoaderCircle, Send, X } from 'lucide-react'
import { api, type ActionProposal, type Conversation, type ConfirmedProposal } from '../api'
import type { Toast } from './shared'

type Props = {
  industry:string
  provider:string
  providerName:string
  notify:(value:Toast)=>void
}

const actionNames:Record<string,string>={daily:'每日情报',weekly:'周报',monthly:'月报',quarterly:'季报',report:'行业报告',deep_report:'深度研究',impact:'影响分析',lab:'Intelligence Lab',bootstrap:'初始化研究',coverage:'覆盖搜索',history:'历史回填'}

export default function AgentConversation({industry,provider,providerName,notify}:Props){
  const [collapsed,setCollapsed]=useState(localStorage.getItem('intdog.chat.collapsed')==='true')
  const [state,setState]=useState<Conversation|null>(null)
  const [message,setMessage]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const endRef=useRef<HTMLDivElement>(null)

  useEffect(()=>{
    setState(null);setError('')
    if(!industry||!provider)return
    let active=true
    api<Conversation>(`/industries/${encodeURIComponent(industry)}/conversation?provider=${encodeURIComponent(provider)}`)
      .then(value=>{if(active)setState(value)})
      .catch(reason=>{if(active)setError(String(reason))})
    return()=>{active=false}
  },[industry,provider])
  useEffect(()=>{
    if(typeof endRef.current?.scrollIntoView==='function')endRef.current.scrollIntoView({block:'nearest'})
  },[state?.messages.length,state?.proposals.length])

  const toggle=()=>setCollapsed(value=>{localStorage.setItem('intdog.chat.collapsed',String(!value));return !value})
  const send=async(event:FormEvent)=>{
    event.preventDefault()
    const value=message.trim();if(!value||busy)return
    setBusy(true);setError('');setMessage('')
    try{setState(await api<Conversation>(`/industries/${encodeURIComponent(industry)}/conversation/turn`,{method:'POST',body:JSON.stringify({provider,message:value})}))}
    catch(reason){setError(String(reason));setMessage(value)}finally{setBusy(false)}
  }
  const decide=async(proposal:ActionProposal,decision:'confirm'|'reject')=>{
    if(busy)return
    setBusy(true);setError('')
    try{
      const path=`/industries/${encodeURIComponent(industry)}/conversation/proposals/${encodeURIComponent(proposal.id)}/${decision}` as const
      const result=await api<ConfirmedProposal|ActionProposal>(path,{method:'POST',body:JSON.stringify({revision:proposal.revision})})
      setState(current=>current?{...current,proposals:current.proposals.map(item=>item.id===proposal.id?(decision==='confirm'?(result as ConfirmedProposal).proposal:result as ActionProposal):item)}:current)
      notify({kind:'ok',text:decision==='confirm'?'任务已进入任务中心':'已拒绝执行建议'})
    }catch(reason){setError(String(reason))}finally{setBusy(false)}
  }

  if(collapsed)return <button className="agent-chat-tab" onClick={toggle} aria-label="打开 Agent 对话"><Bot/><span>Agent</span><ChevronLeft/></button>
  const capability=state?.capability||{}
  const protocol=String(state?.connection||capability.session_protocol||'等待连接')
  return <aside className="agent-chat" aria-label="行业 Agent 对话">
    <header><div><span className="agent-avatar"><Bot/></span><div><strong>研究 Agent</strong><small>{providerName||provider} · {protocol}</small></div></div><button className="icon-button" onClick={toggle} aria-label="收起 Agent 对话"><ChevronRight/></button></header>
    <div className="agent-chat-context"><span>{industry||'未选择行业'}</span><p>对话只保存在本机，并随行业切换。执行建议必须逐项确认。</p></div>
    <div className="agent-chat-stream">
      {!provider&&<div className="agent-chat-empty"><Bot/><strong>尚未选择 Agent</strong><p>请先在连接设置中选择可用的 Agent 或 API。</p></div>}
      {provider&&!state&&!error&&<div className="agent-chat-loading"><LoaderCircle/> 正在读取本地对话…</div>}
      {state?.messages.map(item=><article key={item.id} className={`chat-message ${item.role}`}><span>{item.role==='user'?'你':'Agent'}</span><p>{item.content}</p></article>)}
      {state?.proposals.filter(item=>item.status==='pending').map(item=><article className="action-proposal" key={item.id}><header><span>待确认操作</span><strong>{actionNames[item.action]||item.action}</strong></header><p>{String(item.payload.summary||'Agent 建议执行此任务')}</p><dl><div><dt>行业</dt><dd>{industry}</dd></div><div><dt>Provider</dt><dd>{String(item.payload.provider||provider)}</dd></div><div><dt>执行方式</dt><dd>{String(item.payload.execution_mode||'direct')}</dd></div></dl><footer><button className="button ghost" onClick={()=>void decide(item,'reject')} disabled={busy}><X/>拒绝</button><button className="button primary" onClick={()=>void decide(item,'confirm')} disabled={busy}>确认并执行</button></footer></article>)}
      {error&&<p className="agent-chat-error" role="alert">{error}</p>}
      <div ref={endRef}/>
    </div>
    <form className="agent-chat-composer" onSubmit={send}><label htmlFor="agent-message">给 Agent 发消息</label><textarea id="agent-message" value={message} onChange={event=>setMessage(event.target.value)} placeholder="提问、分析，或让 Agent 提议一项研究任务…" rows={3} disabled={!provider||busy}/><button className="button primary" disabled={!message.trim()||!provider||busy}>{busy?<LoaderCircle className="spin"/>:<Send/>}发送</button></form>
  </aside>
}
