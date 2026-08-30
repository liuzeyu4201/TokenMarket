import { ApiError, apiFetch } from '../client'
import type { ApiEnvelope } from '../../types/auth'

export type ProjectMode = 'shared' | 'dedicated'
export type ProtocolName = 'openai' | 'anthropic' | 'vertex'
export type ProjectStatus = 'draft' | 'active' | 'suspended' | 'archived'

export interface ProtocolState {
  protocol: ProtocolName
  enabled: boolean
  enabled_at: string | null
  disabled_at: string | null
}

export interface Project {
  project_id: string
  owner_account_id: string
  display_name: string
  mode: ProjectMode
  status: ProjectStatus
  enabled_protocols: ProtocolName[]
  protocols: ProtocolState[]
  created_at: string
  updated_at?: string
  archived_at?: string | null
}

export interface Admission {
  allows_new_proxy: boolean
  project_id: string
  status: ProjectStatus
}

export const MODE_CONSEQUENCE: Record<ProjectMode, string> = {
  shared: '共享模式：仅允许目录中的无状态调用；创建后不能改为专享。',
  dedicated:
    '专享模式：只使用本 Project 绑定的连接，故障时失败关闭，不会回退共享池；创建后不能改为共享。',
}

function csrfHeaders(token: string | null): Record<string, string> {
  return token ? { 'X-CSRF-Token': token } : {}
}

function unwrap<T>(envelope: ApiEnvelope<T>, requestId: string): T {
  if (envelope.code !== '0' || envelope.data == null) {
    throw new ApiError(envelope.message || '请求失败', 0, envelope, requestId, envelope.code)
  }
  return envelope.data
}

export async function listProjects(): Promise<Project[]> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ items: Project[] }>>(
    '/api/v1/projects',
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId).items
}

export async function getProject(projectId: string): Promise<Project> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Project>>(
    `/api/v1/projects/${projectId}`,
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId)
}

export async function createProject(
  body: {
    display_name: string
    mode: ProjectMode
    enabled_protocols: ProtocolName[]
  },
  csrfToken: string | null,
): Promise<Project> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Project>>('/api/v1/projects', {
    method: 'POST',
    sameOriginAuth: true,
    headers: csrfHeaders(csrfToken),
    body: JSON.stringify(body),
  })
  return unwrap(data, requestId)
}

export async function renameProject(
  projectId: string,
  displayName: string,
  csrfToken: string | null,
): Promise<Project> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Project>>(
    `/api/v1/projects/${projectId}`,
    {
      method: 'PATCH',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify({ display_name: displayName }),
    },
  )
  return unwrap(data, requestId)
}

export async function transitionProject(
  projectId: string,
  action: 'activate' | 'suspend' | 'archive',
  csrfToken: string | null,
): Promise<Project> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Project>>(
    `/api/v1/projects/${projectId}/${action}`,
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify({}),
    },
  )
  return unwrap(data, requestId)
}

export async function deleteProject(projectId: string, csrfToken: string | null): Promise<void> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ deleted?: boolean }>>(
    `/api/v1/projects/${projectId}`,
    {
      method: 'DELETE',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
    },
  )
  unwrap(data, requestId)
}

export async function setProtocolEnabled(
  projectId: string,
  protocol: ProtocolName,
  enabled: boolean,
  csrfToken: string | null,
): Promise<Project> {
  const verb = enabled ? 'enable' : 'disable'
  const { data, requestId } = await apiFetch<ApiEnvelope<Project>>(
    `/api/v1/projects/${projectId}/protocols/${protocol}/${verb}`,
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify({}),
    },
  )
  return unwrap(data, requestId)
}
