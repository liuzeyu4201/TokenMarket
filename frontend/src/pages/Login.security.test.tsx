/**
 * US2 Login security UX (T061 / T127):
 * idempotency-key lifecycle, countdown, rate-limit, neutral copy, zero extra calls.
 */
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

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Login security UX', () => {
  beforeEach(async () => {
    requestChallenge.mockReset()
    createSession.mockReset()
    bootstrapSession.mockReset()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    sessionStorage.clear()
    localStorage.clear()
  })

  it('reuses one Idempotency-Key across in-flight double clicks (zero extra calls)', async () => {
    const user = userEvent.setup()
    let resolveChallenge!: (v: unknown) => void
    const pending = new Promise((resolve) => {
      resolveChallenge = resolve
    })
    requestChallenge.mockImplementation(() => pending)

    renderLogin()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '登录' })).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('手机号'), '13800138000')

    const btn = screen.getByRole('button', { name: '获取验证码' })
    await user.click(btn)
    await user.click(btn)
    await user.click(btn)

    expect(requestChallenge).toHaveBeenCalledTimes(1)
    const key1 = requestChallenge.mock.calls[0][1] as string
    expect(key1).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)

    resolveChallenge({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('请求已受理')
    })
  })

  it('shows 60s countdown and disables resend after neutral accept', async () => {
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
      expect(screen.getByRole('button', { name: /秒后可重新获取/ })).toBeDisabled()
    })
    const label = screen.getByRole('button', { name: /秒后可重新获取/ }).textContent ?? ''
    const seconds = Number.parseInt(label, 10)
    expect(seconds).toBeGreaterThan(0)
    expect(seconds).toBeLessThanOrEqual(60)
  })

  it('maps RATE_LIMITED to neutral wait UI without account existence leak', async () => {
    const user = userEvent.setup()
    const { PhoneAuthClientError } = await import('../api/v1/phoneAuth')
    requestChallenge.mockRejectedValue(
      new PhoneAuthClientError(
        '请求过于频繁，请稍后再试',
        'RATE_LIMITED',
        'wait_retry',
        429,
        'rid-rl',
        undefined,
        42,
      ),
    )
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/频繁|稍后/)
    })
    const alert = screen.getByRole('alert')
    expect(alert).not.toHaveTextContent(/不存在|未注册|suspended|deleted/i)
    expect(screen.queryByText(/13800138000/)).not.toBeInTheDocument()
  })

  it('keeps neutral accepted copy (never claims SMS delivered)', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13900139000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('请求已受理')
    })
    const status = screen.getByRole('status').textContent ?? ''
    expect(status).toMatch(/不表示|不保证|受理/)
    expect(status).not.toMatch(/已发送|短信已达|发送成功/)
    expect(status).not.toContain('13900139000')
    expect(status).toContain('*******8000')
  })

  it('rotates idempotency key after successful accept for a new get-code action', async () => {
    const user = userEvent.setup()
    requestChallenge
      .mockResolvedValueOnce({
        challenge_id: '11111111-1111-1111-1111-111111111111',
        phone_masked: '*******8000',
        expires_at: new Date(Date.now() + 300_000).toISOString(),
        resend_available_at: new Date(Date.now() - 1000).toISOString(),
      })
      .mockResolvedValueOnce({
        challenge_id: '22222222-2222-2222-2222-222222222222',
        phone_masked: '*******8000',
        expires_at: new Date(Date.now() + 300_000).toISOString(),
        resend_available_at: new Date(Date.now() + 60_000).toISOString(),
      })

    renderLogin()
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(requestChallenge).toHaveBeenCalledTimes(1)
    })
    const firstKey = requestChallenge.mock.calls[0][1] as string

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '获取验证码' })).toBeEnabled()
    })
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(requestChallenge).toHaveBeenCalledTimes(2)
    })
    const secondKey = requestChallenge.mock.calls[1][1] as string
    expect(secondKey).not.toBe(firstKey)
  })
})
