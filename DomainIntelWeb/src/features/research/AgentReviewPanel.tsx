import { useState } from 'react'
import { ExternalLink, MessageSquareText, RotateCw, ShieldCheck, XCircle } from 'lucide-react'

import { api } from '../../api'
import type {
  AgentGateCheck,
  AgentReviewRequest,
  AgentResultPage,
  AgentResultState,
  AgentVerificationChecks,
  AgentVerificationState,
} from '../../generated/openapi'

type AgentReviewPanelProps = Pick<AgentResultPage, 'items' | 'total' | 'next_offset'> & {
  industry: string
  loading: boolean
  loadError: string
  onLoadMore: () => void | Promise<void>
  onResultChanged: (result: AgentResultState) => void
}

const gateLabels: Record<keyof AgentVerificationChecks, string> = {
  atomization: '原子化',
  reachability: '链接可达性',
  publisher_identity: '发布者身份',
  publication_time: '发布时间',
  entity_alignment: '实体对齐',
  locator_integrity: '证据定位',
  generation_provenance: '生成来源',
  verifier_independence: '核验独立性',
  semantic_support: '语义支持',
  numeric_consistency: '数值一致性',
  type_classification: '声明类型',
  type_policy: '类型政策',
  resource_budget: '资源边界',
  corroboration: '独立佐证',
  conflict: '事实冲突',
  fact_projection: '事实入库',
}

const gateKeys = Object.keys(gateLabels) as Array<keyof AgentVerificationChecks>

const statusLabels: Record<AgentResultState['status'], string> = {
  draft_review_required: '待人工复核',
  rejected: '已驳回',
  opinion: '观点',
  submitted_for_verification: '待自动核验',
  candidate: '候选事实',
  disputed: '存在争议',
  accepted: '已进入事实库',
}

function safeExternalUrl(value: string): string | null {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

function sourceName(value: string): string {
  const safe = safeExternalUrl(value)
  if (!safe) return value
  return new URL(safe).hostname.replace(/^www\./, '')
}

function formatLocator(value: unknown): string {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return '定位器无法显示'
  }
}

function formatImportTime(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(parsed)
}

function GateList({ checks }: { checks: AgentVerificationChecks }) {
  return <div className="verification-gates" aria-label="自动核验门槛">
    {gateKeys.map(key => {
      const check: AgentGateCheck = checks[key]
      return <article className={`verification-gate gate-${check.status}`} key={key}>
        <header>
          <strong>{gateLabels[key]}</strong>
          <span>{check.status}</span>
        </header>
        <p>{check.reason}</p>
        {!!check.failures?.length && <ul className="gate-failures" aria-label="门槛失败明细">
          {check.failures.map((failure, index) => <li
            key={`${failure.evidence_id}-${failure.failure_code || 'failure'}-${index}`}>
            <code>{failure.evidence_id}</code>
            <strong>{failure.reason}</strong>
            {failure.status_code !== null && failure.status_code !== undefined &&
              <span>HTTP {failure.status_code}</span>}
          </li>)}
        </ul>}
        {!!check.locators.length && <ul className="evidence-locators">
          {check.locators.map((locator, index) => {
            const safe = safeExternalUrl(locator.url)
            return <li key={`${locator.evidence_id}-${index}`}>
              <div>
                {safe
                  ? <a href={safe} target="_blank" rel="noopener noreferrer external"
                    referrerPolicy="no-referrer">
                    {sourceName(safe)} <ExternalLink aria-hidden="true"/>
                  </a>
                  : <span>{sourceName(locator.url)}</span>}
                <code>{formatLocator(locator.locator)}</code>
              </div>
              <p>{locator.excerpt}</p>
              <small>{locator.evidence_id} · SHA-256 {locator.content_hash.slice(0, 12)}…</small>
            </li>
          })}
        </ul>}
      </article>
    })}
  </div>
}

