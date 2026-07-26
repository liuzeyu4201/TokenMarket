import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import { Login } from '../pages/Login'
import type { SessionData } from '../types/auth'
import { PhoneAuthClientError } from '../api/v1/phoneAuth'

const requestChallenge = vi.fn()
const createSession = vi.fn()
const bootstrapSession = vi.fn()
const logoutSession = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>(
    '../api/v1/phoneAuth',
  )
  return {
    ...actual,
    requestChallenge: (...args: unknown[]) => requestChallenge(...args),
    createSession: (...args: unknown[]) => createSession(...args),
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: (...args: unknown[]) => logoutSession(...args),
  }
})

const SESSION: SessionData = {
  user_id: 'user-1111-2222-3333-444444444444',
  nickname: '测试用户',
  phone_masked: '*******8000',
  role: 'buyer',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: 'csrf-secret-must-not-persist',
}

function AuthProbe() {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="summary">
        {auth.session
          ? `${auth.session.userId}|${auth.session.phoneMasked}|${auth.session.role}`
          : 'none'}
      </span>
      <span data-testid="csrf">{auth.getCsrfToken() ?? ''}</span>
      <button type="button" onClick={() => auth.establishSession(SESSION)}>
        apply-session
      </button>
      <button type="button" onClick={() => auth.clearSession()}>
        clear-session
      </button>
      <button type="button" onClick={() => void auth.revalidate()}>
        revalidate
      </button>
      <button type="button" onClick={() => void auth.logout()}>
        logout
      </button>
    </div>
  )
}

function storageHasSensitive(): boolean {
  const keys = [...Object.keys(localStorage), ...Object.keys(sessionStorage)]
  const values = keys.flatMap((k) => [
    k,
    localStorage.getItem(k) ?? '',
    sessionStorage.getItem(k) ?? '',
  ])
  const blob = values.join('\n')
  return (
    blob.includes('csrf-secret-must-not-persist') ||
    blob.includes('__Host-tokenmarket_session') ||
    blob.includes(SESSION.user_id)
  )
}

