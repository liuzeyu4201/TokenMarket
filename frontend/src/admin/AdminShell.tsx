import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { Button } from '../ui/Button'
import { ErrorBoundary } from '../ui/ErrorBoundary'
import { PageState } from '../ui/PageState'
import { useAdminAuth } from './AdminAuthContext'

const KIND_LABEL: Record<string, string> = {
  user: '用户',
  session: '会话',
  connection: '连接',
  project: 'Project',
  price: '价格',
  route: '路由',
  ledger: '账本',
  alert: '告警',
  audit: '审计',
}

export function AdminShell() {
  const auth = useAdminAuth()
  const location = useLocation()

  if (auth.status === 'checking') {
    return <PageState kind="loading" />
  }

  const onLogin = location.pathname.endsWith('/login') || location.pathname === '/login'

  if (auth.status === 'anonymous' && !onLogin) {
    return <Navigate to="/admin/login" replace />
  }

  if (auth.status === 'authenticated' && onLogin) {
    return <Navigate to="/admin" replace />
  }

  return (
    <div className="app-shell" data-testid="admin-shell">
      <a className="skip-link" href="#admin-main">
        跳到主要内容
      </a>
      <header className="app-header">
        <strong>
          <Link to="/admin" className="app-brand">
            TokenMarket 运营后台
          </Link>
        </strong>
        <nav aria-label="运营导航">
          {Object.entries(KIND_LABEL).map(([kind, label]) => (
            <Link
              key={kind}
              to={`/admin/ops/${kind}`}
              aria-current={location.pathname.includes(`/ops/${kind}`) ? 'page' : undefined}
            >
              {label}
            </Link>
          ))}
          <Link
            to="/admin/publish"
            aria-current={location.pathname.includes('/publish') ? 'page' : undefined}
          >
            配置发布
          </Link>
          <Link
            to="/admin/wizards"
            aria-current={location.pathname.includes('/wizards') ? 'page' : undefined}
          >
            高风险向导
          </Link>
        </nav>
        {auth.session ? (
          <span className="session-chip" data-testid="admin-identity">
            {auth.session.role}
            {auth.session.readonly ? '（只读）' : ''}
            <Button variant="link" type="button" onClick={() => void auth.logout()}>
              退出
            </Button>
          </span>
        ) : null}
      </header>
      <main id="admin-main">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
