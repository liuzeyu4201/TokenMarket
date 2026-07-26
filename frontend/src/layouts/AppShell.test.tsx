import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, AUTH_BROADCAST_CHANNEL } from '../auth/AuthContext'
import { AppShell } from './AppShell'
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
  user_id: 'shell-user',
  nickname: '壳层用户',
  phone_masked: '*******9999',
  role: 'both',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: 'csrf-shell-token',
}

function renderShell() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<div>child</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('AppShell', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    logoutSession.mockReset()
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
  })

  it('shows login/register for anonymous users', async () => {
    renderShell()
    await waitFor(() => {
      expect(screen.getByRole('link', { name: '登录' })).toHaveAttribute('href', '/login')
      expect(screen.getByRole('link', { name: '注册' })).toHaveAttribute('href', '/register')
    })
    expect(screen.getByText('child')).toBeInTheDocument()
  })

  it('shows masked identity, role, dashboard and logout when authenticated', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    renderShell()
    await waitFor(() => {
      expect(screen.getByTestId('shell-identity')).toHaveTextContent('*******9999')
    })
    expect(screen.getByTestId('shell-identity')).toHaveTextContent('买家与卖家')
    expect(screen.getByRole('link', { name: '工作台' })).toHaveAttribute(
      'href',
      '/dashboard',
    )
    expect(screen.getByRole('button', { name: '退出' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '登录' })).not.toBeInTheDocument()
  })

  it('logout invokes API with CSRF and returns to anonymous nav', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    logoutSession.mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderShell()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '退出' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: '退出' }))
    await waitFor(() => {
      expect(logoutSession).toHaveBeenCalledWith('csrf-shell-token')
      expect(screen.getByRole('link', { name: '登录' })).toBeInTheDocument()
    })
  })

  it('BroadcastChannel messages carry only event names', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    const received: unknown[] = []
    const channel = new BroadcastChannel(AUTH_BROADCAST_CHANNEL)
    channel.onmessage = (ev) => {
      received.push(ev.data)
    }

    logoutSession.mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderShell()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '退出' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: '退出' }))
    await waitFor(() => {
      expect(received.length).toBeGreaterThanOrEqual(1)
    })
    for (const msg of received) {
      expect(typeof msg).toBe('string')
      expect(['login', 'logout', 'session-invalidated']).toContain(msg)
      expect(JSON.stringify(msg)).not.toContain('csrf')
      expect(JSON.stringify(msg)).not.toContain('shell-user')
    }
    channel.close()
  })

  it('focus event triggers bootstrap revalidation', async () => {
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
    renderShell()
    await waitFor(() => {
      expect(bootstrapSession).toHaveBeenCalledTimes(1)
    })
    bootstrapSession.mockResolvedValue(SESSION)
    await act(async () => {
      window.dispatchEvent(new Event('focus'))
    })
    await waitFor(() => {
      expect(bootstrapSession.mock.calls.length).toBeGreaterThanOrEqual(2)
    })
  })
})
