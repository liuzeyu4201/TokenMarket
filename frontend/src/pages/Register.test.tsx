import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { PhoneAuthClientError } from '../api/v1/phoneAuth'
import { Register } from './Register'

const bootstrapSession = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    requestChallenge: vi.fn(),
    createSession: vi.fn(),
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: vi.fn(),
  }
})

describe('Register page', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    bootstrapSession.mockRejectedValue(
      new PhoneAuthClientError('未登录', 'UNAUTHENTICATED', 'clear_session', 401),
    )
  })

  it('uses the unified phone verification entry', async () => {
    render(
      <MemoryRouter initialEntries={['/register']}>
        <AuthProvider>
          <Routes>
            <Route path="/register" element={<Register />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByLabelText('手机号')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('验证码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '获取验证码' })).toBeInTheDocument()
  })
})
