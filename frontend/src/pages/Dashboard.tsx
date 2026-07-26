import { useAuth } from '../auth/AuthContext'

const ROLE_LABEL: Record<string, string> = {
  buyer: '买家',
  seller: '卖家',
  both: '买家与卖家',
}

/**
 * Protected placeholder shell for authenticated users.
 * Guarded by ProtectedRoute — no buyer/seller/billing/Key business behavior.
 * Session summary is display-only; logout lives in AppShell for consistent nav.
 */
export function Dashboard() {
  const auth = useAuth()
  const session = auth.session

  if (!session) {
    return null
  }

  return (
    <div className="card" data-testid="dashboard-protected">
      <h1>工作台</h1>
      <p>受保护首页占位。业务能力将陆续开放。</p>
      <p className="hint">使用顶部导航的「退出」可结束当前会话。刷新后会话由服务端 Cookie 恢复。</p>
      <dl className="session-summary" aria-label="当前会话摘要">
        <div>
          <dt>昵称</dt>
          <dd>{session.nickname}</dd>
        </div>
        <div>
          <dt>手机号</dt>
          <dd>{session.phoneMasked}</dd>
        </div>
        <div>
          <dt>角色</dt>
          <dd>{ROLE_LABEL[session.role] ?? session.role}</dd>
        </div>
      </dl>
    </div>
  )
}

export default Dashboard
