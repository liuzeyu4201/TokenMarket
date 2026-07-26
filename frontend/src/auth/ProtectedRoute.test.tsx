import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from './AuthContext'
import { ProtectedRoute } from './ProtectedRoute'
import { PhoneAuthClientError } from '../api/v1/phoneAuth'
import type { SessionData } from '../types/auth'

const bootstrapSession = vi.fn()
const logoutSession = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>(
    '../api/v1/phoneAuth',
  )
  return {
    ...actual,
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: (...args: unknown[]) => logoutSession(...args),
  }
})

const SESSION: SessionData = {
  user_id: 'u1',
  nickname: '守卫用户',
  phone_masked: '*******1234',
  role: 'seller',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: 'csrf-guard',
}

function renderProtected(path = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div data-testid="secret">受保护内容</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div data-testid="login-page">登录页</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    logoutSession.mockReset()
  })

  it('does not flash protected content while checking', async () => {
    let resolveBoot!: (v: SessionData) => void
    bootstrapSession.mockReturnValue(
      new Promise<SessionData>((resolve) => {
        resolveBoot = resolve
      }),
    )
    renderProtected()
    expect(screen.getByTestId('auth-checking')).toBeInTheDocument()
    expect(screen.queryByTestId('secret')).not.toBeInTheDocument()
    resolveBoot(SESSION)
    await waitFor(() => {
      expect(screen.getByTestId('secret')).toBeInTheDocument()
    })
  })

  it('redirects anonymous to login with return path', async () => {
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    renderProtected('/dashboard')
    await waitFor(() => {
      expect(screen.getByTestId('login-page')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('secret')).not.toBeInTheDocument()
  })

  it('shows unavailable without protected content', async () => {
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('不可用', 'SERVICE_UNAVAILABLE', 'retry_later', 503),
    )
    renderProtected()
    await waitFor(() => {
      expect(screen.getByTestId('auth-unavailable')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('secret')).not.toBeInTheDocument()
  })

  it('renders children when authenticated', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    renderProtected()
    await waitFor(() => {
      expect(screen.getByTestId('secret')).toBeInTheDocument()
    })
  })
})
