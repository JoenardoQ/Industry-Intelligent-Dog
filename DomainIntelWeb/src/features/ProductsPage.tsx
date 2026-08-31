import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, FileText } from 'lucide-react'
import { api, artifactUrl, type ProductItem, type ProductsPayload } from '../api'
import { ChainGraph, Empty, Generate, Header, Loading, Markdown, type Toast } from './shared'

export default function ProductsPage({ industry, notify }: { industry: string; notify: (t: Toast) => void }) {
  const [data, setData] = useState<ProductsPayload | null>(null); const [active, setActive] = useState<ProductItem | null>(null); const [error, setError] = useState('')
  const load = useCallback(() => api<ProductsPayload>(`/industries/${industry}/products`).then(value => { setData(value); const all = [...Object.values(value.periodic).flat(), ...value.reports, ...value.deep_reports, ...value.impacts]; setActive(current => current || all[0] || null) }).catch(e => { setError(String(e)); notify({kind:'error',text:String(e)}) }), [industry, notify])
  useEffect(() => { setData(null); setActive(null); setError(''); void load() }, [load])
  if (error) return <Empty title="研究产物不可用" body={error}/>
  const groups = data ? [{label:'每周', rows:data.periodic.weekly},{label:'每月',rows:data.periodic.monthly},{label:'每季',rows:data.periodic.quarterly},{label:'行业报告',rows:data.reports},{label:'深度研究',rows:data.deep_reports},{label:'影响分析',rows:data.impacts}] : []
  const path = active?.report_file || active?.path || active?._file; const graphNodes = active?.visualization?.directed_graph?.nodes || []
  return <><Header eyebrow="RESEARCH PRODUCTS" title="研究产物" body="直接生成周、月、季产物；报告、图表、证据和限制在同一阅读空间呈现。"/>
    <div className="period-actions"><Generate industry={industry} action="weekly" label="生成周报" notify={notify}/><Generate industry={industry} action="monthly" label="生成月报" notify={notify}/><Generate industry={industry} action="quarterly" label="生成季报" notify={notify}/></div>
    <div className="reader-layout"><section className="section-card product-index">{!data ? <Loading label="正在载入研究产物…"/> : groups.map(group => <div key={group.label}><h3>{group.label}<span>{group.rows.length}</span></h3>{group.rows.map((row: ProductItem, index: number) => <button className={active === row ? 'active' : ''} key={row.id || row._key || row.name || index} onClick={() => setActive(row)}><FileText/><span><strong>{row.title || row.name || row._key || '未命名产物'}</strong><small>{row.generated_at || row.window_end || row.status || '本地产物'}</small></span></button>)}</div>)}</section>
      <section className="section-card markdown-reader">{!active ? <Empty title="暂无研究产物" body="使用上方按钮生成第一份产物。" compact/> : <><div className="reader-meta"><div><span className="eyebrow">DOCUMENT</span><h2>{active.title || active.name || active._key}</h2></div>{path && <a className="button secondary" href={artifactUrl(path)} target="_blank" rel="noreferrer">打开原文 <ExternalLink/></a>}</div>{graphNodes.length > 0 && <div className="embedded-chain"><span className="eyebrow">UPSTREAM → DOWNSTREAM</span><ChainGraph nodes={graphNodes.map(node => ({...node, name:node.label || node.name}))}/></div>}<Markdown path={path} fallback={active.summary || JSON.stringify(active, null, 2)}/></>}</section></div>
  </>
}
