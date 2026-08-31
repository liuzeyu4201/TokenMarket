import { Link } from 'react-router-dom'

export function AdminHome() {
  return (
    <div className="card" data-testid="admin-home">
      <h1>运营后台</h1>
      <p>按角色查看用户、连接、Project、价格、路由、账本、告警与审计。配置须走发布管线。</p>
      <p>
        <Link to="/admin/ops/connection">连接目录</Link>
        {' · '}
        <Link to="/admin/publish">配置发布</Link>
        {' · '}
        <Link to="/admin/wizards">高风险向导</Link>
      </p>
    </div>
  )
}
