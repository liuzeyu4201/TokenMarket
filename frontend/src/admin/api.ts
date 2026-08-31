import { ApiError, apiFetch } from '../api/client'
import type { ApiEnvelope } from '../types/auth'

export type OpsKind =
  'user' | 'session' | 'connection' | 'project' | 'price' | 'route' | 'ledger' | 'alert' | 'audit'

export interface OpsItem {
  id: string
  fingerprint?: string
  health?: string
  freshness?: 'live' | 'stale' | 'unknown'
  protocol?: string
  status?: string
  state?: string
  version?: number
  [key: string]: unknown
}

export interface OpsPage {
  kind: OpsKind
  items: OpsItem[]
  next_cursor: string | null
  total: number
  freshness: string
}

export interface AdminSession {
  admin_id: string
  role: string
  readonly: boolean
}

export interface ConfigDraft {
  draft_id: string
  kind: 'price' | 'route'
  payload: Record<string, unknown>
  status: string
  active_unchanged: boolean
  sim_ok: boolean
  version: number
  base_version: number
  error: string
}

export interface Wizard {
  wizard_id: string
  kind: string
  target: string
  impact: string[]
  status: string
  request_id: string | null
  reason: string
  expires_at: string
}

function unwrap<T>(envelope: ApiEnvelope<T>, requestId: string): T {
  if (envelope.code !== '0' || envelope.data == null) {
    throw new ApiError(envelope.message || '请求失败', 0, envelope, requestId, envelope.code)
  }
  return envelope.data
}

export async function adminLogin(
  login: string,
  password: string,
  mfaCode: string,
): Promise<AdminSession> {
  const { data, requestId } = await apiFetch<ApiEnvelope<AdminSession>>('/admin/v1/sessions', {
    method: 'POST',
    body: JSON.stringify({ login, password, mfa_code: mfaCode }),
  })
  return unwrap(data, requestId)
}

export async function adminSession(): Promise<AdminSession> {
  const { data, requestId } = await apiFetch<ApiEnvelope<AdminSession>>('/admin/v1/session', {
    method: 'GET',
  })
  return unwrap(data, requestId)
}

export async function adminLogout(): Promise<void> {
  await apiFetch<ApiEnvelope<{ logged_out: boolean }>>('/admin/v1/session', { method: 'DELETE' })
}

export async function listOpsKinds(): Promise<OpsKind[]> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ kinds: OpsKind[] }>>('/admin/v1/ops', {
    method: 'GET',
  })
  return unwrap(data, requestId).kinds
}

export async function listOps(
  kind: OpsKind,
  params: { cursor?: string; limit?: number; q?: string } = {},
): Promise<OpsPage> {
  const query = new URLSearchParams()
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.limit) query.set('limit', String(params.limit))
  if (params.q) query.set('q', params.q)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const { data, requestId } = await apiFetch<ApiEnvelope<OpsPage>>(
    `/admin/v1/ops/${kind}${suffix}`,
    {
      method: 'GET',
    },
  )
  return unwrap(data, requestId)
}

export async function getOpsItem(
  kind: OpsKind,
  id: string,
): Promise<{
  item: OpsItem
  freshness: string
  audit: unknown[]
  alerts: unknown[]
  related: unknown[]
  version: number
}> {
  const { data, requestId } = await apiFetch<
    ApiEnvelope<{
      item: OpsItem
      freshness: string
      audit: unknown[]
      alerts: unknown[]
      related: unknown[]
      version: number
    }>
  >(`/admin/v1/ops/${kind}/${id}`, { method: 'GET' })
  return unwrap(data, requestId)
}

export async function exportOpsItem(kind: OpsKind, id: string): Promise<Record<string, unknown>> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Record<string, unknown>>>(
    `/admin/v1/ops/${kind}/${id}/export`,
    { method: 'GET' },
  )
  return unwrap(data, requestId)
}

export async function createDraft(
  kind: 'price' | 'route',
  payload: Record<string, unknown>,
): Promise<ConfigDraft> {
  const { data, requestId } = await apiFetch<ApiEnvelope<ConfigDraft>>('/admin/v1/config', {
    method: 'POST',
    body: JSON.stringify({ kind, payload }),
  })
  return unwrap(data, requestId)
}

export async function diffDraft(
  draftId: string,
): Promise<{ changes: { path: string; before: unknown; after: unknown }[] }> {
  const { data, requestId } = await apiFetch<
    ApiEnvelope<{ changes: { path: string; before: unknown; after: unknown }[] }>
  >(`/admin/v1/config/${draftId}/diff`, { method: 'GET' })
  return unwrap(data, requestId)
}

export async function simulateDraft(
  draftId: string,
): Promise<{ ok: boolean; reason: string; active_version: number }> {
  const { data, requestId } = await apiFetch<
    ApiEnvelope<{ ok: boolean; reason: string; active_version: number }>
  >(`/admin/v1/config/${draftId}/simulate`, { method: 'POST' })
  return unwrap(data, requestId)
}

export async function approveDraft(draftId: string): Promise<ConfigDraft> {
  const { data, requestId } = await apiFetch<ApiEnvelope<ConfigDraft>>(
    `/admin/v1/config/${draftId}/approve`,
    { method: 'POST' },
  )
  return unwrap(data, requestId)
}

export async function publishDraft(draftId: string, reason: string): Promise<{ version: number }> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ version: number }>>(
    `/admin/v1/config/${draftId}/publish`,
    { method: 'POST', body: JSON.stringify({ reason }) },
  )
  return unwrap(data, requestId)
}

export async function startWizard(kind: string, target: string, reason: string): Promise<Wizard> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Wizard>>('/admin/v1/wizards', {
    method: 'POST',
    body: JSON.stringify({ kind, target, reason }),
  })
  return unwrap(data, requestId)
}

export async function confirmWizard(id: string, reason: string): Promise<Wizard> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Wizard>>(
    `/admin/v1/wizards/${id}/confirm`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
    },
  )
  return unwrap(data, requestId)
}

export async function cancelWizard(id: string): Promise<Wizard> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Wizard>>(
    `/admin/v1/wizards/${id}/cancel`,
    {
      method: 'POST',
    },
  )
  return unwrap(data, requestId)
}
