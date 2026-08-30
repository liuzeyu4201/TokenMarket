import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../auth/AuthContext'
import { Login, safeInternalPath } from './Login'
import { Dashboard } from './Dashboard'

const requestChallenge = vi.fn()
const createSession = vi.fn()
const completeProfile = vi.fn()
const bootstrapSession = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    requestChallenge: (...args: unknown[]) => requestChallenge(...args),
    createSession: (...args: unknown[]) => createSession(...args),
    completeProfile: (...args: unknown[]) => completeProfile(...args),
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: vi.fn(),
  }
})

function renderLogin(initialEntry: string | { pathname: string; state?: unknown } = '/login') {
  const entry =
    typeof initialEntry === 'string'
      ? initialEntry
      : {
          pathname: initialEntry.pathname,
          state: initialEntry.state,
        }
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/register" element={<div>register-page</div>} />
          <Route path="/protected/target" element={<div>protected-target</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('safeInternalPath', () => {
  it('allows relative in-app paths and rejects open redirects', () => {
    expect(safeInternalPath('/dashboard')).toBe('/dashboard')
    expect(safeInternalPath('/protected/target')).toBe('/protected/target')
    expect(safeInternalPath('https://evil.example/x')).toBe('/dashboard')
    expect(safeInternalPath('//evil.example')).toBe('/dashboard')
    expect(safeInternalPath('javascript:alert(1)')).toBe('/dashboard')
    expect(safeInternalPath(undefined)).toBe('/dashboard')
  })
})

describe('Login page', () => {
  beforeEach(async () => {
    requestChallenge.mockReset()
    createSession.mockReset()
    completeProfile.mockReset()
    bootstrapSession.mockReset()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    localStorage.clear()
    sessionStorage.clear()
  })

  it('shows phone, OTP, get-code, login, and register entry', async () => {
    renderLogin()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '登录' })).toBeInTheDocument()
    })
    expect(screen.getByLabelText('手机号')).toBeInTheDocument()
    expect(screen.getByLabelText('验证码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '获取验证码' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '前往注册' })).toHaveAttribute('href', '/register')
  })

  it('enters neutral accepted state with masked phone and countdown after get-code', async () => {
    const user = userEvent.setup()
    const resendAt = new Date(Date.now() + 60_000).toISOString()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: resendAt,
    })
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))

    await waitFor(() => {
      const status = screen.getByRole('status')
      expect(status).toHaveTextContent('请求已受理')
      expect(status).toHaveTextContent('*******8000')
      expect(status).not.toHaveTextContent('已发送')
      expect(status).not.toHaveTextContent('13800138000')
    })
    expect(screen.getByRole('button', { name: /秒后可重新获取/ })).toBeDisabled()
  })

  it('focuses OTP after challenge accepted and is perceivable within 1s', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    const started = performance.now()
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('请求已受理')
      expect(screen.getByLabelText('验证码')).toHaveFocus()
    })
    expect(performance.now() - started).toBeLessThan(1000)
  })

  it('preserves leading zeros in OTP text input', async () => {
    const user = userEvent.setup()
    renderLogin()
    await waitFor(() => {
      expect(screen.getByLabelText('验证码')).toBeInTheDocument()
    })
    const otp = screen.getByLabelText('验证码')
    expect(otp).toHaveAttribute('type', 'text')
    await user.type(otp, '012345')
    expect((otp as HTMLInputElement).value).toBe('012345')
  })

  it('logs in and navigates to dashboard by default', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    createSession.mockResolvedValue({
      user_id: 'user-1',
      nickname: '买家甲',
      phone_masked: '*******8000',
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'csrf-token-value',
    })
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    await user.type(screen.getByLabelText('验证码'), '012345')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '工作台' })).toBeInTheDocument()
    })
    expect(createSession).toHaveBeenCalledWith({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      code: '012345',
    })
    expect(screen.getByText('*******8000')).toBeInTheDocument()
  })

  it('completes nickname and role after new-number OTP then auto-logs in', async () => {
    const user = userEvent.setup()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    createSession.mockRejectedValue(
      new PhoneAuthClientError(
        '请补充昵称和角色以完成注册',
        'PROFILE_COMPLETION_REQUIRED',
        'complete_profile',
        200,
      ),
    )
    completeProfile.mockResolvedValue({
      user_id: 'user-new',
      nickname: '新买家',
      phone_masked: '*******8000',
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'csrf-token-value',
    })
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    await user.type(screen.getByLabelText('验证码'), '012345')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '完成注册' })).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('昵称'), '新买家')
    await user.selectOptions(screen.getByLabelText('角色'), 'buyer')
    await user.click(screen.getByRole('button', { name: '完成并登录' }))
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '工作台' })).toBeInTheDocument()
    })
    expect(completeProfile).toHaveBeenCalledWith(
      { nickname: '新买家', role: 'buyer' },
      expect.any(String),
    )
  })

  it('restores safe in-app target from router state after login', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    createSession.mockResolvedValue({
      user_id: 'user-1',
      nickname: '买家甲',
      phone_masked: '*******8000',
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'csrf-token-value',
    })
    renderLogin({ pathname: '/login', state: { from: '/protected/target' } })
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    await user.type(screen.getByLabelText('验证码'), '000001')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(screen.getByText('protected-target')).toBeInTheDocument()
    })
  })

  it('guards in-flight get-code and login against double submit', async () => {
    const user = userEvent.setup()
    let resolveChallenge: (v: unknown) => void = () => {}
    requestChallenge.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveChallenge = resolve
        }),
    )
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    const getCode = screen.getByRole('button', { name: '获取验证码' })
    await user.click(getCode)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '提交中…' })).toBeDisabled()
    })
    await user.click(screen.getByRole('button', { name: '提交中…' }))
    expect(requestChallenge).toHaveBeenCalledTimes(1)
    resolveChallenge({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())

    let resolveLogin: (v: unknown) => void = () => {}
    createSession.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveLogin = resolve
        }),
    )
    await user.type(screen.getByLabelText('验证码'), '123456')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '登录中…' })).toBeDisabled()
    })
    await user.click(screen.getByRole('button', { name: '登录中…' }))
    expect(createSession).toHaveBeenCalledTimes(1)
    resolveLogin({
      user_id: 'user-1',
      nickname: '买家甲',
      phone_masked: '*******8000',
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'csrf-token-value',
    })
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '工作台' })).toBeInTheDocument()
    })
  })

  it('reuses the same Idempotency-Key for a single get-code action', async () => {
    const user = userEvent.setup()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    requestChallenge
      .mockRejectedValueOnce(
        new PhoneAuthClientError('网络错误，请稍后重试', 'INTERNAL_ERROR', 'retry_later', 0),
      )
      .mockResolvedValueOnce({
        challenge_id: '11111111-1111-1111-1111-111111111111',
        phone_masked: '*******8000',
        expires_at: new Date(Date.now() + 300_000).toISOString(),
        resend_available_at: new Date(Date.now() + 60_000).toISOString(),
      })
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    expect(requestChallenge).toHaveBeenCalledTimes(2)
    const key1 = requestChallenge.mock.calls[0][1]
    const key2 = requestChallenge.mock.calls[1][1]
    expect(key1).toBe(key2)
  })

  it('writes login result only through AuthContext', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    createSession.mockResolvedValue({
      user_id: 'user-ctx',
      nickname: '唯一上下文',
      phone_masked: '*******8000',
      role: 'seller',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'csrf-only-memory',
    })

    function CtxMirror() {
      const auth = useAuth()
      return (
        <div data-testid="mirror">
          {auth.status}:{auth.session?.userId ?? ''}:{auth.session?.nickname ?? ''}
        </div>
      )
    }

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <CtxMirror />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )

    await user.type(screen.getByLabelText('手机号'), '13900139000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    await user.type(screen.getByLabelText('验证码'), '654321')
    await user.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() => {
      expect(screen.getByTestId('mirror')).toHaveTextContent('authenticated:user-ctx:唯一上下文')
    })

    const dash = await screen.findByTestId('dashboard-protected')

    expect(within(dash).getByRole('heading', { name: '工作台' })).toBeInTheDocument()
    expect(within(dash).getByText('唯一上下文')).toBeInTheDocument()
  })
})
