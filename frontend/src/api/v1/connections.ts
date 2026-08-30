import { ApiError, apiFetch } from '../client'
import type { ApiEnvelope } from '../../types/auth'
import type { ProjectMode, ProtocolName } from './projects'

export interface ProviderConnection {
  connection_id: string
  seller_account_id: string
  provider: ProtocolName
  supply_mode: ProjectMode
  region?: string | null
  purpose?: string | null
  base_url?: string | null
  project_number?: string | null
  location?: string | null
  credential_fingerprint: string
  credential_version: number
  status: 'active' | 'deleted'
  health_state?: 'unknown' | 'healthy' | 'degraded' | 'unhealthy'
  health_reason?: string | null
  capability_version?: number
}

export interface CreateConnectionBody {
  provider: ProtocolName
  supply_mode: ProjectMode
  credential: {
    secret: string
    project_number?: string
    location?: string
  }
  base_url?: string
  region?: string
  purpose?: string
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

export async function listConnections(): Promise<ProviderConnection[]> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ items: ProviderConnection[] }>>(
    '/api/v1/provider-connections',
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId).items
}

export async function createConnection(
  body: CreateConnectionBody,
  csrfToken: string | null,
): Promise<ProviderConnection> {
  const { data, requestId } = await apiFetch<ApiEnvelope<ProviderConnection>>(
    '/api/v1/provider-connections',
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify(body),
    },
  )
  return unwrap(data, requestId)
}

export async function replaceConnectionCredential(
  connectionId: string,
  body: { secret: string; expected_version: number },
  csrfToken: string | null,
): Promise<ProviderConnection> {
  const { data, requestId } = await apiFetch<ApiEnvelope<ProviderConnection>>(
    `/api/v1/provider-connections/${connectionId}/credential`,
    {
      method: 'PUT',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
      body: JSON.stringify({
        credential: { secret: body.secret },
        expected_version: body.expected_version,
      }),
    },
  )
  return unwrap(data, requestId)
}

export async function verifyConnection(
  connectionId: string,
  csrfToken: string | null,
): Promise<ProviderConnection> {
  const { data, requestId } = await apiFetch<ApiEnvelope<ProviderConnection>>(
    `/api/v1/provider-connections/${connectionId}/verify`,
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
    },
  )
  return unwrap(data, requestId)
}

export async function deleteConnection(
  connectionId: string,
  csrfToken: string | null,
): Promise<void> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ status: string }>>(
    `/api/v1/provider-connections/${connectionId}`,
    {
      method: 'DELETE',
      sameOriginAuth: true,
      headers: csrfHeaders(csrfToken),
    },
  )
  unwrap(data, requestId)
}
