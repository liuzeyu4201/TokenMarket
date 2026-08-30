import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import type { SessionData } from '../types/auth'
import { Supply } from './Supply'
import { assertNoSeriousA11y } from '../ui/assertA11y'
import type { WorkbenchCard } from '../api/v1/workbench'

const bootstrapSession = vi.fn()
const listWorkbench = vi.fn()
const submitQuote = vi.fn()
const setCapacity = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: vi.fn(),
  }
})

vi.mock('../api/v1/workbench', () => ({
  listWorkbench: (...args: unknown[]) => listWorkbench(...args),
  submitQuote: (...args: unknown[]) => submitQuote(...args),
  setCapacity: (...args: unknown[]) => setCapacity(...args),
}))

const SESSION: SessionData = {
  user_id: 'seller-1',
  nickname: '卖家',
  phone_masked: '*******0000',
  role: 'both',
  workspace: 'seller',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: 'csrf-supply',
}

const CARD: WorkbenchCard = {
  connection_id: 'c1',
  provider: 'openai',
  supply_mode: 'shared',
  lifecycle_state: 'listed',
  health_state: 'healthy',
  declared_capacity: 5,
  admits_new: true,
  quote: { seq: 1, multiplier_bps: 10000, rate_version: 'rv-published' },
  quote_history_len: 1,
  bounds: {
    seller_quote_min_bps: 8000,
    seller_quote_max_bps: 11000,
    rate_version: 'rv-published',
  },
  earnings: {
    settled_minor: 10,
    unresolved_count: 1,
    unresolved_reasons: ['parse_failed'],
    ledger_ready: true,
  },
  route_summary: { admits_new: true, reason: null },
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/supply']}>
      <AuthProvider>
        <Routes>
          <Route path="/supply" element={<Supply />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Supply workbench', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    listWorkbench.mockReset()
    submitQuote.mockReset()
    setCapacity.mockReset()
    listWorkbench.mockResolvedValue([CARD])
    submitQuote.mockResolvedValue({ seq: 2, multiplier_bps: 10100 })
    setCapacity.mockResolvedValue({ declared_capacity: 0 })
  })

  it('lists quote bounds without buyer multiplier', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    const { container } = renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('supply-page')).toBeInTheDocument()
    })
    expect(screen.getByText(/10000 bps/)).toBeInTheDocument()
    expect(screen.getByText('parse_failed', { exact: false })).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/buyer_multiplier/i)
    assertNoSeriousA11y(container)
  })

  it('submits quote with csrf', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByLabelText('报价倍率 bps')).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('报价倍率 bps'), '10100')
    await user.click(screen.getByRole('button', { name: '提交报价' }))
    await waitFor(() => {
      expect(submitQuote).toHaveBeenCalled()
    })
    expect(submitQuote.mock.calls[0][2]).toBe('csrf-supply')
  })

  it('hides workbench from buyer workspace', async () => {
    bootstrapSession.mockResolvedValue({ ...SESSION, workspace: 'buyer' })
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('supply-forbidden')).toBeInTheDocument()
    })
  })
})
