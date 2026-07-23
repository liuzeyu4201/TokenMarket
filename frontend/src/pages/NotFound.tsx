import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <div className="card">
      <h1>页面未找到或暂未开放</h1>
      <p>您访问的路径尚不可用。</p>
      <p>
        <Link to="/">返回首页</Link>
        {' · '}
        <Link to="/register">去注册</Link>
      </p>
    </div>
  )
}

export default NotFound
