import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { Login } from './Login'

const requestChallenge = vi.fn()
const createSession = vi.fn()
const bootstrapSession = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>(
    '../api/v1/phoneAuth',
  )
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
          <Route path="/dashboard" element={<div>dash</div>} />
          <Route path="/register" element={<div>register-page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Login accessibility (T110)', () => {
  beforeEach(async () => {
    requestChallenge.mockReset()
    createSession.mockReset()
    bootstrapSession.mockReset()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    localStorage.clear()
    sessionStorage.clear()
  })

  it('exposes visible labels associated with phone and OTP fields', async () => {
    renderLogin()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '登录' })).toBeInTheDocument()
    })
    const phone = screen.getByLabelText('手机号')
    const otp = screen.getByLabelText('验证码')
    expect(phone.tagName).toBe('INPUT')
    expect(otp.tagName).toBe('INPUT')
    // Labels are visible (not sr-only only).
    expect(screen.getByText('手机号', { selector: 'label' })).toBeVisible()
    expect(screen.getByText('验证码', { selector: 'label' })).toBeVisible()
  })

  it('wires aria-describedby for help text and field errors; sets aria-invalid', async () => {
    const user = userEvent.setup()
    renderLogin()
    await waitFor(() => expect(screen.getByLabelText('手机号')).toBeInTheDocument())

    const phone = screen.getByLabelText('手机号')
    const otp = screen.getByLabelText('验证码')
    const phoneDesc = phone.getAttribute('aria-describedby')
    const otpDesc = otp.getAttribute('aria-describedby')
    expect(phoneDesc).toBeTruthy()
    expect(otpDesc).toBeTruthy()
    // Help text targets exist.
    for (const id of (phoneDesc as string).split(/\s+/)) {
      expect(document.getElementById(id)).toBeTruthy()
    }
    for (const id of (otpDesc as string).split(/\s+/)) {
      expect(document.getElementById(id)).toBeTruthy()
    }

    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(screen.getByLabelText('手机号')).toHaveAttribute('aria-invalid', 'true')
    })
    const phoneAfter = screen.getByLabelText('手机号')
    const descAfter = phoneAfter.getAttribute('aria-describedby') ?? ''
    expect(descAfter.split(/\s+/).some((id) => document.getElementById(id)?.classList.contains('field-error'))).toBe(
      true,
    )
  })

  it('marks form busy and exposes status / alert roles during flow', async () => {
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
      const form = screen.getByLabelText('手机号').closest('form')
      expect(form).toHaveAttribute('aria-busy', 'true')
    })
    expect(screen.getByRole('button', { name: '提交中…' })).toHaveAttribute(
      'aria-busy',
      'true',
    )

    resolveChallenge({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('请求已受理')
    })

    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    createSession.mockRejectedValue(
      new PhoneAuthClientError('验证码不正确，请重试', 'VERIFICATION_FAILED', 'retry_code', 401),
    )
    // Enable login after countdown would block resend but login is still allowed.
    await user.type(screen.getByLabelText('验证码'), '000000')
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('验证码不正确')
    })
  })

  it('moves focus to the invalid field on field errors', async () => {
    const user = userEvent.setup()
    renderLogin()
    await waitFor(() => expect(screen.getByLabelText('手机号')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(screen.getByLabelText('手机号')).toHaveFocus()
    })
  })

  it('moves focus to OTP after challenge accepted', async () => {
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
      expect(screen.getByLabelText('验证码')).toHaveFocus()
    })
  })

  it('OTP uses text + numeric inputMode + one-time-code autocomplete (leading zeros)', async () => {
    const user = userEvent.setup()
    renderLogin()
    await waitFor(() => expect(screen.getByLabelText('验证码')).toBeInTheDocument())
    const otp = screen.getByLabelText('验证码')
    expect(otp).toHaveAttribute('type', 'text')
    expect(otp).toHaveAttribute('inputMode', 'numeric')
    expect(otp).toHaveAttribute('autoComplete', 'one-time-code')
    await user.type(otp, '012345')
    expect((otp as HTMLInputElement).value).toBe('012345')
  })

  it('supports logical keyboard tab order: phone → get-code → OTP → login', async () => {
    const user = userEvent.setup()
    renderLogin()
    await waitFor(() => expect(screen.getByLabelText('手机号')).toBeInTheDocument())

    const phone = screen.getByLabelText('手机号')
    const getCode = screen.getByRole('button', { name: '获取验证码' })
    const otp = screen.getByLabelText('验证码')
    const loginBtn = screen.getByRole('button', { name: '登录' })

    phone.focus()
    expect(phone).toHaveFocus()
    await user.tab()
    expect(getCode).toHaveFocus()
    await user.tab()
    expect(otp).toHaveFocus()
    await user.tab()
    expect(loginBtn).toHaveFocus()
  })

  it('does not announce ticking countdown every second via live region', async () => {
    const user = userEvent.setup()
    vi.useFakeTimers({ shouldAdvanceTime: true })
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
      expect(screen.getByTestId('resend-countdown')).toBeInTheDocument()
    })
    const countdown = screen.getByTestId('resend-countdown')
    expect(countdown).toHaveAttribute('aria-hidden', 'true')
    // Live status regions must not contain the changing second counter.
    for (const status of screen.getAllByRole('status')) {
      expect(status.textContent ?? '').not.toMatch(/\d+\s*秒后可重新获取/)
    }
    vi.useRealTimers()
  })

  it('keeps register entry reachable for keyboard users', async () => {
    renderLogin()
    await waitFor(() => {
      expect(screen.getByRole('link', { name: '前往注册' })).toHaveAttribute(
        'href',
        '/register',
      )
    })
    const page = screen.getByTestId('login-page')
    expect(within(page).getByRole('link', { name: '前往注册' })).toBeInTheDocument()
  })
})
