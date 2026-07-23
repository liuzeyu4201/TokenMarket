import { apiFetch } from '../client'
import type { ApiEnvelope, RegisterRequest, RegisterSuccessData } from '../../types/auth'

/** Register user — no automatic retry (caller may retry with same Idempotency-Key). */
export async function registerUser(
  body: RegisterRequest,
  idempotencyKey: string,
): Promise<ApiEnvelope<RegisterSuccessData>> {
  const { data } = await apiFetch<ApiEnvelope<RegisterSuccessData>>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(body),
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  })
  return data
}
