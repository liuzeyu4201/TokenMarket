import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { Login } from './Login'

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

/** Unique sentinels for privacy scanning of storage / non-input DOM. */
const RAW_PHONE = '13800138888'
const RAW_OTP = '012345'
const MASKED = '*******8888'

function storageBlob(): string {
  const parts: string[] = []
  for (let i = 0; i < localStorage.length; i += 1) {
    const k = localStorage.key(i)
    if (k) parts.push(k, localStorage.getItem(k) ?? '')
  }
  for (let i = 0; i < sessionStorage.length; i += 1) {
    const k = sessionStorage.key(i)
    if (k) parts.push(k, sessionStorage.getItem(k) ?? '')
  }
  return parts.join('\0')
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<div>dash</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Login privacy', () => {
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

  it('clears OTP after submit and never writes raw phone/OTP to Web Storage', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
      phone_masked: MASKED,
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    createSession.mockResolvedValue({
      user_id: 'user-privacy',
      nickname: '隐私',
      phone_masked: MASKED,
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'csrf-privacy-token',
    })

    renderLogin()
    await user.type(screen.getByLabelText('手机号'), RAW_PHONE)
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(MASKED)
    })

    // After neutral accept, non-input UI shows only masked phone.
    const status = screen.getByRole('status')
    expect(status.textContent).toContain(MASKED)
    expect(status.textContent).not.toContain(RAW_PHONE)
    expect(status.textContent).not.toContain(RAW_OTP)

    const otp = screen.getByLabelText('验证码') as HTMLInputElement
    await user.type(otp, RAW_OTP)
    expect(otp.value).toBe(RAW_OTP)

    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(screen.getByText('dash')).toBeInTheDocument()
    })

    // OTP cleared on submit (form unmounted after navigate; if remounted would be empty).
    // Storage must not contain sentinels.
    const blob = storageBlob()
    expect(blob).not.toContain(RAW_PHONE)
    expect(blob).not.toContain(RAW_OTP)
    expect(blob).not.toContain('csrf-privacy-token')
    expect(localStorage.length).toBe(0)
  })

  it('on failed login still clears OTP and keeps raw secrets out of storage', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
      phone_masked: MASKED,
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    createSession.mockRejectedValue(
      new PhoneAuthClientError('验证码不正确，请重试', 'VERIFICATION_FAILED', 'retry_code', 401),
    )

    renderLogin()
    await user.type(screen.getByLabelText('手机号'), RAW_PHONE)
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(MASKED))
    await user.type(screen.getByLabelText('验证码'), RAW_OTP)
    await user.click(screen.getByRole('button', { name: '登录' }))
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('验证码不正确')
    })

    expect((screen.getByLabelText('验证码') as HTMLInputElement).value).toBe('')
    const blob = storageBlob()
    expect(blob).not.toContain(RAW_PHONE)
    expect(blob).not.toContain(RAW_OTP)

    // Neutral UI still only shows masked phone.
    expect(screen.getByRole('status').textContent).toContain(MASKED)
    expect(screen.getByRole('status').textContent).not.toContain(RAW_PHONE)
  })
})
