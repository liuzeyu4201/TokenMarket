import { Link, Outlet } from 'react-router-dom'

export function AppShell() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <strong>TokenMarket</strong>
        <nav aria-label="主导航">
          <Link to="/">首页</Link>
          <Link to="/register">注册</Link>
        </nav>
      </header>
      <main className="app-main" role="main">
        <Outlet />
      </main>
    </div>
  )
}

export default AppShell
