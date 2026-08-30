import { ApiError, apiFetch } from '../client'
import type { ApiEnvelope } from '../../types/auth'

export interface WorkbenchCard {
  connection_id: string
  provider: string
  supply_mode: string
  lifecycle_state: string
  health_state: string
  health_reason?: string | null
  declared_capacity: number | null
  admits_new: boolean
  quote: { seq: number; multiplier_bps: number; rate_version: string } | null
  quote_history_len: number
  bounds: {
    seller_quote_min_bps: number
    seller_quote_max_bps: number
    rate_version: string
  }
  earnings: {
    settled_minor: number
    unresolved_count: number
    unresolved_reasons: string[]
    ledger_ready: boolean
  }
  route_summary: { admits_new: boolean; reason: string | null }
}

function unwrap<T>(envelope: ApiEnvelope<T>, requestId: string): T {
  if (envelope.code !== '0' || envelope.data == null) {
    throw new ApiError(envelope.message || '请求失败', 0, envelope, requestId, envelope.code)
  }
  return envelope.data
}

function csrfHeaders(token: string | null): Record<string, string> {
  return token ? { 'X-CSRF-Token': token } : {}
}

export async function listWorkbench(): Promise<WorkbenchCard[]> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ items: WorkbenchCard[] }>>(
    '/api/v1/seller/workbench',
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId).items
}

export async function submitQuote(
  connectionId: string,
  multiplierBps: number,
  csrfToken: string | null,
): Promise<{ seq: number; multiplier_bps: number }> {
  const { data, requestId } = await apiFetch<
    ApiEnvelope<{ seq: number; multiplier_bps: number; rate_version: string }>
  >(`/api/v1/seller/workbench/${connectionId}/quotes`, {
    method: 'POST',
    sameOriginAuth: true,
    headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) },
    body: JSON.stringify({ multiplier_bps: multiplierBps }),
  })
  return unwrap(data, requestId)
}

export async function setCapacity(
  connectionId: string,
  declaredCapacity: number,
  csrfToken: string | null,
): Promise<{ declared_capacity: number }> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ declared_capacity: number }>>(
    `/api/v1/seller/workbench/${connectionId}/capacity`,
    {
      method: 'POST',
      sameOriginAuth: true,
      headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) },
      body: JSON.stringify({ declared_capacity: declaredCapacity }),
    },
  )
  return unwrap(data, requestId)
}
