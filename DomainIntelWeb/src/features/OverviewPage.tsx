import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, BadgeCheck, Bot, Building2, FileCheck2, FileText, Globe2, Search, X } from 'lucide-react'
import { type KnowledgeEntityDetail, type KnowledgeEntityPage, type OverviewPayload, type PageKey } from '../api'
import { ChainGraph, Empty, Header, Loading } from './shared'
import { useLatestRequest } from './useLatestRequest'

export default function OverviewPage({ industry, navigate }: { industry: string; navigate: (p: PageKey) => void }) {
  const {data,error,load:loadOverview}=useLatestRequest<OverviewPayload>()
  const {data:entityPage,error:listError,loading:listLoading,load:loadPage}=useLatestRequest<KnowledgeEntityPage>()
  const {data:activeEntity,error:detailError,loading:detailLoading,load:loadDetail,clear:closeDetail}=useLatestRequest<KnowledgeEntityDetail>()
  const [entityQuery,setEntityQuery]=useState('');const [entityKind,setEntityKind]=useState('');const [entityChain,setEntityChain]=useState('')
  useEffect(()=>{void loadOverview(`/industries/${industry}/overview`)},[industry,loadOverview])
  const loadEntities=useCallback((offset=0)=>{
    const params=new URLSearchParams({limit:'50',offset:String(offset),...(entityQuery&&{query:entityQuery}),...(entityKind&&{kind:entityKind}),...(entityChain&&{chain:entityChain})})
    return loadPage(`/industries/${industry}/knowledge/entities?${params}`)
  },[industry,entityQuery,entityKind,entityChain,loadPage])
  useEffect(()=>{void loadEntities();closeDetail()},[loadEntities,closeDetail])
  const openEntity=(id:string)=>loadDetail(`/industries/${industry}/knowledge/entities/${id}`)
  if (error) return <Empty title="行业概览不可用" body={error}/>
  if (!data) return <Loading label="正在组织行业知识结构…"/>
  const cards = [
    ['信息源', data.stats.sources, () => navigate('sources'), Globe2], ['文档', data.stats.documents, () => navigate('daily'), FileText],
    ['实体', data.stats.entities, () => document.getElementById('overview-entities')?.scrollIntoView({behavior:'smooth'}), Building2], ['断言', data.stats.claims, () => navigate('research'), FileCheck2],
    ['正式事实', data.stats.verified_claims, () => navigate('research'), BadgeCheck], ['关系', data.stats.relations, () => document.getElementById('overview-chain')?.scrollIntoView({behavior:'smooth'}), ArrowRight],
  ] as const
  return <>
    <Header eyebrow="INDUSTRY OVERVIEW" title={data.industry.name || industry}
      body={data.industry.description || '从来源、文档、实体和证据出发，构建可审计的行业认知。'}
      actions={<button className="button primary" onClick={() => navigate('research')}><Bot size={18}/>开始研究</button>}/>
    {listError&&<p role="alert">{listError} <button onClick={()=>void loadEntities()}>重试</button></p>}{detailError&&<p role="alert">{detailError}</p>}{detailLoading&&<p role="status">正在读取实体详情…</p>}
    <div className="metric-grid">{cards.map(([label, value, activate, Icon]) => <button className="metric-card" aria-label={`${label} ${Number(value||0)}`} key={label} onClick={activate}>
      <span className="metric-icon"><Icon/></span><strong>{Number(value || 0).toLocaleString()}</strong><span>{label}</span><ArrowRight size={18}/>
    </button>)}</div>
    <section className="section-card chain-section" id="overview-chain" tabIndex={-1}><div className="section-title"><div><span className="eyebrow">VALUE CHAIN</span><h2>产业链知识结构与关系</h2></div><span className="subtle">{data.chain.length} 个环节 · {data.chain_edges.length} 条有证据状态的有向边 · {data.stats.relations} 条实体关系</span></div><ChainGraph nodes={data.chain} edges={data.chain_edges}/></section>
    <div className="two-columns">
      <section className="section-card knowledge-explorer" id="overview-entities" tabIndex={-1}><div className="section-title"><div><h2>完整实体与研究组</h2><span className="subtle">可检索 {entityPage?.total??data.stats.entities} 个当前实体，不设 Top 10 边界</span></div></div><div className="entity-filters"><label className="search-field"><span className="sr-only">搜索实体、英文名或别名</span><Search/><input value={entityQuery} onChange={e=>setEntityQuery(e.target.value)} placeholder="搜索企业、研究组、人物或技术"/></label><label><span>类型</span><select value={entityKind} onChange={e=>setEntityKind(e.target.value)}><option value="">全部类型</option>{['company','research_group','regulator','association','person','technology','product','facility'].map(value=><option key={value}>{value}</option>)}</select></label><label><span>产业链</span><select value={entityChain} onChange={e=>setEntityChain(e.target.value)}><option value="">全部环节</option>{data.chain.map(node=><option key={node.id||node.name} value={node.name}>{node.name}</option>)}</select></label></div><div className="entity-list" aria-busy={listLoading}>{listLoading&&<Loading label="正在筛选实体…"/>}{(entityPage?.items||[]).map(entity => <button className="entity-row" key={`${entity.id}-${entity.chain}`} onClick={()=>void openEntity(entity.id)}><span className="avatar">{String(entity.name || '?').slice(0, 1)}</span><div><strong>{entity.name}</strong><small>{entity.kind} · {entity.chain || entity.role || '待分类'} · {entity.country || '地区未知'}</small></div><span className="confidence">{entity.confidence ? `${Math.round(entity.confidence * 100)}%` : '待验证'}</span></button>)}</div><div className="pager"><button className="button secondary" disabled={!entityPage?.offset} onClick={()=>loadEntities(Math.max(0,(entityPage?.offset||0)-50))}>上一页</button><span>{entityPage?`${entityPage.offset+1}–${Math.min(entityPage.offset+entityPage.items.length,entityPage.total)} / ${entityPage.total}`:'加载中'}</span><button className="button secondary" disabled={entityPage?.next_offset==null} onClick={()=>loadEntities(entityPage?.next_offset||0)}>下一页</button></div></section>
      <section className="section-card"><div className="section-title"><h2>来源结构</h2><button className="text-button" onClick={() => navigate('sources')}>管理来源 <ArrowRight size={16}/></button></div><div className="category-bars">{Object.entries(data.source_categories).sort((a, b) => b[1] - a[1]).map(([name, count]) => <div key={name}><span>{name.replace('_', ' ')}</span><div><i style={{ width: `${Math.min(100, count * 12)}%` }}/></div><strong>{count}</strong></div>)}</div></section>
    </div>
    {activeEntity&&<div className="entity-drawer" role="dialog" aria-modal="true" aria-labelledby="entity-detail-title"><button className="drawer-backdrop" aria-label="关闭实体详情" onClick={()=>closeDetail()}/><aside><button className="icon-button drawer-close" aria-label="关闭实体详情" autoFocus onClick={()=>closeDetail()}><X/></button><span className="eyebrow">{activeEntity.kind} · {activeEntity.status}</span><h2 id="entity-detail-title">{activeEntity.canonical_name}</h2><p>{activeEntity.name_en||''} · {activeEntity.country||'地区未知'} · {activeEntity.chain||'产业链待分类'}</p><div className="detail-stats"><span>{activeEntity.roles.length} 个角色</span><span>{activeEntity.relations.length} 条关系</span><span>{activeEntity.evidence_count} 条证据</span></div><h3>上下游关系</h3>{!activeEntity.relations.length?<p className="subtle">尚无结构化关系证据。</p>:activeEntity.relations.map(row=><div className="relation-row" key={row.id}><strong>{row.src_name}</strong><span>{row.predicate} →</span><strong>{row.dst_name}</strong></div>)}<h3>主张与证据</h3>{!activeEntity.claims.length?<p className="subtle">尚无关联主张。</p>:activeEntity.claims.map(claim=><article className="claim-card" key={claim.id}><strong>{claim.predicate}</strong><span className="tag">{claim.status}</span><pre>{JSON.stringify(claim.object,null,2)}</pre>{claim.evidence.map((ev,index)=>ev.document_url?<a key={index} href={ev.document_url} target="_blank" rel="noreferrer">{ev.relation} · {ev.document_title||ev.document_url}</a>:null)}</article>)}</aside></div>}
  </>
}
