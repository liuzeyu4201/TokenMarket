import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { PhoneAuthClientError } from '../api/v1/phoneAuth'
import { AccountSecurity } from './AccountSecurity'

const bootstrapSession = vi.fn()
const fetchSecuritySummary = vi.fn()
const revokeAllSessions = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    fetchSecuritySummary: (...args: unknown[]) => fetchSecuritySummary(...args),
    revokeAllSessions: (...args: unknown[]) => revokeAllSessions(...args),
    logoutSession: vi.fn(),
  }
})

describe('AccountSecurity', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    fetchSecuritySummary.mockReset()
    revokeAllSessions.mockReset()
  })

  it('redirects anonymous visitors to login', async () => {
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    render(
      <MemoryRouter initialEntries={['/account/security']}>
        <AuthProvider>
          <Routes>
            <Route path="/account/security" element={<AccountSecurity />} />
            <Route path="/login" element={<div>login-page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByText('login-page')).toBeInTheDocument()
    })
  })

  it('shows redacted summary without token text', async () => {
    bootstrapSession.mockResolvedValue({
      user_id: 'u1',
      nickname: '安全用户',
      phone_masked: '*******8000',
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'c'.repeat(32),
    })
    fetchSecuritySummary.mockResolvedValue({
      session: {
        issued_at: '2026-08-31T00:00:00+00:00',
        expires_at: '2026-08-31T01:00:00+00:00',
        generation: 2,
        client_hint: 'abcd1234',
      },
      recent_events: [
        {
          event_type: 'session_issued',
          outcome: 'success',
          reason_code: 'login',
          request_id: 'req-1',
          occurred_at: '2026-08-31T00:00:00+00:00',
        },
      ],
    })
    render(
      <MemoryRouter initialEntries={['/account/security']}>
        <AuthProvider>
          <Routes>
            <Route path="/account/security" element={<AccountSecurity />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '账户安全' })).toBeInTheDocument()
    })
    expect(await screen.findByText('abcd1234')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.queryByText(/csrf/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '结束全部 Web 会话' })).toBeInTheDocument()
  })

  it('revoke-all calls API with CSRF', async () => {
    const user = userEvent.setup()
    bootstrapSession.mockResolvedValue({
      user_id: 'u1',
      nickname: '安全用户',
      phone_masked: '*******8000',
      role: 'buyer',
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
      csrf_token: 'c'.repeat(32),
    })
    fetchSecuritySummary.mockResolvedValue({
      session: {
        issued_at: '2026-08-31T00:00:00+00:00',
        expires_at: '2026-08-31T01:00:00+00:00',
        generation: 2,
        client_hint: null,
      },
      recent_events: [],
    })
    revokeAllSessions.mockResolvedValue(undefined)
    render(
      <MemoryRouter initialEntries={['/account/security']}>
        <AuthProvider>
          <Routes>
            <Route path="/account/security" element={<AccountSecurity />} />
            <Route path="/login" element={<div>login-page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '结束全部 Web 会话' })).toBeEnabled()
    })
    await user.click(screen.getByRole('button', { name: '结束全部 Web 会话' }))
    await waitFor(() => {
      expect(revokeAllSessions).toHaveBeenCalledWith('c'.repeat(32))
    })
  })
})
