import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { saveChallenge, loadChallenge, CHALLENGE_STORAGE_KEY } from '../auth/challengeState'
import { AppShell } from './AppShell'
import { PhoneAuthClientError } from '../api/v1/phoneAuth'
import type { SessionData } from '../types/auth'

const bootstrapSession = vi.fn()
const logoutSession = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: (...args: unknown[]) => logoutSession(...args),
    switchWorkspace: vi.fn(),
  }
})

const SESSION: SessionData = {
  user_id: 'shell-a11y-user',
  nickname: '可访问用户',
  phone_masked: '*******9999',
  role: 'both',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: 'csrf-shell-a11y',
}

function renderShell(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<div>home-child</div>} />
            <Route path="login" element={<div>login-child</div>} />
            <Route path="register" element={<div>register-child</div>} />
            <Route path="dashboard" element={<div>dashboard-child</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('AppShell accessibility (T113)', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    logoutSession.mockReset()
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    sessionStorage.clear()
    localStorage.clear()
  })

  it('exposes a semantic primary navigation landmark', async () => {
    renderShell()
    await waitFor(() => {
      expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument()
    })
    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '跳到主要内容' })).toHaveAttribute(
      'href',
      '#main-content',
    )
    expect(screen.getByRole('navigation', { name: '面包屑' })).toBeInTheDocument()
  })

  it('shows discoverable login/register only when anonymous — no fake identity', async () => {
    renderShell()
    await waitFor(() => {
      expect(screen.getByTestId('shell-login')).toBeInTheDocument()
      expect(screen.getByTestId('shell-register')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('shell-identity')).not.toBeInTheDocument()
    expect(screen.queryByTestId('shell-logout')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '退出' })).not.toBeInTheDocument()
  })

  it('shows masked identity, role, protected entry and logout when authenticated', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    renderShell()
    await waitFor(() => {
      expect(screen.getByTestId('shell-identity')).toBeInTheDocument()
    })
    const identity = screen.getByTestId('shell-identity')
    const accessibleName = identity.getAttribute('aria-label') ?? ''
    expect(accessibleName).toContain('*******9999')
    expect(accessibleName).toContain('买家与卖家')
    expect(screen.getByTestId('shell-phone-masked')).toHaveTextContent('*******9999')
    expect(screen.getByTestId('shell-role')).toHaveTextContent('买家与卖家')
    expect(screen.getByRole('link', { name: '工作台' })).toHaveAttribute('href', '/dashboard')
    expect(screen.getByTestId('shell-logout')).toBeInTheDocument()
    // Authenticated chrome must not duplicate anonymous auth actions.
    expect(screen.queryByTestId('shell-login')).not.toBeInTheDocument()
    expect(screen.queryByTestId('shell-register')).not.toBeInTheDocument()
  })

  it('marks logout busy while exiting and returns focus to login link', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    let resolveLogout: () => void = () => {}
    logoutSession.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveLogout = resolve
        }),
    )
    const user = userEvent.setup()
    renderShell()
    await waitFor(() => {
      expect(screen.getByTestId('shell-logout')).toBeInTheDocument()
    })
    const logoutBtn = screen.getByTestId('shell-logout')
    await user.click(logoutBtn)
    await waitFor(() => {
      expect(logoutBtn).toHaveAttribute('aria-busy', 'true')
      expect(logoutBtn).toBeDisabled()
      expect(logoutBtn).toHaveTextContent('退出中…')
    })
    await act(async () => {
      resolveLogout()
    })
    await waitFor(() => {
      expect(screen.getByTestId('shell-login')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId('shell-login')).toHaveFocus()
    })
  })

  it('clears challenge sessionStorage on logout (terminal/invalidation cleanup path)', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    logoutSession.mockResolvedValue(undefined)
    saveChallenge({
      challenge_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
      phone_masked: '*******8888',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      resend_available_at: new Date(Date.now() + 60_000).toISOString(),
    })
    expect(loadChallenge()).not.toBeNull()

    const user = userEvent.setup()
    renderShell()
    await waitFor(() => expect(screen.getByTestId('shell-logout')).toBeInTheDocument())
    await user.click(screen.getByTestId('shell-logout'))
    await waitFor(() => {
      expect(screen.getByTestId('shell-login')).toBeInTheDocument()
    })
    expect(sessionStorage.getItem(CHALLENGE_STORAGE_KEY)).toBeNull()
    expect(loadChallenge()).toBeNull()
  })

  it('does not show authenticated actions during checking', async () => {
    let resolveBootstrap: (v: SessionData) => void = () => {}
    bootstrapSession.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveBootstrap = resolve
        }),
    )
    renderShell()
    expect(screen.getByTestId('shell-checking')).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByTestId('shell-login')).not.toBeInTheDocument()
    expect(screen.queryByTestId('shell-logout')).not.toBeInTheDocument()
    await act(async () => {
      resolveBootstrap(SESSION)
    })
    await waitFor(() => {
      expect(screen.getByTestId('shell-identity')).toBeInTheDocument()
    })
  })
})
