/**
 * sessionStorage adapter for phone-login challenge metadata only.
 *
 * Allowed fields: challenge_id, phone_masked, expires_at, resend_available_at.
 * Absolute server-issued deadlines drive countdown; never store raw phone, OTP,
 * CSRF, session tokens, or full user summary.
 */

import type { ChallengeAcceptedData } from '../types/auth'

export const CHALLENGE_STORAGE_KEY = 'tokenmarket.auth.challenge.v1'

const ALLOWED_KEYS = ['challenge_id', 'phone_masked', 'expires_at', 'resend_available_at'] as const

export type PersistedChallenge = Pick<
  ChallengeAcceptedData,
  'challenge_id' | 'phone_masked' | 'expires_at' | 'resend_available_at'
>

function isIsoDateString(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value))
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

/** Seconds remaining until an absolute ISO deadline (server clock authority). */
export function secondsUntilDeadline(iso: string, nowMs: number = Date.now()): number {
  const target = Date.parse(iso)
  if (Number.isNaN(target)) return 0
  return Math.max(0, Math.ceil((target - nowMs) / 1000))
}

export function isDeadlinePassed(iso: string, nowMs: number = Date.now()): boolean {
  return secondsUntilDeadline(iso, nowMs) <= 0
}

/** Reject any key outside the allowlist (raw phone, OTP, CSRF, user summary, …). */
function hasForbiddenKeys(record: Record<string, unknown>): boolean {
  for (const key of Object.keys(record)) {
    if (!(ALLOWED_KEYS as readonly string[]).includes(key)) {
      return true
    }
  }
  return false
}

function normalize(data: ChallengeAcceptedData): PersistedChallenge | null {
  if (
    !isNonEmptyString(data.challenge_id) ||
    !isNonEmptyString(data.phone_masked) ||
    !isIsoDateString(data.expires_at) ||
    !isIsoDateString(data.resend_available_at)
  ) {
    return null
  }
  // phone_masked must not look like a full CN mobile number.
  if (/1[3-9]\d{9}/.test(data.phone_masked.replace(/\D/g, ''))) {
    return null
  }
  return {
    challenge_id: data.challenge_id,
    phone_masked: data.phone_masked,
    expires_at: data.expires_at,
    resend_available_at: data.resend_available_at,
  }
}

function getStorage(): Storage | null {
  try {
    if (typeof sessionStorage === 'undefined') return null
    return sessionStorage
  } catch {
    return null
  }
}

/** Persist allowed challenge metadata only. */
export function saveChallenge(data: ChallengeAcceptedData): void {
  const storage = getStorage()
  if (!storage) return
  const normalized = normalize(data)
  if (!normalized) {
    clearChallenge()
    return
  }
  storage.setItem(CHALLENGE_STORAGE_KEY, JSON.stringify(normalized))
}

/**
 * Restore challenge metadata after refresh.
 * Returns null when missing, malformed, forbidden fields present, or expired
 * by absolute `expires_at` (server-issued wall time).
 */
export function loadChallenge(nowMs: number = Date.now()): ChallengeAcceptedData | null {
  const storage = getStorage()
  if (!storage) return null
  const raw = storage.getItem(CHALLENGE_STORAGE_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      clearChallenge()
      return null
    }
    if (hasForbiddenKeys(parsed)) {
      clearChallenge()
      return null
    }
    const candidate: ChallengeAcceptedData = {
      challenge_id: String(parsed.challenge_id ?? ''),
      phone_masked: String(parsed.phone_masked ?? ''),
      expires_at: String(parsed.expires_at ?? ''),
      resend_available_at: String(parsed.resend_available_at ?? ''),
    }
    const normalized = normalize(candidate)
    if (!normalized) {
      clearChallenge()
      return null
    }
    if (isDeadlinePassed(normalized.expires_at, nowMs)) {
      clearChallenge()
      return null
    }
    return normalized
  } catch {
    clearChallenge()
    return null
  }
}

/** Clear on terminal success, logout, session invalidation, or expired challenge. */
export function clearChallenge(): void {
  const storage = getStorage()
  if (!storage) return
  try {
    storage.removeItem(CHALLENGE_STORAGE_KEY)
  } catch {
    // ignore quota / private mode
  }
}
