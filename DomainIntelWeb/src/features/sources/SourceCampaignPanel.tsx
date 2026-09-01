import {useCallback,useEffect,useState} from 'react'
import {api,type EntityCoverageMatrix,type SourceCampaignDetail,
  type SourceCampaignPage,type SourceCandidate,type SourceCandidateStatus,
  type CoverageRound,type CoverageReviewQueue,type CoverageCandidate} from '../../api'
import {Loading,type Toast} from '../shared'

const PAGE_SIZE=20
const visibleStates=['candidate','active','manual','reserve','rejected','paused','converged'] as const

export default function SourceCampaignPanel({industry,notify}:{industry:string;notify:(toast:Toast)=>void}){
  const [campaigns,setCampaigns]=useState<SourceCampaignPage|null>(null)
  const [selected,setSelected]=useState('')
  const [detail,setDetail]=useState<SourceCampaignDetail|null>(null)
  const [coverage,setCoverage]=useState<EntityCoverageMatrix|null>(null)
  const [coverageRounds,setCoverageRounds]=useState<CoverageRound[]>([])
  const [reviewQueue,setReviewQueue]=useState<CoverageReviewQueue>({entities:[],relations:[]})
  const [reasons,setReasons]=useState<Record<string,string>>({})
  const [loading,setLoading]=useState(true)

  const loadDetail=useCallback(async(id:string,offset=0)=>{
    const payload=await api<SourceCampaignDetail>(
      `/industries/${industry}/source-campaigns/${id}?limit=${PAGE_SIZE}&offset=${offset}`)
    setDetail(payload)
  },[industry])

  const load=useCallback(async()=>{
    setLoading(true)
    try{
      const [campaignPage,matrix,rounds,queue]=await Promise.all([
        api<SourceCampaignPage>(`/industries/${industry}/source-campaigns?limit=20&offset=0`),
        api<EntityCoverageMatrix>(`/industries/${industry}/coverage-matrix`),
        api<CoverageRound[]>(`/industries/${industry}/coverage-expansions`),
        api<CoverageReviewQueue>(`/industries/${industry}/coverage-review-queue`),
      ])
      setCampaigns(campaignPage);setCoverage(matrix);setCoverageRounds(rounds);setReviewQueue(queue)
      const campaignId=campaignPage.items[0]?.id||''
      setSelected(campaignId)
      if(campaignId) await loadDetail(campaignId)
      else setDetail(null)
    }catch(error){notify({kind:'error',text:String(error)})}
    finally{setLoading(false)}
  },[industry,loadDetail,notify])

  useEffect(()=>{void load()},[load])

  const createCampaign=async()=>{
    try{
      const created=await api<{id:string}>(`/industries/${industry}/source-campaigns`,{
        method:'POST',body:JSON.stringify({
          targets:['official','associations','blogs','platforms','self_media','news','journals','financials','finance'],
          budget:80,
        }),
      })
      notify({kind:'ok',text:'来源检索活动已建立；候选仍需复核后进入活跃池'})
      await load();setSelected(created.id);await loadDetail(created.id)
    }catch(error){notify({kind:'error',text:String(error)})}
  }

  const review=async(candidate:SourceCandidate,decision:Exclude<SourceCandidateStatus,'candidate'>)=>{
    const reason=(reasons[candidate.id]||'').trim()
    if(!reason){notify({kind:'error',text:'请先填写候选复核说明'});return}
    try{
      const updated=await api<SourceCandidate>(
        `/industries/${industry}/source-candidates/${candidate.id}/review`,{
          method:'POST',body:JSON.stringify({decision,actor:'local-user',reason}),
        })
      setDetail(current=>current?{...current,candidate_page:{...current.candidate_page,
        items:current.candidate_page.items.map(item=>item.id===updated.id?updated:item)}}:current)
      notify({kind:'ok',text:`${candidate.name} 已转为 ${decision}`})
    }catch(error){notify({kind:'error',text:String(error)})}
  }

  const executeCampaign=async()=>{
    if(!detail)return
    try{
      const job=await api<{run_id:string}>(`/industries/${industry}/source-campaigns/${detail.id}/execute`,{
        method:'POST',body:JSON.stringify({provider:'codex'}),
      })
      notify({kind:'ok',text:`来源活动已进入任务队列 · ${job.run_id.slice(0,12)}`})
      location.hash='/jobs'
    }catch(error){notify({kind:'error',text:String(error)})}
  }

  const expand=async()=>{
    try{
      const planned=await api<{round_id:string}>(`/industries/${industry}/coverage-expansions`,{
        method:'POST',body:JSON.stringify({}),
      })
      const job=await api<{run_id:string}>(`/industries/${industry}/coverage-expansions/${planned.round_id}/execute`,{
        method:'POST',body:JSON.stringify({provider:'codex'}),
      })
      notify({kind:'ok',text:`覆盖轮次已持久化并进入任务队列 · ${job.run_id.slice(0,12)}`})
      location.hash='/jobs'
    }catch(error){notify({kind:'error',text:String(error)})}
  }

  const reviewCoverage=async(candidate:CoverageCandidate,kind:'entity'|'relation',decision:'approve'|'manual_review'|'rejected')=>{
    const reason=(reasons[candidate.id]||'').trim()
    if(!reason){notify({kind:'error',text:'请先填写覆盖候选复核说明'});return}
    const path=kind==='entity'?'entity-candidates':'relation-candidates'
    try{
      await api(`/industries/${industry}/${path}/${candidate.id}/review`,{
        method:'POST',body:JSON.stringify({decision,actor:'local-user',reason}),
      })
      notify({kind:'ok',text:'覆盖候选复核已保存'});await load()
    }catch(error){notify({kind:'error',text:String(error)})}
  }

  return <section className="section-card source-campaign-panel">
    <div className="section-heading"><div><span className="eyebrow">DISCOVERY CONTROL</span>
      <h2>来源检索与覆盖</h2><p>候选池、查询账本与缺口解释分开呈现；达标不代表完整性已证明。</p></div>
      <button className="button primary" onClick={createCampaign}>新建来源检索活动</button></div>
    <div className="campaign-state-legend" aria-label="工作流状态">
      {visibleStates.map(state=><span className={`health health-${state}`} key={state}>{state}</span>)}
    </div>
    {loading&&!campaigns?<Loading label="正在读取检索活动与覆盖矩阵…"/>:<>
      <div className="campaign-tabs">{campaigns?.items.map(campaign=><button
        className={selected===campaign.id?'button secondary selected':'button secondary'}
        key={campaign.id} onClick={()=>{setSelected(campaign.id);void loadDetail(campaign.id)}}>
        {campaign.targets.join(' / ')} · <span>{campaign.status}</span>
      </button>)}</div>
      {detail&&<>
        {!['converged','failed'].includes(detail.status)&&<button className="button primary"
          onClick={()=>void executeCampaign()}>执行 / 恢复当前来源活动</button>}
        {detail.stopping_reason&&<p className="callout">停止原因：{detail.stopping_reason}</p>}
        {detail.round_history.map(round=><details key={round.id} className="campaign-log">
          <summary>Round {round.round_no} · {round.status}</summary>
          {round.log.map((entry,index)=><p key={`${entry.at}-${index}`}>{entry.at} · {entry.message}</p>)}
        </details>)}
        <div className="source-gap-grid">{detail.source_gaps.map(gap=><article key={gap.category}>
          <strong>{gap.category} · {gap.current} / {gap.target}</strong><span>缺口 {gap.gap}</span>
          <p>{gap.explanation}</p></article>)}</div>
        <div className="query-ledger"><h3>查询账本</h3>{detail.query_ledger.map(query=><article key={query.id}>
          <span>{query.language} · round {query.round_no} · {query.family}</span><strong>{query.query}</strong>
        </article>)}</div>
        <div className="candidate-list"><h3>候选复核</h3>{detail.candidate_page.items.map(candidate=><article key={candidate.id}>
          <div><strong>{candidate.name}</strong><span className={`health health-${candidate.status}`}>
            {candidate.status==='manual_review'?'manual':candidate.status}</span></div>
          <p>{candidate.selection_reason||candidate.status_reason||'尚无选择说明'}</p>
          {candidate.review?.reason&&<small>最近复核：{candidate.review.reason}</small>}
          {candidate.status!=='rejected'&&<><label><span>候选复核说明 · {candidate.name}</span>
            <textarea aria-label={`候选复核说明 · ${candidate.name}`} value={reasons[candidate.id]||''}
              onChange={event=>setReasons(current=>({...current,[candidate.id]:event.target.value}))}/></label>
            <div className="candidate-actions">
              {(['active','manual_review','reserve','rejected'] as const).map(state=><button
                className="button secondary" key={state} onClick={()=>void review(candidate,state)}
                aria-label={`转为 ${state==='manual_review'?'manual':state} · ${candidate.name}`}>
                转为 {state==='manual_review'?'manual':state} · {candidate.name}</button>)}
            </div></>}
        </article>)}</div>
        {detail.candidate_page.next_offset!==null&&<button className="button secondary"
          aria-label="下一页候选" onClick={()=>void loadDetail(detail.id,detail.candidate_page.next_offset!)}>
          下一页候选</button>}
      </>}
      <div className="coverage-matrix"><div className="section-heading"><div><h3>实体覆盖矩阵</h3>
        <p>{coverage?.completeness_proven?'完整性已证明':'完整性未证明；空白单元和低于阈值单元将保留为缺口。'}</p></div>
        <button className="button secondary" onClick={()=>void expand()}>生成覆盖扩展查询</button></div>
        {coverage?.cells.map(cell=><article key={cell.id}>
          <div><strong>{cell.chain_stage}</strong><span>{cell.entity_type}</span><span>{cell.region}</span></div>
          <strong>{cell.current} / {cell.target}</strong><span>缺口 {cell.gap}</span><p>{cell.explanation}</p>
          {cell.relation_evidence.map(edge=><small key={edge.edge_id}>{edge.relation} · {edge.evidence_count} 条证据</small>)}
        </article>)}
      </div>
      <div className="query-ledger"><h3>覆盖执行历史</h3>{coverageRounds.map(round=><article key={round.id}>
        <span>Round {round.round_no} · {round.status}</span><strong>{round.stopping_reason||'等待执行'}</strong>
        {round.log.slice(-3).map((entry,index)=><small key={`${entry.at}-${index}`}>{entry.message}</small>)}
      </article>)}</div>
      {(reviewQueue.entities.length>0||reviewQueue.relations.length>0)&&<div className="candidate-list">
        <h3>实体与关系复核队列</h3>{([['entity',reviewQueue.entities],['relation',reviewQueue.relations]] as const)
          .flatMap(([kind,items])=>items.map(candidate=><article key={candidate.id}>
            <div><strong>{String(candidate.payload.name||candidate.payload.relation||candidate.id)}</strong>
              <span className={`health health-${candidate.status}`}>{kind} · {candidate.status}</span></div>
            <label><span>覆盖候选复核说明</span><textarea value={reasons[candidate.id]||''}
              onChange={event=>setReasons(current=>({...current,[candidate.id]:event.target.value}))}/></label>
            <div className="candidate-actions">{(['approve','manual_review','rejected'] as const).map(decision=><button
              className="button secondary" key={decision}
              onClick={()=>void reviewCoverage(candidate,kind,decision)}>{decision}</button>)}</div>
          </article>))}</div>}
    </>}
  </section>
}
