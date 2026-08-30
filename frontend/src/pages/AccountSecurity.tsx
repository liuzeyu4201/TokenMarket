import { FormEvent, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { fetchSecuritySummary, revokeAllSessions } from '../api/v1/phoneAuth'
import { useAuth } from '../auth/AuthContext'

interface SecurityPayload {
  session: {
    issued_at: string
    expires_at: string
    generation: number
    client_hint: string | null
  }
  recent_events: Array<{
    event_type: string
    outcome: string
    reason_code: string
    request_id: string
    occurred_at: string
  }>
}

export function AccountSecurity() {
  const auth = useAuth()
  const [data, setData] = useState<SecurityPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (auth.status !== 'authenticated') return
    let cancelled = false
    void fetchSecuritySummary()
      .then((payload) => {
        if (!cancelled) setData(payload)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '无法加载安全摘要')
      })
    return () => {
      cancelled = true
    }
  }, [auth.status])

  if (auth.status === 'checking') {
    return <p>确认中…</p>
  }
  if (auth.status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: '/account/security' }} />
  }

  const onRevokeAll = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await revokeAllSessions(auth.getCsrfToken())
      auth.clearSession()
    } catch (err) {
      setError(err instanceof Error ? err.message : '结束全部会话失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" data-testid="account-security">
      <h1>账户安全</h1>
      <p>当前 Web 会话摘要。不会显示登录凭据。</p>
      {error ? (
        <div className="form-error" role="alert">
          {error}
        </div>
      ) : null}
      {data ? (
        <dl className="session-summary" aria-label="当前会话安全摘要">
          <div>
            <dt>世代</dt>
            <dd>{data.session.generation}</dd>
          </div>
          <div>
            <dt>签发</dt>
            <dd>{data.session.issued_at}</dd>
          </div>
          <div>
            <dt>过期</dt>
            <dd>{data.session.expires_at}</dd>
          </div>
          <div>
            <dt>来源摘要</dt>
            <dd>{data.session.client_hint ?? '—'}</dd>
          </div>
        </dl>
      ) : (
        <p>加载会话摘要…</p>
      )}
      {data && data.recent_events.length > 0 ? (
        <section aria-label="最近认证事件">
          <h2>最近认证事件</h2>
          <ul>
            {data.recent_events.map((ev) => (
              <li key={`${ev.request_id}-${ev.occurred_at}`}>
                {ev.event_type} · {ev.outcome} · {ev.request_id}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <form onSubmit={(e) => void onRevokeAll(e)}>
        <button type="submit" className="primary" disabled={busy}>
          {busy ? '处理中…' : '结束全部 Web 会话'}
        </button>
      </form>
    </div>
  )
}

export default AccountSecurity
