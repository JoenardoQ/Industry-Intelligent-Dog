import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Activity, BookOpen, Check, CircleDot, FileText, FlaskConical, FolderKanban, Globe2, LayoutDashboard, Menu, Newspaper, ServerCog, X } from 'lucide-react'
import { api, type Industry, type PageKey, type SetupPayload } from './api'
import { Empty, Loading, type Toast } from './features/shared'
import AgentConversation from './features/AgentConversation'
import PageHelp from './features/PageHelp'
import IndustryPicker from './features/IndustryPicker'

const OverviewPage = lazy(() => import('./features/OverviewPage'))
const DailyPage = lazy(() => import('./features/DailyPage'))
const KnowledgePage = lazy(() => import('./features/KnowledgePage'))
const ProductsPage = lazy(() => import('./features/ProductsPage'))
const SourcesPage = lazy(() => import('./features/SourcesPage'))
const ResearchPage = lazy(() => import('./features/ResearchPage'))
const JobsPage = lazy(() => import('./features/JobsPage'))
const SystemPage = lazy(() => import('./features/SystemPage'))
const SetupWizard = lazy(() => import('./features/SetupWizard'))

const navigation: { key: PageKey; label: string; note: string; icon: typeof Activity }[] = [
  { key: 'overview', label: '行业概览', note: '知识与产业链', icon: LayoutDashboard },
  { key: 'daily', label: '每日情报', note: '持续监测', icon: Newspaper },
  { key: 'knowledge', label: '实体与关系', note: '知识库详情', icon: BookOpen },
  { key: 'products', label: '研究产物', note: '周月季与报告', icon: FileText },
  { key: 'sources', label: '信息源', note: '来源与可信度', icon: Globe2 },
  { key: 'research', label: '研究助手', note: '问题、证据与实验', icon: FlaskConical },
  { key: 'jobs', label: '任务中心', note: '进度与日志', icon: FolderKanban },
  { key: 'system', label: '系统状态', note: '运行环境', icon: ServerCog },
]

function useHashPage(): [PageKey, (page: PageKey) => void] {
  const read = () => {
    const key = location.hash.replace('#/', '') as PageKey
    return navigation.some(item => item.key === key) ? key : 'overview'
  }
  const [page, setPage] = useState<PageKey>(read)
  useEffect(() => {
    const listener = () => setPage(read())
    addEventListener('hashchange', listener)
    return () => removeEventListener('hashchange', listener)
  }, [])
  return [page, key => { location.hash = `/${key}`; setPage(key) }]
}