export default function AgentReviewPanel({
  industry, items, total, next_offset: nextOffset, loading, loadError,
  onLoadMore, onResultChanged,
}: AgentReviewPanelProps) {
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [pendingAssertion, setPendingAssertion] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [verificationDetail, setVerificationDetail] = useState<Record<string, string>>({})

  const verifyAllPages = async (resultId: string) => {
    let offset = 0
    let expectedTotal: number | null = null
    let accumulated = 0
    const details: string[] = []
    while (true) {
      const page = await api<AgentVerificationState>(
        `/industries/${industry}/agent-bridge/results/${resultId}/verify?limit=10&offset=${offset}`,
        { method: 'POST' },
      )
      if (page.result_id !== resultId || page.offset !== offset || page.limit !== 10) {
        throw new Error('核验分页合同异常：响应身份、offset 或 limit 与请求不一致')
      }
      if (expectedTotal === null) expectedTotal = page.total
      if (page.total !== expectedTotal || page.decisions.length > page.limit) {
        throw new Error('核验分页合同异常：total 变化或单页结果超过 limit')
      }
      accumulated += page.decisions.length
      details.push(page.detail)
      if (page.next_offset === null || page.next_offset === undefined) {
        if (accumulated !== page.total) {
          throw new Error('核验分页合同异常：累计结果数与 total 不一致')
        }
        break
      }
      if (page.next_offset <= offset || page.next_offset !== offset + page.decisions.length ||
          page.next_offset > page.total) {
        throw new Error('核验分页合同异常：next_offset 必须严格单调并匹配累计结果数')
      }
      offset = page.next_offset
    }
    setVerificationDetail(current => ({ ...current, [resultId]: [...new Set(details)].join(' · ') }))
  }

  const review = async (
    resultId: string,
    assertionId: string,
    decision: AgentReviewRequest['decision'],
  ) => {
    setError('')
    setPendingAssertion(assertionId)
    const payload: AgentReviewRequest = {
      assertion_id: assertionId,
      decision,
      note: notes[assertionId]?.trim() || '',
    }
    try {
      let updated = await api<AgentResultState>(
        `/industries/${industry}/agent-bridge/results/${resultId}/review`,
        { method: 'POST', body: JSON.stringify(payload) },
      )
      onResultChanged(updated)
      if (decision === 'submitted_for_verification') {
        await verifyAllPages(resultId)
        updated = await api<AgentResultState>(
          `/industries/${industry}/agent-bridge/results/${resultId}`)
        onResultChanged(updated)
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError))
    } finally {
      setPendingAssertion(null)
    }
  }

  const retryVerification = async (resultId: string, assertionId: string) => {
    setError('')
    setPendingAssertion(assertionId)
    try {
      await verifyAllPages(resultId)
      const updated = await api<AgentResultState>(
        `/industries/${industry}/agent-bridge/results/${resultId}`)
      onResultChanged(updated)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError))
    } finally {
      setPendingAssertion(null)
    }
  }

  if (loading && !items.length) return <div className="agent-review-empty agent-review-loading">
    <h3>导入结果与人工复核</h3>
    <p>正在读取 Agent 结果…</p>
  </div>

  if (loadError && !items.length) return <div className="agent-review-empty">
    <h3>导入结果与人工复核</h3>
    <p className="agent-review-error" role="alert">{loadError}</p>
  </div>

  if (!items.length) return <div className="agent-review-empty">
    <h3>导入结果与人工复核</h3>
    <p>尚未导入 Agent 结果。</p>
  </div>

  return <section className="agent-review-panel" aria-label="Agent 断言复核">
    <header className="agent-review-heading">
      <div>
        <h3>导入结果与断言复核</h3>
        <p>逐条判断；格式完整不代表证据充分，自动核验也不能越过人工提交。</p>
      </div>
      <span>{total} 份结果</span>
    </header>
    {(error || loadError) && <p className="agent-review-error" role="alert">
      {error || loadError}
    </p>}
    <div className="agent-review-results">
      {items.map(result => <article className="agent-review-result" key={result.result_id}>
        <header className="agent-result-summary">
          <div>
            <span className={`status-pill ${result.status}`}>{statusLabels[result.status]}</span>
            <h4>{result.summary}</h4>
          </div>
          <dl>
            <div><dt>Agent</dt><dd>{result.agent_id}</dd></div>
            <div><dt>任务</dt><dd>{result.task_id}</dd></div>
            <div><dt>导入时间</dt><dd>{formatImportTime(result.created_at)}</dd></div>
            <div><dt>状态</dt><dd>{result.status}</dd></div>
          </dl>
        </header>
        {verificationDetail[result.result_id] &&
          <p className="verification-detail" role="status">{verificationDetail[result.result_id]}</p>}
        <div className="assertion-list">
          {result.assertions.map((assertion, index) => {
            const reviewable = assertion.status === 'draft_review_required'
            const pending = pendingAssertion === assertion.id
            return <section className="assertion-review-card" key={assertion.id}>
              <header>
                <span>断言 {index + 1}</span>
                <span className={`status-pill ${assertion.status}`}>
                  {statusLabels[assertion.status]}
                </span>
              </header>
              <h5>{assertion.text}</h5>
              <p className="assertion-type">{assertion.type}</p>
              <div className="assertion-citations" aria-label={`引用 · ${assertion.text}`}>
                {assertion.citations.map(citation => {
                  const safe = safeExternalUrl(citation.url)
                  return safe
                    ? <a key={citation.id} href={safe} target="_blank"
                      rel="noopener noreferrer external" referrerPolicy="no-referrer">
                      {sourceName(safe)} <ExternalLink aria-hidden="true"/>
                    </a>
                    : <span key={citation.id}>无法安全打开：{citation.url}</span>
                })}
              </div>
              {assertion.verification && <GateList checks={assertion.verification}/>}
              {reviewable && <div className="assertion-review-controls">
                <label>
                  <span>复核说明</span>
                  <textarea
                    aria-label={`复核说明 · ${assertion.text}`}
                    value={notes[assertion.id] || ''}
                    onChange={event => setNotes(current => ({
                      ...current, [assertion.id]: event.target.value,
                    }))}
                    maxLength={2000}
                    rows={3}
                    placeholder="记录判断依据、待核对口径或驳回原因"
                  />
                </label>
                <div>
                  <button className="button danger" disabled={pendingAssertion !== null}
                    onClick={() => void review(result.result_id, assertion.id, 'rejected')}>
                    <XCircle aria-hidden="true"/>驳回
                  </button>
                  <button className="button secondary" disabled={pendingAssertion !== null}
                    onClick={() => void review(result.result_id, assertion.id, 'opinion')}>
                    <MessageSquareText aria-hidden="true"/>保留为观点
                  </button>
                  <button className="button primary" disabled={pendingAssertion !== null}
                    onClick={() => void review(
                      result.result_id, assertion.id, 'submitted_for_verification')}>
                    {pending ? <RotateCw className="spin" aria-hidden="true"/>
                      : <ShieldCheck aria-hidden="true"/>}
                    {pending ? '正在提交…' : '提交核验'}
                  </button>
                </div>
              </div>}
              {assertion.status === 'submitted_for_verification' &&
                <div className="assertion-retry-controls">
                  <button className="button secondary" disabled={pendingAssertion !== null}
                    onClick={() => void retryVerification(result.result_id, assertion.id)}>
                    <RotateCw className={pending ? 'spin' : ''} aria-hidden="true"/>
                    {pending ? '正在重新核验…' : '重试自动核验'}
                  </button>
                </div>}
            </section>
          })}
        </div>
      </article>)}
    </div>
    {nextOffset !== null && nextOffset !== undefined && <div className="agent-review-pagination">
      <button className="button secondary" disabled={loading} onClick={() => void onLoadMore()}>
        {loading ? '正在加载更多结果…' : `加载更多结果（${items.length} / ${total}）`}
      </button>
    </div>}
  </section>
}
