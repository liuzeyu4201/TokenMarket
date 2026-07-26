/**
 * Privacy: CSRF stays in memory; BroadcastChannel carries event names only (T079).
 */

import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AUTH_BROADCAST_CHANNEL,
  AuthProvider,
  useAuth,
} from './AuthContext'
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

const CSRF = 'tm_csrf_sentinel_privacy_only_memory'
const SESSION: SessionData = {
  user_id: 'privacy-user-id',
  nickname: '隐私用户',
  phone_masked: '*******0000',
  role: 'buyer',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: CSRF,
}

function Probe() {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="csrf">{auth.getCsrfToken() ?? ''}</span>
      <button type="button" onClick={() => auth.establishSession(SESSION)}>
        establish
      </button>
      <button type="button" onClick={() => void auth.logout()}>
        logout
      </button>
    </div>
  )
}

describe('AuthContext privacy', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    logoutSession.mockReset()
    localStorage.clear()
    sessionStorage.clear()
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
  })

  it('never writes CSRF or session id into Web Storage', async () => {
    const user = userEvent.setup()
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    })
    await user.click(screen.getByRole('button', { name: 'establish' }))
    expect(screen.getByTestId('csrf')).toHaveTextContent(CSRF)

    const storageBlob = [
      ...Object.keys(localStorage),
      ...Object.keys(sessionStorage),
      ...Object.keys(localStorage).map((k) => localStorage.getItem(k) ?? ''),
      ...Object.keys(sessionStorage).map((k) => sessionStorage.getItem(k) ?? ''),
    ].join('\n')
    expect(storageBlob).not.toContain(CSRF)
    expect(storageBlob).not.toContain('privacy-user-id')
    expect(storageBlob).not.toContain('__Host-tokenmarket_session')

    // DOM probe may show CSRF only via explicit test hook — real UI must not.
    // getCsrfToken is for API clients, not display; status node must not include it.
    expect(screen.getByTestId('status').textContent).not.toContain(CSRF)
  })

  it('BroadcastChannel publishes only safe event name strings', async () => {
    const messages: unknown[] = []
    const listener = new BroadcastChannel(AUTH_BROADCAST_CHANNEL)
    listener.onmessage = (ev) => {
      messages.push(ev.data)
    }

    bootstrapSession.mockResolvedValue(SESSION)
    logoutSession.mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
    // establish via bootstrap may or may not broadcast login; logout must.
    await user.click(screen.getByRole('button', { name: 'logout' }))
    await waitFor(() => {
      expect(messages.some((m) => m === 'logout')).toBe(true)
    })

    for (const msg of messages) {
      expect(typeof msg).toBe('string')
      expect(['login', 'logout', 'session-invalidated']).toContain(msg)
      const serialized = JSON.stringify(msg)
      expect(serialized).not.toContain(CSRF)
      expect(serialized).not.toContain('privacy-user-id')
      expect(serialized).not.toContain('phone')
      expect(serialized).not.toContain('token')
    }
    listener.close()
  })

  it('login broadcast is name-only when establishSession is used', async () => {
    const messages: unknown[] = []
    const listener = new BroadcastChannel(AUTH_BROADCAST_CHANNEL)
    listener.onmessage = (ev) => {
      messages.push(ev.data)
    }
    const user = userEvent.setup()
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    })
    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'establish' }))
    })
    await waitFor(() => {
      expect(messages).toContain('login')
    })
    expect(messages.every((m) => m === 'login' || m === 'logout' || m === 'session-invalidated')).toBe(
      true,
    )
    listener.close()
  })
})
