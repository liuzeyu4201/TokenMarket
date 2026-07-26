import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { clearChallenge, saveChallenge } from '../auth/challengeState'
import { Login, deriveLoginState } from './Login'
import { Dashboard } from './Dashboard'

const requestChallenge = vi.fn()
const createSession = vi.fn()
const bootstrapSession = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    requestChallenge: (...args: unknown[]) => requestChallenge(...args),
    createSession: (...args: unknown[]) => createSession(...args),
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: vi.fn(),
  }
})

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

function loginPage() {
  return screen.getByTestId('login-page')
}

describe('deriveLoginState', () => {
  it('maps flags to FR-019 primary states with correct priority', () => {
    expect(
      deriveLoginState({
        requestingCode: false,
        loggingIn: false,
        success: false,
        errorKind: null,
        hasChallenge: false,
        resendSeconds: 0,
      }),
    ).toBe('idle')
    expect(
      deriveLoginState({
        requestingCode: true,
        loggingIn: false,
        success: false,
        errorKind: null,
        hasChallenge: false,
        resendSeconds: 0,
      }),
    ).toBe('requesting')
    expect(
      deriveLoginState({
        requestingCode: false,
        loggingIn: true,
        success: false,
        errorKind: null,
        hasChallenge: true,
        resendSeconds: 30,
      }),
    ).toBe('verifying')
    expect(
      deriveLoginState({
        requestingCode: false,
        loggingIn: false,
        success: true,
        errorKind: null,
        hasChallenge: false,
        resendSeconds: 0,
      }),
    ).toBe('success')
    expect(
      deriveLoginState({
        requestingCode: false,
        loggingIn: false,
        success: false,
        errorKind: 'field-error',
        hasChallenge: false,
        resendSeconds: 0,
      }),
    ).toBe('field-error')
    expect(
      deriveLoginState({
        requestingCode: false,
        loggingIn: false,
        success: false,
        errorKind: null,
        hasChallenge: true,
        resendSeconds: 45,
      }),
    ).toBe('countdown')
    expect(
      deriveLoginState({
        requestingCode: false,
        loggingIn: false,
        success: false,
        errorKind: null,
        hasChallenge: true,
        resendSeconds: 0,
      }),
    ).toBe('accepted')
  })
})

describe('Login UI states (T111)', () => {
  beforeEach(async () => {
    requestChallenge.mockReset()
    createSession.mockReset()
    bootstrapSession.mockReset()
    clearChallenge()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    localStorage.clear()
    sessionStorage.clear()
  })

  it('starts in idle', async () => {
    renderLogin()
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'idle')
    })
  })

  it('enters requesting while get-code is in flight', async () => {
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
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'requesting')
    })
    resolveChallenge({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'countdown')
    })
  })

  it('enters countdown when resend deadline is in the future', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'countdown')
      expect(screen.getByTestId('resend-countdown')).toBeInTheDocument()
    })
  })

  it('enters accepted when challenge exists and resend is available', async () => {
    saveChallenge({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() - 1_000).toISOString(),
    })
    renderLogin()
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'accepted')
      expect(screen.getByTestId('resend-ready')).toBeInTheDocument()
    })
  })

  it('enters verifying while login is in flight', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    let resolveLogin: (v: unknown) => void = () => {}
    createSession.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveLogin = resolve
        }),
    )
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    await user.type(screen.getByLabelText('验证码'), '012345')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'verifying')
    })
    resolveLogin({
      user_id: 'user-1',
      nickname: '买家',
      phone_masked: '*******8000',
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'csrf-token',
    })
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '工作台' })).toBeInTheDocument()
    })
  })

  it('reaches success by establishing session and leaving login', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    createSession.mockResolvedValue({
      user_id: 'user-1',
      nickname: '买家',
      phone_masked: '*******8000',
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'csrf-token',
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
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
  })

  it('enters field-error for local and server field validation', async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'field-error')
    })

    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    requestChallenge.mockRejectedValue(
      new PhoneAuthClientError('请检查输入后重试', 'VALIDATION_ERROR', 'fix_fields', 400, 'req-1', {
        phone: ['手机号格式不正确'],
      }),
    )
    await user.type(screen.getByLabelText('手机号'), '123')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'field-error')
      expect(screen.getByText('手机号格式不正确')).toBeInTheDocument()
    })
  })

  it('enters code-error when OTP is wrong but challenge remains usable', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    createSession.mockRejectedValue(
      new PhoneAuthClientError('验证码不正确，请重试', 'VERIFICATION_FAILED', 'retry_code', 401),
    )
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    await user.type(screen.getByLabelText('验证码'), '111111')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'code-error')
      expect(screen.getByRole('alert')).toHaveTextContent('验证码不正确')
    })
  })

  it('enters expired when challenge is no longer usable', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    createSession.mockRejectedValue(
      new PhoneAuthClientError(
        '验证码已过期，请重新获取',
        'CHALLENGE_EXPIRED',
        'request_new_code',
        410,
      ),
    )
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    await user.type(screen.getByLabelText('验证码'), '111111')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'expired')
      expect(screen.getByRole('alert')).toHaveTextContent('过期')
    })
  })

  it('enters rate-limited on RATE_LIMITED', async () => {
    const user = userEvent.setup()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    requestChallenge.mockRejectedValue(
      new PhoneAuthClientError(
        '请求过于频繁，请稍后再试',
        'RATE_LIMITED',
        'wait_retry',
        429,
        'req-rl',
        undefined,
        30,
      ),
    )
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'rate-limited')
      expect(screen.getByRole('alert')).toHaveTextContent('过于频繁')
    })
  })

  it('enters unavailable on service/delivery outage', async () => {
    const user = userEvent.setup()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    requestChallenge.mockRejectedValue(
      new PhoneAuthClientError(
        '服务暂时不可用，请稍后重试',
        'DELIVERY_UNAVAILABLE',
        'retry_later',
        503,
      ),
    )
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(loginPage()).toHaveAttribute('data-login-state', 'unavailable')
      expect(screen.getByRole('alert')).toHaveTextContent('暂时不可用')
    })
  })
})
