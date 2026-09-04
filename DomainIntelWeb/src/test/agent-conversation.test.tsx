import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => vi.fn())
vi.mock('../api', async importOriginal => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, api: apiMock }
})

import AgentConversation from '../features/AgentConversation'

const state = (industry:string) => ({
  conversation:{id:`conv-${industry}`,industry_id:`ind-${industry}`,provider:'codex',external_session_id:'',created_at:'now',updated_at:'now',archived_at:null},
  messages:[{id:'m1',conversation_id:`conv-${industry}`,role:'assistant',content:`${industry} welcome`,metadata:{connection:'codex_app_server'},created_at:'now'}],
  proposals:[], capability:{id:'codex',name:'Codex CLI',session_protocol:'codex_app_server',session_level:'full',protocol_maturity:'stable',native_session_implemented:true,fallbacks:['cli']},
})

beforeEach(()=>apiMock.mockReset())
afterEach(()=>{cleanup();localStorage.clear()})

it('switches local transcripts with the industry and confirms proposals explicitly',async()=>{
  apiMock.mockImplementation((path:string,init?:RequestInit)=>{
    const value=String(path||'')
    if(value.includes('/conversation?'))return Promise.resolve(state(value.includes('/AI/')?'AI':'chips'))
    if(value.endsWith('/conversation/turn'))return Promise.resolve({...state('AI'),proposals:[{
      id:'prop-1',conversation_id:'conv-AI',revision:1,action:'daily',payload:{summary:'抓取今日情报',provider:'codex'},status:'pending',expires_at:'later',confirmed_at:null,task_run_id:null,created_at:'now',updated_at:'now',
    }]})
    if(value.endsWith('/proposals/prop-1/confirm')&&init?.method==='POST')return Promise.resolve({proposal:{},job:{run_id:'task-1',status:'queued'}})
    return Promise.resolve({})
  })
  const {rerender}=render(<AgentConversation industry="AI" provider="codex" providerName="Codex CLI" notify={vi.fn()}/>)
  expect(await screen.findByText('AI welcome')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('给 Agent 发消息'),{target:{value:'生成今日情报'}})
  fireEvent.click(screen.getByRole('button',{name:'发送'}))
  expect(await screen.findByText('抓取今日情报')).toBeInTheDocument()
  expect(apiMock.mock.calls.filter(call=>String(call[0]).includes('/confirm'))).toHaveLength(0)
  fireEvent.click(screen.getByRole('button',{name:'确认并执行'}))
  await waitFor(()=>expect(apiMock).toHaveBeenCalledWith(
    '/industries/AI/conversation/proposals/prop-1/confirm',expect.objectContaining({method:'POST'})))
  rerender(<AgentConversation industry="chips" provider="codex" providerName="Codex CLI" notify={vi.fn()}/>)
  expect(await screen.findByText('chips welcome')).toBeInTheDocument()
  expect(screen.queryByText('AI welcome')).not.toBeInTheDocument()
})

it('shows when the native protocol downgraded to the same Agent CLI',async()=>{
  apiMock.mockResolvedValue({
    ...state('AI'),connection:'cli_fallback',
    connection_warning:'Codex App Server 无法使用，已改用同一 Codex CLI。',
  })

  render(<AgentConversation industry="AI" provider="codex" providerName="Codex CLI" notify={vi.fn()}/>)

  expect(await screen.findByText(/本机 CLI 回退/)).toBeInTheDocument()
  expect(screen.getByText('Codex App Server 无法使用，已改用同一 Codex CLI。')).toBeInTheDocument()
})
