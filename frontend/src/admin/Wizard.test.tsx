import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminApp } from './AdminApp'

const adminSession = vi.fn()
const startWizard = vi.fn()
const confirmWizard = vi.fn()
const cancelWizard = vi.fn()

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return {
    ...actual,
    adminSession: (...args: unknown[]) => adminSession(...args),
    adminLogout: vi.fn(),
    startWizard: (...args: unknown[]) => startWizard(...args),
    confirmWizard: (...args: unknown[]) => confirmWizard(...args),
    cancelWizard: (...args: unknown[]) => cancelWizard(...args),
  }
})

describe('admin high-risk wizard', () => {
  beforeEach(() => {
    adminSession.mockResolvedValue({ admin_id: 'a1', role: 'support', readonly: false })
    startWizard.mockResolvedValue({
      wizard_id: 'w1',
      kind: 'force_logout',
      target: 'sess-1',
      impact: ['目标会话立即失效'],
      status: 'pending',
      request_id: null,
      reason: 'abuse',
      expires_at: '2099-01-01T00:00:00Z',
    })
    cancelWizard.mockResolvedValue({
      wizard_id: 'w1',
      kind: 'force_logout',
      target: 'sess-1',
      impact: ['目标会话立即失效'],
      status: 'cancelled',
      request_id: null,
      reason: 'abuse',
      expires_at: '2099-01-01T00:00:00Z',
    })
  })

  it('cancel leaves no success request id and does not confirm', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/wizards']}>
        <Routes>
          <Route path="/admin/*" element={<AdminApp />} />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('admin-wizard')).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('目标'), 'sess-1')
    await user.type(screen.getByLabelText('原因'), 'abuse')
    await user.click(screen.getByRole('button', { name: '开始' }))
    await waitFor(() => {
      expect(screen.getByTestId('wizard-status')).toHaveTextContent('pending')
    })
    await user.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() => {
      expect(screen.getByTestId('wizard-status')).toHaveTextContent('cancelled')
    })
    expect(confirmWizard).not.toHaveBeenCalled()
    expect(screen.queryByTestId('wizard-request-id')).not.toBeInTheDocument()
  })
})
