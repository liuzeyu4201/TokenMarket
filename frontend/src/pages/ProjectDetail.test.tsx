import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import type { SessionData } from '../types/auth'
import { ProjectDetail } from './ProjectDetail'
import { assertNoSeriousA11y } from '../ui/assertA11y'

const bootstrapSession = vi.fn()
const getProject = vi.fn()

vi.mock('../api/v1/phoneAuth', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/phoneAuth')>('../api/v1/phoneAuth')
  return {
    ...actual,
    bootstrapSession: (...args: unknown[]) => bootstrapSession(...args),
    logoutSession: vi.fn(),
  }
})

vi.mock('../api/v1/projects', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/projects')>('../api/v1/projects')
  return {
    ...actual,
    getProject: (...args: unknown[]) => getProject(...args),
  }
})

const SESSION: SessionData = {
  user_id: 'buyer-1',
  nickname: '买家',
  phone_masked: '*******0000',
  role: 'buyer',
  workspace: 'buyer',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: 'csrf-detail',
}

describe('ProjectDetail', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    getProject.mockReset()
  })

  it('shows immutable mode copy', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    getProject.mockResolvedValue({
      project_id: 'p1',
      owner_account_id: 'buyer-1',
      display_name: '专享项目',
      mode: 'dedicated',
      status: 'draft',
      enabled_protocols: ['openai'],
      protocols: [{ protocol: 'openai', enabled: true, enabled_at: null, disabled_at: null }],
      created_at: '2026-08-31T00:00:00.000Z',
    })
    const { container } = render(
      <MemoryRouter initialEntries={['/projects/p1']}>
        <AuthProvider>
          <Routes>
            <Route path="/projects/:projectId" element={<ProjectDetail />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('project-mode')).toHaveTextContent('专享')
    })
    expect(screen.getByText(/不会回退共享池/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: '模式' })).not.toBeInTheDocument()
    assertNoSeriousA11y(container)
  })
})