describe('AuthContext', () => {
  beforeEach(() => {
    requestChallenge.mockReset()
    createSession.mockReset()
    bootstrapSession.mockReset()
    logoutSession.mockReset()
    localStorage.clear()
    sessionStorage.clear()
    // Default: anonymous bootstrap
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
  })

  it('starts checking then settles to anonymous when bootstrap is 401', async () => {
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    expect(screen.getByTestId('status').textContent).toMatch(/checking|anonymous/)
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    })
    expect(bootstrapSession).toHaveBeenCalled()
    expect(screen.getByTestId('summary')).toHaveTextContent('none')
    expect(screen.getByTestId('csrf')).toHaveTextContent('')
  })

  it('bootstrap success yields authenticated with memory CSRF only', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
    expect(screen.getByTestId('summary')).toHaveTextContent(
      'user-1111-2222-3333-444444444444|*******8000|buyer',
    )
    expect(screen.getByTestId('csrf')).toHaveTextContent('csrf-secret-must-not-persist')
    expect(storageHasSensitive()).toBe(false)
  })

  it('network failure becomes unavailable, not anonymous logout', async () => {
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('网络错误', 'INTERNAL_ERROR', 'retry_later', 0),
    )
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('unavailable')
    })
    expect(screen.getByTestId('summary')).toHaveTextContent('none')
  })

  it('authenticated survives revalidate network failure', async () => {
    bootstrapSession.mockResolvedValueOnce(SESSION)
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('服务不可用', 'SERVICE_UNAVAILABLE', 'retry_later', 503),
    )
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'revalidate' }))
    })
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
    expect(screen.getByTestId('csrf')).toHaveTextContent('csrf-secret-must-not-persist')
  })

  it('401 revalidate clears summary and CSRF', async () => {
    bootstrapSession.mockResolvedValueOnce(SESSION)
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'revalidate' }))
    })
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    })
    expect(screen.getByTestId('csrf')).toHaveTextContent('')
  })

  it('logout sends CSRF and clears session', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    logoutSession.mockResolvedValue(undefined)
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'logout' }))
    })
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    })
    expect(logoutSession).toHaveBeenCalledWith('csrf-secret-must-not-persist')
    expect(screen.getByTestId('csrf')).toHaveTextContent('')
  })

  it('establishSession is the sole writer of session summary and memory CSRF', async () => {
    const user = userEvent.setup()
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    })
    await user.click(screen.getByRole('button', { name: 'apply-session' }))
    expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    expect(screen.getByTestId('summary')).toHaveTextContent(
      'user-1111-2222-3333-444444444444|*******8000|buyer',
    )
    expect(screen.getByTestId('csrf')).toHaveTextContent('csrf-secret-must-not-persist')
    expect(storageHasSensitive()).toBe(false)
  })

  it('clearSession removes summary and CSRF without touching cookies API', async () => {
    const user = userEvent.setup()
    const cookieDesc = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
    const cookieGetter = vi.fn(() => '')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get: cookieGetter,
      set: vi.fn(),
    })
    try {
      render(
        <AuthProvider>
          <AuthProbe />
        </AuthProvider>,
      )
      await waitFor(() => {
        expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
      })
      await user.click(screen.getByRole('button', { name: 'apply-session' }))
      await user.click(screen.getByRole('button', { name: 'clear-session' }))
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
      expect(screen.getByTestId('summary')).toHaveTextContent('none')
      expect(screen.getByTestId('csrf')).toHaveTextContent('')
      expect(cookieGetter).not.toHaveBeenCalled()
    } finally {
      if (cookieDesc) {
        Object.defineProperty(document, 'cookie', cookieDesc)
      }
    }
  })

  it('login success writes only into AuthContext; credential/CSRF not persisted', async () => {
    const user = userEvent.setup()
    requestChallenge.mockResolvedValue({
      challenge_id: '11111111-1111-1111-1111-111111111111',
      phone_masked: '*******8000',
      expires_at: '2099-01-01T00:05:00.000Z',
      resend_available_at: '2099-01-01T00:01:00.000Z',
    })
    createSession.mockResolvedValue(SESSION)

    function Shell() {
      const auth = useAuth()
      return (
        <>
          <span data-testid="ctx-status">{auth.status}</span>
          <span data-testid="ctx-masked">{auth.session?.phoneMasked ?? ''}</span>
          <span data-testid="ctx-csrf">{auth.getCsrfToken() ?? ''}</span>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<div>dashboard-ok</div>} />
          </Routes>
        </>
      )
    }

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Shell />
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('ctx-status')).toHaveTextContent('anonymous')
    })

    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.click(screen.getByRole('button', { name: '获取验证码' }))
    await waitFor(() => {
      expect(screen.getByText(/请求已受理/)).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('验证码'), '012345')
    await user.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() => {
      expect(screen.getByTestId('ctx-status')).toHaveTextContent('authenticated')
      expect(screen.getByTestId('ctx-masked')).toHaveTextContent('*******8000')
      expect(screen.getByTestId('ctx-csrf')).toHaveTextContent('csrf-secret-must-not-persist')
      expect(screen.getByText('dashboard-ok')).toBeInTheDocument()
    })

    expect(screen.queryByRole('heading', { name: '登录' })).not.toBeInTheDocument()
    expect(storageHasSensitive()).toBe(false)
    expect(localStorage.length).toBe(0)
  })

  it('revalidates on window focus', async () => {
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(bootstrapSession).toHaveBeenCalledTimes(1)
    })
    bootstrapSession.mockResolvedValue(SESSION)
    await act(async () => {
      window.dispatchEvent(new Event('focus'))
    })
    await waitFor(() => {
      expect(bootstrapSession.mock.calls.length).toBeGreaterThanOrEqual(2)
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
  })
})
