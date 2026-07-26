import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChallengeAcceptedData } from '../types/auth'
import {
  CHALLENGE_STORAGE_KEY,
  clearChallenge,
  isDeadlinePassed,
  loadChallenge,
  saveChallenge,
  secondsUntilDeadline,
} from './challengeState'

const VALID: ChallengeAcceptedData = {
  challenge_id: '11111111-1111-1111-1111-111111111111',
  phone_masked: '*******8000',
  expires_at: '2099-01-01T00:05:00.000Z',
  resend_available_at: '2099-01-01T00:01:00.000Z',
}

describe('challengeState', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    vi.useRealTimers()
  })

  afterEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    vi.useRealTimers()
  })

  it('saves only challenge id, phone_masked, and absolute deadlines to sessionStorage', () => {
    saveChallenge(VALID)
    const raw = sessionStorage.getItem(CHALLENGE_STORAGE_KEY)
    expect(raw).toBeTruthy()
    const parsed = JSON.parse(raw as string) as Record<string, unknown>
    expect(Object.keys(parsed).sort()).toEqual(
      ['challenge_id', 'expires_at', 'phone_masked', 'resend_available_at'].sort(),
    )
    expect(parsed.challenge_id).toBe(VALID.challenge_id)
    expect(parsed.phone_masked).toBe(VALID.phone_masked)
    expect(parsed.expires_at).toBe(VALID.expires_at)
    expect(parsed.resend_available_at).toBe(VALID.resend_available_at)
    expect(localStorage.length).toBe(0)
  })

  it('restores challenge after simulated refresh (load from sessionStorage)', () => {
    saveChallenge(VALID)
    const restored = loadChallenge(Date.parse('2099-01-01T00:00:30.000Z'))
    expect(restored).toEqual(VALID)
  })

  it('uses absolute server deadlines for countdown (server clock authority)', () => {
    const now = Date.parse('2099-01-01T00:00:00.000Z')
    expect(secondsUntilDeadline('2099-01-01T00:01:00.000Z', now)).toBe(60)
    expect(secondsUntilDeadline('2099-01-01T00:00:00.500Z', now)).toBe(1)
    expect(secondsUntilDeadline('2098-12-31T23:59:59.000Z', now)).toBe(0)
    expect(isDeadlinePassed('2099-01-01T00:00:00.000Z', now)).toBe(true)
    expect(isDeadlinePassed('2099-01-01T00:00:01.000Z', now)).toBe(false)

    // Restored resend countdown is derived from absolute resend_available_at, not a relative client timer seed.
    saveChallenge({
      ...VALID,
      resend_available_at: '2099-01-01T00:00:45.000Z',
      expires_at: '2099-01-01T00:05:00.000Z',
    })
    const restored = loadChallenge(now)
    expect(restored).not.toBeNull()
    expect(secondsUntilDeadline(restored!.resend_available_at, now)).toBe(45)
  })

  it('clears expired challenges on load based on absolute expires_at', () => {
    saveChallenge({
      ...VALID,
      expires_at: '2099-01-01T00:00:00.000Z',
      resend_available_at: '2098-12-31T23:59:00.000Z',
    })
    expect(loadChallenge(Date.parse('2099-01-01T00:00:01.000Z'))).toBeNull()
    expect(sessionStorage.getItem(CHALLENGE_STORAGE_KEY)).toBeNull()
  })

  it('clearChallenge removes terminal state from sessionStorage', () => {
    saveChallenge(VALID)
    expect(sessionStorage.getItem(CHALLENGE_STORAGE_KEY)).toBeTruthy()
    clearChallenge()
    expect(sessionStorage.getItem(CHALLENGE_STORAGE_KEY)).toBeNull()
    expect(loadChallenge()).toBeNull()
  })

  it('rejects and clears payloads with raw phone, OTP, CSRF, or user summary fields', () => {
    const forbiddenPayloads: Record<string, unknown>[] = [
      { ...VALID, phone: '13800138000' },
      { ...VALID, code: '012345' },
      { ...VALID, otp: '012345' },
      { ...VALID, csrf_token: 'csrf-secret' },
      { ...VALID, user_id: 'user-1', nickname: '买家', role: 'buyer' },
      { ...VALID, session_token: 'tok' },
    ]
    for (const payload of forbiddenPayloads) {
      sessionStorage.setItem(CHALLENGE_STORAGE_KEY, JSON.stringify(payload))
      expect(loadChallenge(Date.parse('2099-01-01T00:00:00.000Z'))).toBeNull()
      expect(sessionStorage.getItem(CHALLENGE_STORAGE_KEY)).toBeNull()
    }
  })

  it('never writes raw phone, OTP, CSRF, or user summary via saveChallenge API', () => {
    // API only accepts ChallengeAcceptedData; verify storage blob excludes secrets.
    saveChallenge(VALID)
    const blob = [
      ...Array.from({ length: sessionStorage.length }, (_, i) => {
        const k = sessionStorage.key(i)
        return k ? `${k}=${sessionStorage.getItem(k)}` : ''
      }),
      ...Array.from({ length: localStorage.length }, (_, i) => {
        const k = localStorage.key(i)
        return k ? `${k}=${localStorage.getItem(k)}` : ''
      }),
    ].join('\n')
    expect(blob).not.toMatch(/138\d{8}/)
    expect(blob).not.toContain('012345')
    expect(blob.toLowerCase()).not.toContain('csrf')
    expect(blob).not.toContain('user_id')
    expect(blob).not.toContain('nickname')
  })

  it('rejects phone_masked that embeds a full mobile number', () => {
    saveChallenge({
      ...VALID,
      phone_masked: '13800138000',
    })
    expect(sessionStorage.getItem(CHALLENGE_STORAGE_KEY)).toBeNull()
  })
})