function App() {
  const [industries, setIndustries] = useState<Industry[]>([])
  const [industry, setIndustry] = useState(localStorage.getItem('intdog.industry') || '')
  const [page, navigate] = useHashPage()
  const [mobileNav, setMobileNav] = useState(false)
  const [toast, setToast] = useState<Toast>(null)
  const [loading, setLoading] = useState(true)
  const [setup, setSetup] = useState<SetupPayload|null>(null)
  const [workflowProvider,setWorkflowProvider]=useState('taskpack')
  const [showSetup, setShowSetup] = useState(localStorage.getItem('intdog.onboarding.v1') !== 'complete')
  const notify = useCallback((value: Toast) => {
    setToast(value)
    if (value) window.setTimeout(() => setToast(null), 4500)
  }, [])
  const refreshIndustries = useCallback(async () => {
    try {
      const rows = await api<Industry[]>('/industries')
      setIndustries(rows)
      setIndustry(current => {
        const next = rows.some(row => row.folder === current) ? current : rows[0]?.folder || ''
        if (next) localStorage.setItem('intdog.industry', next)
        return next
      })
    } catch (error) { notify({ kind: 'error', text: String(error) }) }
    finally { setLoading(false) }
  }, [notify])
  useEffect(() => { void refreshIndustries() }, [refreshIndustries])
  const refreshSetup = useCallback(async()=>{ try { setSetup(await api<SetupPayload>('/setup')) } catch(error) { notify({kind:'error',text:String(error)}) } },[notify])
  useEffect(()=>{ void refreshSetup() },[refreshSetup])
  const refreshWorkflowSettings=useCallback(async()=>{if(!industry){setWorkflowProvider('taskpack');return}try{const value=await api<{provider:string}>(`/settings/effective?folder=${encodeURIComponent(industry)}&operation=*`);setWorkflowProvider(value.provider||'taskpack')}catch{setWorkflowProvider('taskpack')}},[industry])
  useEffect(()=>{void refreshWorkflowSettings();const listener=()=>void refreshWorkflowSettings();addEventListener('intdog:settings-changed',listener);return()=>removeEventListener('intdog:settings-changed',listener)},[refreshWorkflowSettings])
  const current = industries.find(row => row.folder === industry)
  const chooseIndustry = (folder: string) => { setIndustry(folder); localStorage.setItem('intdog.industry', folder) }
  const selectedProvider=workflowProvider
  const selectedAgent=localStorage.getItem('intdog.agent')||selectedProvider
  const agentState=setup?.agents.find(item=>item.id===selectedAgent)
  const apiState=setup?.api_providers.find(item=>item.id===selectedProvider)
  const connectionReady=selectedProvider==='taskpack'||Boolean(agentState?.ready)||Boolean(apiState?.ready)
  const connectionLabel=selectedProvider==='taskpack'?(agentState&&agentState.id!=='taskpack'?`${agentState.name} · 任务包交接`:'任务包模式可用'):(agentState?.ready?`${agentState.name} 已连接`:apiState?.ready?`${apiState.name} 已配置`:'智能体尚未就绪')
  const preferredAgent=setup?.agents.find(item=>item.id===selectedAgent)
  const preferredApi=setup?.api_providers.find(item=>item.id===selectedProvider)
  const chatTarget=(preferredAgent?.installed||preferredAgent?.ready)?preferredAgent:
    preferredApi?.ready?preferredApi:
    setup?.agents.find(item=>item.ready)||setup?.api_providers.find(item=>item.ready)
  const chatProvider=chatTarget?.id||''
  const chatProviderName=chatTarget?.name||''

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-mark">I</div><div><strong>IntDog</strong><span>INDUSTRY INTELLIGENCE</span></div></div>
      <nav aria-label="主要导航">{navigation.map(item => <button key={item.key} className={page === item.key ? 'nav-item active' : 'nav-item'} onClick={() => { navigate(item.key); setMobileNav(false) }}><item.icon size={20}/><span><strong>{item.label}</strong><small>{item.note}</small></span></button>)}</nav>
      <div className="sidebar-foot"><CircleDot size={15}/><span>Local-first · Evidence-aware</span></div>
    </aside>
    {mobileNav && <button className="scrim" aria-label="关闭导航" onClick={() => setMobileNav(false)}/>}
    <main>
      <header className="topbar"><button className="icon-button mobile-menu" onClick={() => setMobileNav(true)}><Menu/></button><IndustryPicker industries={industries} value={industry} onChange={chooseIndustry} disabled={loading}/><div className="top-status"><span className={`status-dot ${connectionReady?'':'warn'}`}/><span>{loading?'正在连接本地数据':`${current?`${current.name} 已加载 · `:''}${connectionLabel}`}</span><button onClick={()=>setShowSetup(true)}>连接设置</button></div></header>
      <div className="workspace">{loading ? <Loading label="正在加载行业数据库…"/> : !industry && page !== 'system' ? <Empty title="还没有行业" body="从左侧进入系统状态，新建第一个行业。"/> : <Suspense fallback={<Loading label="正在载入工作台模块…"/>}><PageRouter page={page} industry={industry} navigate={navigate} notify={notify} setup={setup}/></Suspense>}</div>
    </main>
    <AgentConversation industry={industry} provider={chatProvider} providerName={chatProviderName} notify={notify}/>
    <PageHelp page={page}/>
    {toast && <div className={`toast ${toast.kind}`} role="status">{toast.kind === 'ok' ? <Check/> : <X/>}{toast.text}</div>}
    {showSetup&&setup&&<Suspense fallback={null}><SetupWizard setup={setup} hasIndustry={Boolean(industries.length)} onRefresh={refreshSetup} onComplete={async(_provider,folder)=>{if(folder){localStorage.setItem('intdog.industry',folder);await refreshIndustries();navigate('overview')}setShowSetup(false)}}/></Suspense>}
  </div>
}

function PageRouter({ page, industry, navigate, notify, setup }: { page: PageKey; industry: string; navigate: (p: PageKey) => void; notify: (t: Toast) => void; setup: SetupPayload|null }) {
  if (page === 'overview') return <OverviewPage industry={industry} navigate={navigate}/>
  if (page === 'daily') return <DailyPage industry={industry} notify={notify}/>
  if (page === 'knowledge') return <KnowledgePage industry={industry}/>
  if (page === 'products') return <ProductsPage industry={industry} notify={notify}/>
  if (page === 'sources') return <SourcesPage industry={industry} notify={notify}/>
  if (page === 'research') return <ResearchPage industry={industry} notify={notify} setup={setup}/>
  if (page === 'jobs') return <JobsPage/>
  return <SystemPage industry={industry} notify={notify} setup={setup}/>
}

export default App
