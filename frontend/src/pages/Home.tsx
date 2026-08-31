import { Link } from 'react-router-dom'
import { UnavailableAction } from '../ui/UnavailableAction'

export function Home() {
  return (
    <div className="card">
      <h1>TokenMarket</h1>
      <p>平台首页占位。业务能力将陆续开放。</p>
      <p>
        使用 <Link to="/login">手机号验证码</Link> 登录或注册。新用户验证后补充资料即可自动登录。
      </p>
      <section aria-labelledby="product-boundary">
        <h2 id="product-boundary">产品边界</h2>
        <p>数据面按 OpenAI、Anthropic、Google Vertex 各自原生协议透传，不做跨协议转换。</p>
        <p>
          Project
          分为共享与专享：共享仅无状态调用；专享独占连接，故障时失败关闭，不会自动回退共享池。
        </p>
        <p>V0.2 仅提供测试额度，不可购买、转让、兑换或提现，也没有充值、支付或法币锚定。</p>
      </section>
      <section aria-labelledby="coming-soon">
        <h2 id="coming-soon">即将开放</h2>
        <p>以下入口尚未交付，不会提交请求。</p>
        <UnavailableAction label="创建买家 Project" />
        <UnavailableAction label="接入卖家连接" />
      </section>
    </div>
  )
}

export default Home
