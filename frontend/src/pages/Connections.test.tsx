import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import type { SessionData } from '../types/auth'
import { Connections } from './Connections'
import { assertNoSeriousA11y } from '../ui/assertA11y'

const bootstrapSession = vi.fn()
const listConnections = vi.fn()
const createConnection = vi.fn()
const replaceConnectionCredential = vi.fn()
const deleteConnection = vi.fn()
const verifyConnection = vi.fn()
const lifecycleAction = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: vi.fn(),
  }
})

vi.mock('../api/v1/connections', async () => {
  const actual =
    await vi.importActual<typeof import('../api/v1/connections')>('../api/v1/connections')
  return {
    ...actual,
    listConnections: (...args: unknown[]) => listConnections(...args),
    createConnection: (...args: unknown[]) => createConnection(...args),
    replaceConnectionCredential: (...args: unknown[]) => replaceConnectionCredential(...args),
    deleteConnection: (...args: unknown[]) => deleteConnection(...args),
    verifyConnection: (...args: unknown[]) => verifyConnection(...args),
    lifecycleAction: (...args: unknown[]) => lifecycleAction(...args),
  }
})

const SESSION: SessionData = {
  user_id: 'seller-1',
  nickname: '卖家',
  phone_masked: '*******0000',
  role: 'both',
  workspace: 'seller',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: 'csrf-connections',
}

const ROW = {
  connection_id: 'c1',
  seller_account_id: 'seller-1',
  provider: 'openai' as const,
  supply_mode: 'shared' as const,
  credential_fingerprint: 'abc123fingerprint',
  credential_version: 1,
  status: 'active' as const,
  health_state: 'healthy' as const,
  lifecycle_state: 'listed' as const,
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/connections']}>
      <AuthProvider>
        <Routes>
          <Route path="/connections" element={<Connections />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Connections page', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    listConnections.mockReset()
    createConnection.mockReset()
    replaceConnectionCredential.mockReset()
    deleteConnection.mockReset()
    verifyConnection.mockReset()
    verifyConnection.mockResolvedValue({ ...ROW, health_state: 'healthy' })
    lifecycleAction.mockReset()
    lifecycleAction.mockResolvedValue({ ...ROW, lifecycle_state: 'paused' })
    listConnections.mockResolvedValue([])
    createConnection.mockResolvedValue(ROW)
  })

  it('shows password credential form and does not echo secret', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    const user = userEvent.setup()
    const { container } = renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('connections-page')).toBeInTheDocument()
    })
    const secret = screen.getByLabelText('凭据')
    expect(secret).toHaveAttribute('type', 'password')
    await user.type(secret, 'sk-never-show-this')
    await user.click(screen.getByRole('button', { name: '创建连接' }))
    await waitFor(() => {
      expect(createConnection).toHaveBeenCalled()
    })
    const [body, csrf] = createConnection.mock.calls[0] as [
      { credential: { secret: string } },
      string,
    ]
    expect(body.credential.secret).toBe('sk-never-show-this')
    expect(csrf).toBe('csrf-connections')
    expect(secret).toHaveValue('')
    expect(screen.queryByDisplayValue('sk-never-show-this')).not.toBeInTheDocument()
    assertNoSeriousA11y(container)
  })

  it('lists fingerprint after create and never renders secret from API', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    listConnections.mockResolvedValueOnce([]).mockResolvedValue([ROW])
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('connection-create-form')).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('凭据'), 'sk-once')
    await user.click(screen.getByRole('button', { name: '创建连接' }))
    await waitFor(() => {
      expect(screen.getByTestId('connection-fingerprint')).toHaveTextContent('abc123fingerprint')
    })
    expect(screen.queryByText('sk-once')).not.toBeInTheDocument()
    expect(screen.queryByText('sk-live')).not.toBeInTheDocument()
  })

  it('shows health and re-verify without echoing secret', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    listConnections.mockResolvedValue([{ ...ROW, health_state: 'unhealthy' }])
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('connection-health')).toHaveTextContent('不健康')
    })
    await user.click(screen.getByRole('button', { name: '立即复验' }))
    await waitFor(() => {
      expect(verifyConnection).toHaveBeenCalled()
    })
    const [, csrf] = verifyConnection.mock.calls[0] as [string, string]
    expect(csrf).toBe('csrf-connections')
    expect(screen.queryByText('sk-never-show-this')).not.toBeInTheDocument()
  })

  it('pauses a listed connection', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    listConnections.mockResolvedValue([{ ...ROW, lifecycle_state: 'listed' }])
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('connection-lifecycle')).toHaveTextContent('已上架')
    })
    await user.click(screen.getByRole('button', { name: '暂停' }))
    await waitFor(() => {
      expect(lifecycleAction).toHaveBeenCalled()
    })
    expect(lifecycleAction.mock.calls[0][1]).toBe('pause')
  })

  it('hides create for buyer workspace', async () => {
    bootstrapSession.mockResolvedValue({ ...SESSION, workspace: 'buyer' })
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('connections-forbidden')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: '创建连接' })).not.toBeInTheDocument()
    expect(listConnections).not.toHaveBeenCalled()
  })
})
