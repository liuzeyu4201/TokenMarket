import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { AppShell } from './layouts/AppShell'
import { Dashboard } from './pages/Dashboard'
import { DesignSystem } from './pages/DesignSystem'
import { Home } from './pages/Home'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { Register } from './pages/Register'
import { PhoneAuthClientError } from './api/v1/phoneAuth'

const bootstrapSession = vi.fn()

vi.mock('./api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('./api/v1/phoneAuth')>('./api/v1/phoneAuth')
  return {
    ...actual,
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: vi.fn(),
  }
})

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Home />} />
            <Route path="register" element={<Register />} />
            <Route path="login" element={<Login />} />
            <Route path="design-system" element={<DesignSystem />} />
            <Route
              path="dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('app shell routes', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
  })

  it('shows home placeholder not register form on /', async () => {
    renderAt('/')
    await waitFor(() => {
      expect(screen.getByText(/平台首页占位/)).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: '注册' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: '注册' }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/补充资料即可自动登录/)).toBeInTheDocument()
    expect(screen.queryByText(/注册不自动登录/)).not.toBeInTheDocument()
    expect(screen.getByText(/OpenAI/)).toBeInTheDocument()
    expect(screen.getByText(/测试额度/)).toBeInTheDocument()
  })

  it('shows design system catalog on /design-system', async () => {
    renderAt('/design-system')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '组件目录' })).toBeInTheDocument()
    })
  })

  it('shows unified phone verification on /register', async () => {
    renderAt('/register')
    await waitFor(() => {
      expect(screen.getByLabelText('手机号')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('验证码')).toBeInTheDocument()
  })

  it('shows login form on /login', async () => {
    renderAt('/login')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '登录' })).toBeInTheDocument()
    })
    expect(screen.getByLabelText('手机号')).toBeInTheDocument()
    expect(screen.getByLabelText('验证码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '获取验证码' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '前往注册' })).toBeInTheDocument()
  })

  it('redirects anonymous /dashboard visitors to login', async () => {
    renderAt('/dashboard')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '登录' })).toBeInTheDocument()
    })
    expect(screen.queryByTestId('dashboard-protected')).not.toBeInTheDocument()
  })

  it('shows not found for unknown path', async () => {
    renderAt('/no-such-page')
    await waitFor(() => {
      expect(screen.getByText(/页面未找到或暂未开放/)).toBeInTheDocument()
    })
  })
})
