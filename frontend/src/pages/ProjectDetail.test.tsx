import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import type { SessionData } from '../types/auth'
import { ProjectDetail } from './ProjectDetail'
import { assertNoSeriousA11y } from '../ui/assertA11y'

const bootstrapSession = vi.fn()
const getProject = vi.fn()
const listBindings = vi.fn()
const createBinding = vi.fn()
const publishBinding = vi.fn()
const getSdkHint = vi.fn()
const previewReplace = vi.fn()
const replaceBinding = vi.fn()
const listProjectKeys = vi.fn()
const issueProjectKey = vi.fn()

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

vi.mock('../api/v1/proxyKeys', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/proxyKeys')>('../api/v1/proxyKeys')
  return {
    ...actual,
    listProjectKeys: (...args: unknown[]) => listProjectKeys(...args),
    issueProjectKey: (...args: unknown[]) => issueProjectKey(...args),
  }
})

vi.mock('../api/v1/bindings', async () => {
  const actual = await vi.importActual<typeof import('../api/v1/bindings')>('../api/v1/bindings')
  return {
    ...actual,
    listBindings: (...args: unknown[]) => listBindings(...args),
    createBinding: (...args: unknown[]) => createBinding(...args),
    publishBinding: (...args: unknown[]) => publishBinding(...args),
    getSdkHint: (...args: unknown[]) => getSdkHint(...args),
    previewReplace: (...args: unknown[]) => previewReplace(...args),
    replaceBinding: (...args: unknown[]) => replaceBinding(...args),
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
    listBindings.mockReset()
    listBindings.mockResolvedValue([])
    createBinding.mockReset()
    publishBinding.mockReset()
    getSdkHint.mockReset()
    previewReplace.mockReset()
    previewReplace.mockResolvedValue({
      old_connection_id: 'c-old',
      non_migrating: ['files', 'batches', 'caches', 'fine_tuning', 'operations'],
      migrates: false,
    })
    replaceBinding.mockReset()
    listProjectKeys.mockReset()
    listProjectKeys.mockResolvedValue([])
    issueProjectKey.mockReset()
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
    expect(screen.getByTestId('binding-form')).toBeInTheDocument()
    expect(screen.getByTestId('replace-impact')).toHaveTextContent('files')
    expect(screen.getByTestId('replace-impact')).toHaveTextContent('不会迁移')
    assertNoSeriousA11y(container)
  })

  it('shows sdk hint without secrets after publishing a binding', async () => {
    bootstrapSession.mockResolvedValue({ ...SESSION, role: 'buyer', workspace: 'buyer' })
    getProject.mockResolvedValue({
      project_id: 'p1',
      owner_account_id: 'buyer-1',
      display_name: '共享项目',
      mode: 'shared',
      status: 'active',
      enabled_protocols: ['openai'],
      protocols: [{ protocol: 'openai', enabled: true, enabled_at: null, disabled_at: null }],
      created_at: '2026-08-31T00:00:00.000Z',
    })
    createBinding.mockResolvedValue({
      binding_id: 'b1',
      project_id: 'p1',
      protocol: 'openai',
      supply_mode: 'shared',
      status: 'draft',
      version: 0,
      allowed_models: ['gpt-test'],
      allowed_providers: ['openai'],
    })
    publishBinding.mockResolvedValue({
      binding_id: 'b1',
      project_id: 'p1',
      protocol: 'openai',
      supply_mode: 'shared',
      status: 'active',
      version: 1,
      allowed_models: ['gpt-test'],
      allowed_providers: ['openai'],
    })
    getSdkHint.mockResolvedValue({
      protocol: 'openai',
      base_url: '/v1',
      auth_scheme: 'bearer',
      protocol_version: 'v1',
    })
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/projects/p1']}>
        <AuthProvider>
          <Routes>
            <Route path="/projects/:projectId" element={<ProjectDetail />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '发布 Binding' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: '发布 Binding' }))
    await waitFor(() => {
      expect(screen.getByTestId('sdk-hint')).toHaveTextContent('/v1')
    })
    expect(screen.getByTestId('sdk-hint').textContent?.toLowerCase()).not.toMatch(/secret|api_key/)
  })
})
