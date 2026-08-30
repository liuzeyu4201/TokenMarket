/**
 * Auth / registration types. Phone-login shapes align with
 * `frontend/src/api/generated/phoneAuth.ts` (phone-auth-session/v1).
 */

export type UserRole = 'buyer' | 'seller' | 'both'

export interface RegisterRequest {
  phone: string
  nickname: string
  role: UserRole
}

export interface RegisterSuccessData {
  user_id: string
  role: UserRole
  status: 'active'
  created_at: string
  phone_masked?: string
}

export interface ApiEnvelope<T> {
  code: string
  message: string
  data: T | null
  request_id: string
  timestamp: string
}

export interface FieldErrors {
  errors?: Record<string, string[]>
}

/** Opaque challenge handle returned on neutral 202 accept. */
export interface ChallengeAcceptedData {
  challenge_id: string
  phone_masked: string
  expires_at: string
  resend_available_at: string
}

export interface RequestChallengeRequest {
  phone: string
}

export interface CreateSessionRequest {
  challenge_id: string
  /** Six ASCII decimal digits; leading zeros are significant. */
  code: string
}

/**
 * Full session payload from create/bootstrap (includes CSRF).
 * Prefer `SessionSummary` for UI; keep CSRF only in AuthContext memory.
 */
export interface SessionData {
  user_id: string
  nickname: string
  phone_masked: string
  role: UserRole
  expires_at: string
  /** Session-bound CSRF proof — never persist or render. */
  csrf_token: string
}

/** Desensitized session summary for UI (no CSRF, no credentials). */
export interface SessionSummary {
  userId: string
  nickname: string
  phoneMasked: string
  role: UserRole
  expiresAt: string
}

export type AuthStatus = 'checking' | 'authenticated' | 'anonymous' | 'unavailable'

/** Client action derived from stable business `code` (not HTTP status alone). */
export type PhoneAuthAction =
  | 'fix_fields'
  | 'retry_code'
  | 'request_new_code'
  | 'wait_retry'
  | 'retry_later'
  | 'new_idempotency_key'
  | 'security_block'
  | 'clear_session'
  | 'complete_profile'
  | 'unknown'

export type VerificationFailureAction = 'retry_code' | 'request_new_code'

export function toSessionSummary(data: SessionData): SessionSummary {
  return {
    userId: data.user_id,
    nickname: data.nickname,
    phoneMasked: data.phone_masked,
    role: data.role,
    expiresAt: data.expires_at,
  }
}
