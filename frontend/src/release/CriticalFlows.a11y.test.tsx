import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminApp } from '../admin/AdminApp'
import { AuthProvider } from '../auth/AuthContext'
import { Home } from '../pages/Home'
import { Login } from '../pages/Login'
import { assertNoSeriousA11y } from '../ui/assertA11y'
import { PhoneAuthClientError } from '../api/v1/phoneAuth'

const bootstrapSession = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: vi.fn(),
  }
})

vi.mock('../admin/api', async () => {
  const actual = await vi.importActual<typeof import('../admin/api')>('../admin/api')
  return {
    ...actual,
    adminSession: vi.fn(async () => {
      throw new Error('unauth')
    }),
    adminLogin: vi.fn(),
    adminLogout: vi.fn(),
  }
})

describe('critical flow a11y', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
  })

  it('home has no serious a11y violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'TokenMarket' })).toBeInTheDocument()
    })
    assertNoSeriousA11y(container)
  })

  it('login has labelled controls', async () => {
    const { container } = render(
      <MemoryRouter>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByLabelText('手机号')).toBeInTheDocument()
    })
    assertNoSeriousA11y(container)
  })

  it('admin login is isolated and labelled', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/admin/login']}>
        <Routes>
          <Route path="/admin/*" element={<AdminApp />} />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('admin-login')).toBeInTheDocument()
    })
    expect(screen.queryByLabelText('手机号')).not.toBeInTheDocument()
    assertNoSeriousA11y(container)
  })
})
