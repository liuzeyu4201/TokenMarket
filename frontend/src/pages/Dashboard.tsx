import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { UnavailableAction } from '../ui/UnavailableAction'

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
      {session.workspace === 'buyer' ? (
        <p>
          <Link to="/projects">管理买家 Project</Link>
        </p>
      ) : (
        <p>
          当前为卖家工作区，买家 Project 入口不可用。
          <Link to="/connections">管理提供商连接</Link>
          {' · '}
          <Link to="/supply">供给工作台</Link>
        </p>
      )}
      {session.workspace === 'buyer' ? (
        <p className="hint">在 Project 详情中签发受限代理 Key；明文只展示一次。</p>
      ) : (
        <UnavailableAction label="创建代理 Key" />
      )}
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
