import { Link } from 'react-router-dom'

export function Home() {
  return (
    <div className="card">
      <h1>TokenMarket</h1>
      <p>平台首页占位。业务能力将陆续开放。</p>
      <p>
        使用 <Link to="/login">手机号验证码</Link> 登录或注册。新用户验证后补充资料即可自动登录。
      </p>
    </div>
  )
}

export default Home
