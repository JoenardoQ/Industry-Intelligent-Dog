import { Bot, Braces, Cable, Database, RefreshCw } from 'lucide-react'
import type { SetupPayload } from '../../api'

export default function DiagnosticsStep({setup,onRefresh,onNext,onReturn}:{
  setup:SetupPayload; onRefresh:()=>Promise<void>; onNext:()=>void; onReturn?:()=>void
}) {
  const cli=setup.agents.filter(item=>item.execution==='native')
  const api=setup.api_providers
  const checks=[
    {name:'无模型模式',icon:Database,ok:setup.runtime_ready&&setup.taskpack_ready,
      detail:setup.taskpack_ready?'公开来源与任务包可用':'本地任务包未就绪'},
    {name:'CLI',icon:Bot,ok:cli.some(item=>item.ready),
      detail:cli.length?cli.map(item=>`${item.name}：${item.ready?'可用':item.detail||'未就绪'}`).join('；'):'未检测到 CLI'},
    {name:'API',icon:Braces,ok:api.some(item=>item.ready),
      detail:api.length?`${api.filter(item=>item.ready).length} / ${api.length} 个 Provider 已配置`:'未配置 API Provider'},
    {name:'MCP',icon:Cable,ok:setup.mcp_configs.length>0,
      detail:setup.mcp_configs.length?`${setup.mcp_configs.length} 份本地连接配置可复制`:'MCP 配置生成失败'},
  ]
  return <section className="setup-step" aria-labelledby="diagnostics-title">
    <div className="setup-title-row"><div><span className="eyebrow">STEP 1 / 4</span><h2 id="diagnostics-title">环境诊断</h2><p>先确认本地运行、模型连接和任务交接能力；未配置模型不阻塞首次研究。</p></div><button className="button secondary" onClick={()=>void onRefresh()}><RefreshCw/>重新检测</button></div>
    <div className="diagnostic-grid">{checks.map(({name,icon:Icon,ok,detail})=><article key={name} className={ok?'diagnostic-ok':'diagnostic-warn'}><Icon/><div><strong>{name}</strong><p>{detail}</p></div><span>{ok?'已就绪':'需处理'}</span></article>)}</div>
    <p className="setup-privacy">{setup.privacy_note}</p>
    <footer><button className="button primary" onClick={onNext}>继续：选择连接</button>{onReturn&&<button className="button secondary" onClick={onReturn}>进入工作台</button>}</footer>
  </section>
}
