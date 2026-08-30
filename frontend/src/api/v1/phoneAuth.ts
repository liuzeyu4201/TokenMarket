/**
 * Typed facade over phone-auth-session/v1 endpoints.
 * Consumes generated OpenAPI types; maps stable business codes to actionable errors.
 */

import { ApiError, apiFetch } from '../client'
import type { components } from '../generated/phoneAuth'
import type {
  ApiEnvelope,
  ChallengeAcceptedData,
  CreateSessionRequest,
  PhoneAuthAction,
  RequestChallengeRequest,
  SessionData,
  VerificationFailureAction,
} from '../../types/auth'

type ChallengeAcceptedEnvelope = components['schemas']['ChallengeAcceptedEnvelope']
type SessionEnvelope = components['schemas']['SessionEnvelope']

const CHALLENGE_PATH = '/api/v1/auth/verification-challenges'
const SESSIONS_PATH = '/api/v1/auth/sessions'
const SESSION_PATH = '/api/v1/auth/session'

export class PhoneAuthClientError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly action: PhoneAuthAction,
    readonly status: number = 0,
    readonly requestId?: string,
    readonly fieldErrors?: Record<string, string[]>,
    readonly retryAfterSeconds?: number,
    readonly attemptsRemaining?: number,
    readonly verificationAction?: VerificationFailureAction,
  ) {
    super(message)
    this.name = 'PhoneAuthClientError'
  }
}

type ErrorBody = {
  code?: string
  message?: string
  request_id?: string
  data?: {
    errors?: Record<string, string[]>
    action?: VerificationFailureAction
    attempts_remaining?: number
    retry_after_seconds?: number
  } | null
}

function userMessageFor(code: string, fallback?: string): string {
  switch (code) {
    case 'VALIDATION_ERROR':
      return fallback || '请检查输入后重试'
    case 'ORIGIN_REJECTED':
      return '请求来源不被允许'
    case 'CSRF_INVALID':
      return '安全校验失败，请刷新后重试'
    case 'IDEMPOTENCY_KEY_REQUIRED':
    case 'IDEMPOTENCY_KEY_CONFLICT':
    case 'IDEMPOTENCY_KEY_EXPIRED':
      return '请求无法安全重试，请重新获取验证码'
    case 'RATE_LIMITED':
      return '请求过于频繁，请稍后再试'
    case 'VERIFICATION_FAILED':
      return fallback || '验证码不正确，请重试'
    case 'CHALLENGE_UNAVAILABLE':
      return '验证码已失效，请重新获取'
    case 'CHALLENGE_EXPIRED':
      return '验证码已过期，请重新获取'
    case 'UNAUTHENTICATED':
      return '尚未登录或会话已失效'
    case 'DELIVERY_UNAVAILABLE':
    case 'SERVICE_UNAVAILABLE':
      return '服务暂时不可用，请稍后重试'
    case 'INTERNAL_ERROR':
      return '服务异常，请稍后重试'
    default:
      return fallback || '请求失败，请稍后重试'
  }
}

function actionFor(code: string, verificationAction?: VerificationFailureAction): PhoneAuthAction {
  switch (code) {
    case 'VALIDATION_ERROR':
      return 'fix_fields'
    case 'VERIFICATION_FAILED':
      return verificationAction === 'request_new_code' ? 'request_new_code' : 'retry_code'
    case 'CHALLENGE_UNAVAILABLE':
    case 'CHALLENGE_EXPIRED':
      return 'request_new_code'
    case 'RATE_LIMITED':
      return 'wait_retry'
    case 'DELIVERY_UNAVAILABLE':
    case 'SERVICE_UNAVAILABLE':
    case 'INTERNAL_ERROR':
      return 'retry_later'
    case 'IDEMPOTENCY_KEY_REQUIRED':
    case 'IDEMPOTENCY_KEY_CONFLICT':
    case 'IDEMPOTENCY_KEY_EXPIRED':
      return 'new_idempotency_key'
    case 'ORIGIN_REJECTED':
    case 'CSRF_INVALID':
      return 'security_block'
    case 'UNAUTHENTICATED':
      return 'clear_session'
    case 'PROFILE_COMPLETION_REQUIRED':
    case 'AUTH_VERIFICATION_REQUIRED':
      return 'complete_profile'
    default:
      return 'unknown'
  }
}

