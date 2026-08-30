import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Breadcrumbs } from '../ui/Breadcrumbs'
import { ErrorBoundary } from '../ui/ErrorBoundary'
import { PageState } from '../ui/PageState'

const ROLE_LABEL: Record<string, string> = {
  buyer: '买家',
  seller: '卖家',
  both: '买家与卖家',
}

const TITLE: Record<string, string> = {
  '/': '首页',
  '/login': '登录',
  '/register': '注册',
  '/dashboard': '工作台',
  '/account/security': '账户安全',
  '/design-system': '组件目录',
  '/projects': '我的 Project',
}

function pageTitle(pathname: string): string {
  if (pathname.startsWith('/projects/') && pathname !== '/projects') {
    return 'Project 详情'
  }
  return TITLE[pathname] ?? '当前页'
}

export function AppShell() {
  const auth = useAuth()
  const location = useLocation()
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutStatus, setLogoutStatus] = useState<string | null>(null)
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine)
  const loginLinkRef = useRef<HTMLAnchorElement>(null)
  const logoutButtonRef = useRef<HTMLButtonElement>(null)
  const focusLoginAfterLogout = useRef(false)

  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  const onLogout = async () => {
    if (loggingOut) return
    setLoggingOut(true)
    setLogoutStatus('正在退出')
    try {
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
  const crumbs = useMemo(() => {
    if (location.pathname === '/') return [{ label: '首页' }]
    const here = pageTitle(location.pathname)
    return [{ label: '首页', to: '/' }, { label: here }]
  }, [location.pathname])

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
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
          <Link
            to="/design-system"
            aria-current={location.pathname === '/design-system' ? 'page' : undefined}
          >
            组件目录
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
              <span className="workspace-chip" data-testid="workspace-identity">
                工作区：{auth.session!.workspace === 'seller' ? '卖家' : '买家'}
              </span>
              {auth.session!.role === 'both' ? (
                <button
                  type="button"
                  className="link-button"
                  data-testid="workspace-switch"
                  onClick={() =>
                    void auth.switchWorkspace(
                      auth.session!.workspace === 'seller' ? 'buyer' : 'seller',
                    )
                  }
                >
                  切换到{auth.session!.workspace === 'seller' ? '买家' : '卖家'}工作区
                </button>
              ) : (
                <button type="button" className="link-button" disabled title="未授权">
                  切换工作区（未授权）
                </button>
              )}
              <Link
                to="/dashboard"
                aria-current={location.pathname === '/dashboard' ? 'page' : undefined}
              >
                工作台
              </Link>
              {auth.session!.workspace === 'buyer' ? (
                <Link
                  to="/projects"
                  aria-current={location.pathname.startsWith('/projects') ? 'page' : undefined}
                >
                  我的 Project
                </Link>
              ) : null}
              <Link
                to="/account/security"
                aria-current={location.pathname === '/account/security' ? 'page' : undefined}
              >
                账户安全
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
            </>
          ) : null}
        </nav>
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {logoutStatus}
        </div>
      </header>
      <main className="app-main" id="main-content" role="main">
        {!online ? <PageState kind="offline" /> : null}
        <Breadcrumbs items={crumbs} />
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}

export default AppShell
