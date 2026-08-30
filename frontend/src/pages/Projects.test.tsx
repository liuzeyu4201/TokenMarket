import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import type { SessionData } from '../types/auth'
import { Projects } from './Projects'
import { assertNoSeriousA11y } from '../ui/assertA11y'

const bootstrapSession = vi.fn()
const listProjects = vi.fn()
const createProject = vi.fn()

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
    listProjects: (...args: unknown[]) => listProjects(...args),
    createProject: (...args: unknown[]) => createProject(...args),
  }
})

const SESSION: SessionData = {
  user_id: 'buyer-1',
  nickname: '买家',
  phone_masked: '*******0000',
  role: 'both',
  workspace: 'buyer',
  expires_at: '2099-01-01T00:00:00.000Z',
  csrf_token: 'csrf-projects',
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects']}>
      <AuthProvider>
        <Routes>
          <Route path="/projects" element={<Projects />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Projects page', () => {
  beforeEach(() => {
    bootstrapSession.mockReset()
    listProjects.mockReset()
    createProject.mockReset()
    listProjects.mockResolvedValue([])
    createProject.mockResolvedValue({
      project_id: 'p1',
      owner_account_id: 'buyer-1',
      display_name: 'Demo',
      mode: 'shared',
      status: 'draft',
      enabled_protocols: ['openai'],
      protocols: [{ protocol: 'openai', enabled: true, enabled_at: null, disabled_at: null }],
      created_at: '2026-08-31T00:00:00.000Z',
    })
  })

  it('shows create form with mode consequences for buyer workspace', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    const { container } = renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('projects-page')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('显示名称')).toBeInTheDocument()
    expect(screen.getByLabelText('模式')).toBeInTheDocument()
    expect(screen.getByText(/共享模式/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建 Project' })).toBeDisabled()
    assertNoSeriousA11y(container)
  })

  it('creates a project with csrf and refreshes the list', async () => {
    bootstrapSession.mockResolvedValue(SESSION)
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('project-create-form')).toBeInTheDocument()
    })
    await user.type(screen.getByLabelText('显示名称'), 'Demo')
    await user.click(screen.getByRole('button', { name: '创建 Project' }))
    await waitFor(() => {
      expect(createProject).toHaveBeenCalled()
    })
    const [, csrf] = createProject.mock.calls[0] as unknown[]
    expect(csrf).toBe('csrf-projects')
    expect(listProjects.mock.calls.length).toBeGreaterThan(1)
  })

  it('hides create for seller workspace', async () => {
    bootstrapSession.mockResolvedValue({ ...SESSION, workspace: 'seller' })
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('projects-forbidden')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: '创建 Project' })).not.toBeInTheDocument()
  })
})