/** Map ApiError / envelope into a stable PhoneAuthClientError by business code. */
export function mapPhoneAuthError(err: unknown): PhoneAuthClientError {
  if (err instanceof PhoneAuthClientError) {
    return err
  }
  if (err instanceof ApiError) {
    const body = (err.body ?? null) as ErrorBody | null
    const code = err.code || body?.code || 'INTERNAL_ERROR'
    const data = body?.data
    const verificationAction = data?.action
    const fieldErrors = data?.errors
    const message = userMessageFor(code, body?.message || err.message)
    return new PhoneAuthClientError(
      message,
      code,
      actionFor(code, verificationAction),
      err.status,
      err.requestId ?? body?.request_id,
      fieldErrors,
      typeof data?.retry_after_seconds === 'number' ? data.retry_after_seconds : undefined,
      typeof data?.attempts_remaining === 'number' ? data.attempts_remaining : undefined,
      verificationAction,
    )
  }
  return new PhoneAuthClientError('网络错误，请稍后重试', 'INTERNAL_ERROR', 'retry_later')
}

function assertSuccessData<T>(
  envelope: ApiEnvelope<T> | ChallengeAcceptedEnvelope | SessionEnvelope,
  requestId: string,
): T {
  const code = envelope.code ?? ''
  if (code !== '0' || envelope.data == null) {
    throw mapPhoneAuthError(
      new ApiError(
        typeof envelope.message === 'string' ? envelope.message : '请求失败',
        0,
        envelope,
        requestId,
        code || 'INTERNAL_ERROR',
      ),
    )
  }
  return envelope.data as T
}

/**
 * Request a phone verification challenge (neutral 202).
 * Does not assert account existence or SMS delivery.
 */
export async function requestChallenge(
  body: RequestChallengeRequest,
  idempotencyKey: string,
): Promise<ChallengeAcceptedData> {
  try {
    const { data, requestId } = await apiFetch<ChallengeAcceptedEnvelope>(CHALLENGE_PATH, {
      method: 'POST',
      body: JSON.stringify(body),
      sameOriginAuth: true,
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    })
    return assertSuccessData<ChallengeAcceptedData>(data, requestId)
  } catch (err) {
    throw mapPhoneAuthError(err)
  }
}

/**
 * Verify challenge and create the user's only active session.
 * Session credential is set only via HttpOnly cookie (not in body).
 */
export async function createSession(body: CreateSessionRequest): Promise<SessionData> {
  const result = await verifyChallenge(body)
  if (result.status !== 'authenticated') {
    throw new PhoneAuthClientError(
      '请补充昵称和角色以完成注册',
      'PROFILE_COMPLETION_REQUIRED',
      'complete_profile',
    )
  }
  return result.session
}

export type VerifyChallengeResult =
  | { status: 'authenticated'; session: SessionData }
  | { status: 'complete_profile'; phoneMasked: string }

/** Unified verify: existing users get a session; new users must complete profile. */
export async function verifyChallenge(
  body: CreateSessionRequest,
): Promise<VerifyChallengeResult> {
  try {
    const { data, requestId } = await apiFetch<SessionEnvelope>(SESSIONS_PATH, {
      method: 'POST',
      body: JSON.stringify(body),
      sameOriginAuth: true,
    })
    if (data.code === 'PROFILE_COMPLETION_REQUIRED') {
      const phoneMasked =
        data.data && typeof data.data === 'object' && 'phone_masked' in data.data
          ? String((data.data as { phone_masked?: string }).phone_masked ?? '')
          : ''
      return { status: 'complete_profile', phoneMasked }
    }
    return {
      status: 'authenticated',
      session: assertSuccessData<SessionData>(data, requestId),
    }
  } catch (err) {
    throw mapPhoneAuthError(err)
  }
}

