import { ApiError, apiFetch } from '../client'
import type { ApiEnvelope } from '../../types/auth'

export interface QuotaOverview {
  available: number
  reserved: number
  settled: number
  unresolved: number
  warning?: string | null
  note?: string
}

export interface GuideStep {
  id: string
  title: string
  done: boolean
}

export interface Guide {
  checklist: GuideStep[]
  samples: Record<string, { curl: string; sdk: string; auth_header: string; path: string }>
  disclaimer: string
}

export interface UsageItem {
  request_id: string
  key_id: string
  status: string
  amount_minor: number
  reason?: string | null
}

function unwrap<T>(envelope: ApiEnvelope<T>, requestId: string): T {
  if (envelope.code !== '0' || envelope.data == null) {
    throw new ApiError(envelope.message || '请求失败', 0, envelope, requestId, envelope.code)
  }
  return envelope.data
}

export async function getProjectBudget(projectId: string): Promise<QuotaOverview> {
  const { data, requestId } = await apiFetch<ApiEnvelope<QuotaOverview>>(
    `/api/v1/projects/${projectId}/budget`,
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId)
}

export async function getProjectGuide(projectId: string): Promise<Guide> {
  const { data, requestId } = await apiFetch<ApiEnvelope<Guide>>(
    `/api/v1/projects/${projectId}/guide`,
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId)
}

export async function listProjectUsage(projectId: string): Promise<UsageItem[]> {
  const { data, requestId } = await apiFetch<ApiEnvelope<{ items: UsageItem[] }>>(
    `/api/v1/projects/${projectId}/usage`,
    { method: 'GET', sameOriginAuth: true },
  )
  return unwrap(data, requestId).items
}
