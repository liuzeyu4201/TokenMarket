import { Link } from 'react-router-dom'

export function Home() {
  return (
    <div className="card">
      <h1>TokenMarket</h1>
      <p>平台首页占位。业务能力将陆续开放。</p>
      <p>
        新用户请前往 <Link to="/register">注册</Link> 创建账户（注册成功后不会自动登录）。
      </p>
    </div>
  )
}

export default Home
