import { ApiError, apiFetch } from '../client'
import type { ApiEnvelope } from '../../types/auth'
import type { ProtocolName } from './projects'

export interface ProxyKeyPublic {
  key_id: string
  project_id: string | null
  name: string | null
  status: string
  masked_prefix: string
  masked_suffix: string
  protocols: ProtocolName[]
  secret?: string
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

export async function listProjectKeys(projectId: string): Promise<ProxyKeyPublic[]> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ items: ProxyKeyPublic[] }>>(
    `/api/v1/projects/${projectId}/proxy-keys`,
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId).items
}

export async function issueProjectKey(
  projectId: string,
  body: { name?: string; protocols: ProtocolName[]; allowed_models?: string[] },
  csrfToken: string | null,
): Promise<ProxyKeyPublic> {
  const { data, requestId } = await apiFetch<ApiEnvelope<ProxyKeyPublic>>(
    `/api/v1/projects/${projectId}/proxy-keys`,
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify(body),
    },
  )
  return unwrap(data, requestId)
}