export async function completeProfile(
  body: { nickname: string; role: 'buyer' | 'seller' | 'both' },
  idempotencyKey: string,
): Promise<SessionData> {
  try {
    const { data, requestId } = await apiFetch<SessionEnvelope>(
      '/api/v1/auth/profile-completions',
      {
        method: 'POST',
        body: JSON.stringify(body),
        sameOriginAuth: true,
        headers: { 'Idempotency-Key': idempotencyKey },
      },
    )
    return assertSuccessData<SessionData>(data, requestId)
  } catch (err) {
    throw mapPhoneAuthError(err)
  }
}

/**
 * Bootstrap the current browser session from the HttpOnly cookie.
 * Never reads document.cookie; credentials stay HttpOnly.
 */
export async function bootstrapSession(): Promise<SessionData> {
  try {
    const { data, requestId } = await apiFetch<SessionEnvelope>(SESSION_PATH, {
      method: 'GET',
      sameOriginAuth: true,
    })
    return assertSuccessData<SessionData>(data, requestId)
  } catch (err) {
    throw mapPhoneAuthError(err)
  }
}

/**
 * Idempotent logout. Requires memory CSRF when a valid session cookie is present.
 * Browser supplies Origin; credentials remain HttpOnly and unread.
 */
export async function fetchSecuritySummary(): Promise<{
  session: {
    issued_at: string
    expires_at: string
    generation: number
    client_hint: string | null
  }
  recent_events: Array<{
    event_type: string
    outcome: string
    reason_code: string
    request_id: string
    occurred_at: string
  }>
}> {
  try {
    const { data, requestId } = await apiFetch<
      ApiEnvelope<{
        session: {
          issued_at: string
          expires_at: string
          generation: number
          client_hint: string | null
        }
        recent_events: Array<{
          event_type: string
          outcome: string
          reason_code: string
          request_id: string
          occurred_at: string
        }>
      }>
    >('/api/v1/auth/security-summary', {
      method: 'GET',
      sameOriginAuth: true,
    })
    return assertSuccessData(data, requestId)
  } catch (err) {
    throw mapPhoneAuthError(err)
  }
}

export async function revokeAllSessions(csrfToken: string | null): Promise<void> {
  try {
    const headers: Record<string, string> = {}
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken
    }
    const { data, requestId } = await apiFetch<ApiEnvelope<{ logged_out?: boolean }>>(
      '/api/v1/auth/session-revocations',
      {
        method: 'POST',
        sameOriginAuth: true,
        headers,
        body: JSON.stringify({ scope: 'all' }),
      },
    )
    const code = data.code ?? ''
    if (code !== '0') {
      throw mapPhoneAuthError(
        new ApiError(
          typeof data.message === 'string' ? data.message : '退出失败',
          0,
          data,
          requestId,
          code || 'INTERNAL_ERROR',
        ),
      )
    }
  } catch (err) {
    throw mapPhoneAuthError(err)
  }
}

export async function logoutSession(csrfToken: string | null): Promise<void> {
  try {
    const headers: Record<string, string> = {}
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken
    }
    const { data, requestId } = await apiFetch<components['schemas']['LogoutEnvelope']>(
      SESSION_PATH,
      {
        method: 'DELETE',
        sameOriginAuth: true,
        headers,
      },
    )
    const code = data.code ?? ''
    if (code !== '0') {
      throw mapPhoneAuthError(
        new ApiError(
          typeof data.message === 'string' ? data.message : '退出失败',
          0,
          data,
          requestId,
          code || 'INTERNAL_ERROR',
        ),
      )
    }
  } catch (err) {
    throw mapPhoneAuthError(err)
  }
}
