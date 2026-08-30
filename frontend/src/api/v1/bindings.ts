import { ApiError, apiFetch } from '../client'
import type { ApiEnvelope } from '../../types/auth'
import type { ProjectMode, ProtocolName } from './projects'

export type BindingStatus = 'draft' | 'validated' | 'active' | 'inactive' | 'degraded'

export interface Binding {
  binding_id: string
  project_id: string
  protocol: ProtocolName
  supply_mode: ProjectMode
  status: BindingStatus
  version: number
  allowed_models: string[]
  allowed_providers: string[]
  connection_id?: string | null
  draining_connection_id?: string | null
}

export interface ReplacePreview {
  old_connection_id: string | null
  non_migrating: string[]
  migrates: false
}

export interface SdkHint {
  protocol: ProtocolName
  base_url: string
  auth_scheme: string
  protocol_version: string
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

export async function listBindings(projectId: string): Promise<Binding[]> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ items: Binding[] }>>(
    `/api/v1/projects/${projectId}/bindings`,
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId).items
}

export async function createBinding(
  projectId: string,
  body: {
    protocol: ProtocolName
    supply_mode: ProjectMode
    allowed_models?: string[]
    connection_id?: string
  },
  csrfToken: string | null,
): Promise<Binding> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Binding>>(
    `/api/v1/projects/${projectId}/bindings`,
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify(body),
    },
  )
  return unwrap(data, requestId)
}

export async function publishBinding(
  projectId: string,
  bindingId: string,
  csrfToken: string | null,
): Promise<Binding> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Binding>>(
    `/api/v1/projects/${projectId}/bindings/${bindingId}/publish`,
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify({}),
    },
  )
  return unwrap(data, requestId)
}

export async function previewReplace(
  projectId: string,
  bindingId: string,
): Promise<ReplacePreview> {
  const { data, requestId } = await apiFetch<ApiEnvelope<ReplacePreview>>(
    `/api/v1/projects/${projectId}/bindings/${bindingId}/replace-preview`,
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId)
}

export async function replaceBinding(
  projectId: string,
  bindingId: string,
  body: {
    new_connection_id: string
    buyer_confirmed: boolean
    reason: string
    step_up: boolean
  },
  csrfToken: string | null,
): Promise<Binding> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Binding>>(
    `/api/v1/projects/${projectId}/bindings/${bindingId}/replace`,
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify(body),
    },
  )
  return unwrap(data, requestId)
}

export async function getSdkHint(projectId: string, bindingId: string): Promise<SdkHint> {
  const { data, requestId } = await apiFetch<ApiEnvelope<SdkHint>>(
    `/api/v1/projects/${projectId}/bindings/${bindingId}/sdk-hint`,
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId)
}
