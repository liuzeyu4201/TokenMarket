import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminApp } from './AdminApp'

const adminSession = vi.fn()
const createDraft = vi.fn()
const diffDraft = vi.fn()
const simulateDraft = vi.fn()
const approveDraft = vi.fn()
const publishDraft = vi.fn()

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return {
    ...actual,
    adminSession: (...args: unknown[]) => adminSession(...args),
    adminLogout: vi.fn(),
    createDraft: (...args: unknown[]) => createDraft(...args),
    diffDraft: (...args: unknown[]) => diffDraft(...args),
    simulateDraft: (...args: unknown[]) => simulateDraft(...args),
    approveDraft: (...args: unknown[]) => approveDraft(...args),
    publishDraft: (...args: unknown[]) => publishDraft(...args),
  }
})

describe('admin publish pipeline', () => {
  beforeEach(() => {
    adminSession.mockResolvedValue({ admin_id: 'a1', role: 'pricing', readonly: false })
    createDraft.mockResolvedValue({ draft_id: 'd1', kind: 'price', status: 'draft' })
    diffDraft.mockResolvedValue({
      changes: [{ path: 'buyer_bps', before: 10000, after: 11000 }],
    })
    simulateDraft.mockResolvedValue({ ok: true, reason: 'ok', active_version: 1 })
    approveDraft.mockResolvedValue({ draft_id: 'd1', status: 'approved' })
    publishDraft.mockResolvedValue({ version: 2 })
  })

  it('shows semantic diff before publish', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/publish']}>
        <Routes>
          <Route path="/admin/*" element={<AdminApp />} />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('admin-publish')).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: '生成差异并仿真' }))
    await waitFor(() => {
      expect(screen.getByTestId('config-diff')).toHaveTextContent('buyer_bps')
    })
    expect(screen.getByTestId('config-sim')).toHaveTextContent('仿真通过')
    expect(publishDraft).not.toHaveBeenCalled()
  })
})
