import { FormEvent, useState } from 'react'
import { Button } from '../../ui/Button'
import { FormField } from '../../ui/FormField'
import { Notice } from '../../ui/Notice'
import { useAdminAuth } from '../AdminAuthContext'

export function AdminLogin() {
  const auth = useAdminAuth()
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [mfa, setMfa] = useState('')
  const [busy, setBusy] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    try {
      await auth.login(login, password, mfa)
    } catch {
      // error shown via auth.error
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" data-testid="admin-login">
      <h1>管理员登录</h1>
      <p>使用独立管理员会话。买家 Cookie 无法进入此后台。</p>
      {auth.error ? (
        <Notice tone="error">
          <p>{auth.error}</p>
        </Notice>
      ) : null}
      <form onSubmit={(e) => void onSubmit(e)}>
        <FormField
          id="admin-login"
          label="账号"
          value={login}
          onChange={(ev) => setLogin(ev.target.value)}
          required
        />
        <FormField
          id="admin-password"
          label="密码"
          type="password"
          value={password}
          onChange={(ev) => setPassword(ev.target.value)}
          required
        />
        <FormField
          id="admin-mfa"
          label="MFA"
          value={mfa}
          onChange={(ev) => setMfa(ev.target.value)}
          required
        />
        <Button type="submit" loading={busy}>
          登录
        </Button>
      </form>
    </div>
  )
}
