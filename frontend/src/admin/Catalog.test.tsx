import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminApp } from './AdminApp'
import { assertNoSeriousA11y } from '../ui/assertA11y'

const adminSession = vi.fn()
const listOps = vi.fn()
const getOpsItem = vi.fn()
const exportOpsItem = vi.fn()

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return {
    ...actual,
    adminSession: (...args: unknown[]) => adminSession(...args),
    adminLogin: vi.fn(),
    adminLogout: vi.fn(),
    listOpsKinds: vi.fn(async () => ['connection']),
    listOps: (...args: unknown[]) => listOps(...args),
    getOpsItem: (...args: unknown[]) => getOpsItem(...args),
    exportOpsItem: (...args: unknown[]) => exportOpsItem(...args),
  }
})

function renderAdmin(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/*" element={<AdminApp />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('admin catalog', () => {
  beforeEach(() => {
    adminSession.mockReset()
    listOps.mockReset()
    getOpsItem.mockReset()
    exportOpsItem.mockReset()
    adminSession.mockResolvedValue({ admin_id: 'a1', role: 'supply_ops', readonly: false })
    listOps.mockResolvedValue({
      kind: 'connection',
      items: [
        {
          id: 'conn-000000',
          fingerprint: 'abc123fingerprint',
          health: 'healthy',
          freshness: 'live',
          protocol: 'openai',
        },
        {
          id: 'conn-000001',
          fingerprint: 'def456fingerprint',
          health: 'unknown',
          freshness: 'stale',
          protocol: 'anthropic',
        },
      ],
      next_cursor: '50',
      total: 100000,
      freshness: 'live',
    })
    getOpsItem.mockResolvedValue({
      item: {
        id: 'conn-000000',
        fingerprint: 'abc123fingerprint',
        health: 'healthy',
        freshness: 'live',
      },
      version: 1,
      related: [],
      alerts: [],
      audit: [],
      freshness: 'live',
    })
    exportOpsItem.mockResolvedValue({
      id: 'conn-000000',
      fingerprint: 'abc123fingerprint',
      health: 'healthy',
    })
  })

  it('sends anonymous visitors to admin login, not buyer login', async () => {
    adminSession.mockRejectedValue(new Error('unauth'))
    renderAdmin('/admin/ops/connection')
    await waitFor(() => {
      expect(screen.getByTestId('admin-login')).toBeInTheDocument()
    })
    expect(screen.queryByLabelText('手机号')).not.toBeInTheDocument()
    expect(screen.queryByTestId('dashboard-protected')).not.toBeInTheDocument()
  })

  it('paginates connections and never renders secrets or live stale health', async () => {
    const { container } = renderAdmin('/admin/ops/connection')
    await waitFor(() => {
      expect(screen.getByTestId('admin-catalog')).toBeInTheDocument()
    })
    expect(await screen.findByText(/共 100000/)).toBeInTheDocument()
    expect(screen.getByText('下一页')).toBeInTheDocument()
    expect(screen.getByTestId('health-unknown')).toHaveTextContent('未知（过期）')
    expect(container.textContent).not.toMatch(/sk-/)
    expect(container.textContent).not.toMatch(/api_key/)
    expect(container.textContent).not.toMatch(/plaintext/)
    assertNoSeriousA11y(container)
  })
})
