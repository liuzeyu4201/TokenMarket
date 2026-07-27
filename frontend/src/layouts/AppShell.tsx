import { useEffect, useRef, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const ROLE_LABEL: Record<string, string> = {
  buyer: '买家',
  seller: '卖家',
  both: '买家与卖家',
}

export function AppShell() {
  const auth = useAuth()
  const location = useLocation()
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutStatus, setLogoutStatus] = useState<string | null>(null)
  const loginLinkRef = useRef<HTMLAnchorElement>(null)
  const logoutButtonRef = useRef<HTMLButtonElement>(null)
  const focusLoginAfterLogout = useRef(false)

  const onLogout = async () => {
    if (loggingOut) return
    setLoggingOut(true)
    setLogoutStatus('正在退出')
    try {
      // If logout outcome is uncertain, bootstrap first then attempt again.
      if (auth.status === 'unavailable') {
        await auth.revalidate()
      }
      await auth.logout()
      setLogoutStatus('已退出登录')
      focusLoginAfterLogout.current = true
    } finally {
      setLoggingOut(false)
    }
  }

  // After logout, return keyboard focus to the Login link (anonymous nav).
  useEffect(() => {
    if (auth.status === 'anonymous' && focusLoginAfterLogout.current) {
      focusLoginAfterLogout.current = false
      window.requestAnimationFrame(() => {
        loginLinkRef.current?.focus()
      })
    }
  }, [auth.status])

  const isAuthed = auth.status === 'authenticated' && auth.session
  const isChecking = auth.status === 'checking'
  const showAnonymousActions = auth.status === 'anonymous' || auth.status === 'unavailable'

  return (
    <div className="app-shell">
      <header className="app-header">
        <strong>
          <Link to="/" className="app-brand">
            TokenMarket
          </Link>
        </strong>
        <nav aria-label="主导航">
          <Link to="/" aria-current={location.pathname === '/' ? 'page' : undefined}>
            首页
          </Link>
          {isAuthed ? (
            <>
              <span
                className="session-chip"
                data-testid="shell-identity"
                aria-label={`当前用户 ${auth.session!.phoneMasked}，角色 ${ROLE_LABEL[auth.session!.role] ?? auth.session!.role}`}
              >
                <span data-testid="shell-phone-masked">{auth.session!.phoneMasked}</span>
                <span className="session-role" data-testid="shell-role">
                  {ROLE_LABEL[auth.session!.role] ?? auth.session!.role}
                </span>
              </span>
              <Link
                to="/dashboard"
                aria-current={location.pathname === '/dashboard' ? 'page' : undefined}
              >
                工作台
              </Link>
              <button
                ref={logoutButtonRef}
                type="button"
                className="link-button"
                onClick={() => void onLogout()}
                disabled={loggingOut}
                aria-busy={loggingOut || undefined}
                data-testid="shell-logout"
              >
                {loggingOut ? '退出中…' : '退出'}
              </button>
              {/* No login/register when authenticated — avoid duplicate auth actions. */}
            </>
          ) : isChecking ? (
            <span aria-busy="true" data-testid="shell-checking">
              确认中…
            </span>
          ) : showAnonymousActions ? (
            <>
              <Link
                ref={loginLinkRef}
                to="/login"
                id="shell-login-link"
                data-testid="shell-login"
                aria-current={location.pathname === '/login' ? 'page' : undefined}
              >
                登录
              </Link>
              <Link
                to="/register"
                data-testid="shell-register"
                aria-current={location.pathname === '/register' ? 'page' : undefined}
              >
                注册
              </Link>
              {/* No identity/logout when anonymous — avoid fake session UI. */}
            </>
          ) : null}
        </nav>
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {logoutStatus}
        </div>
      </header>
      <main className="app-main" id="main-content" role="main">
        <Outlet />
      </main>
    </div>
  )
}

export default AppShell
