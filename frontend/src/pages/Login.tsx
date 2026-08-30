import { FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import {
  PhoneAuthClientError,
  completeProfile,
  createSession,
  requestChallenge,
} from '../api/v1/phoneAuth'
import { useAuth } from '../auth/AuthContext'
import {
  clearChallenge,
  loadChallenge,
  saveChallenge,
  secondsUntilDeadline,
} from '../auth/challengeState'
import type { ChallengeAcceptedData, UserRole } from '../types/auth'

type FieldKey = 'phone' | 'code'

/**
 * FR-019 login flow states — single primary state for a11y / tests.
 * Mutually exclusive display priority is resolved in `deriveLoginState`.
 */
export type LoginUiState =
  | 'idle'
  | 'requesting'
  | 'accepted'
  | 'countdown'
  | 'verifying'
  | 'success'
  | 'field-error'
  | 'code-error'
  | 'expired'
  | 'rate-limited'
  | 'unavailable'

type ErrorKind = 'field-error' | 'code-error' | 'expired' | 'rate-limited' | 'unavailable' | null

/** Only restore in-app relative paths; block open redirects. */
export function safeInternalPath(candidate: unknown, fallback = '/dashboard'): string {
  if (typeof candidate !== 'string' || candidate.length === 0) {
    return fallback
  }
  if (!candidate.startsWith('/') || candidate.startsWith('//')) {
    return fallback
  }
  if (candidate.includes('://') || candidate.includes('\\')) {
    return fallback
  }
  return candidate
}

export function deriveLoginState(input: {
  requestingCode: boolean
  loggingIn: boolean
  success: boolean
  errorKind: ErrorKind
  hasChallenge: boolean
  resendSeconds: number
}): LoginUiState {
  if (input.success) return 'success'
  if (input.loggingIn) return 'verifying'
  if (input.requestingCode) return 'requesting'
  if (input.errorKind) return input.errorKind
  if (input.hasChallenge && input.resendSeconds > 0) return 'countdown'
  if (input.hasChallenge) return 'accepted'
  return 'idle'
}

export function Login() {
  const phoneId = useId()
  const codeId = useId()
  const phoneHelpId = useId()
  const codeHelpId = useId()
  const statusId = useId()
  const alertId = useId()
  const auth = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const locationState = location.state as { from?: string } | null

  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [profileStep, setProfileStep] = useState(false)
  const [nickname, setNickname] = useState('')
  const [role, setRole] = useState<UserRole | ''>('')
  const profileKeyRef = useRef<string>(crypto.randomUUID())
  const [challenge, setChallenge] = useState<ChallengeAcceptedData | null>(() => loadChallenge())
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [errorKind, setErrorKind] = useState<ErrorKind>(null)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [requestingCode, setRequestingCode] = useState(false)
  const [loggingIn, setLoggingIn] = useState(false)
  const [success, setSuccess] = useState(false)
  const [nowMs, setNowMs] = useState(() => Date.now())
  /** One-shot polite announcement when countdown starts; not updated every second. */
  const [countdownAnnouncement, setCountdownAnnouncement] = useState<string | null>(null)

  const phoneRef = useRef<HTMLInputElement>(null)
  const otpRef = useRef<HTMLInputElement>(null)
  const alertRef = useRef<HTMLDivElement>(null)
  /** One UUID per user "get code" action; reuse on retry of the same action. */
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID())
  const codeInFlightRef = useRef(false)
  const loginInFlightRef = useRef(false)
  const prevResendPositiveRef = useRef(false)

  // Expiry is derived during render (not synced via effect setState).
  const challengeExpired =
    challenge !== null && secondsUntilDeadline(challenge.expires_at, nowMs) <= 0
  const activeChallenge = challengeExpired ? null : challenge
  const resendSeconds = activeChallenge
    ? secondsUntilDeadline(activeChallenge.resend_available_at, nowMs)
    : 0
  const canResend = !activeChallenge || resendSeconds <= 0
  const displayErrorKind: ErrorKind = challengeExpired ? 'expired' : errorKind
  const displayFormError = challengeExpired ? '验证码已过期，请重新获取' : formError

  const loginState = useMemo(
    () =>
      deriveLoginState({
        requestingCode,
        loggingIn,
        success,
        errorKind: displayErrorKind,
        hasChallenge: Boolean(activeChallenge),
        resendSeconds,
      }),
    [requestingCode, loggingIn, success, displayErrorKind, activeChallenge, resendSeconds],
  )

  // Tick from absolute server deadlines while a non-expired challenge is active.
  useEffect(() => {
    if (!challenge || challengeExpired) return
    const id = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [challenge, challengeExpired])

  // Low-noise status: announce countdown once on enter, not every second.
  useEffect(() => {
    const active = Boolean(activeChallenge) && resendSeconds > 0
    if (active && !prevResendPositiveRef.current) {
      // Wording avoids "请求已受理" so visible status remains the unique match for tests/AT.
      setCountdownAnnouncement('冷却计时已开始，请查收验证码后再试')
    }
    if (!active && prevResendPositiveRef.current) {
      setCountdownAnnouncement('可以重新获取验证码')
    }
    prevResendPositiveRef.current = active
  }, [activeChallenge, resendSeconds])

  // Persist expiry to storage only (external system); UI uses derived activeChallenge.
  useEffect(() => {
    if (challengeExpired) {
      clearChallenge()
    }
  }, [challengeExpired])

  const focusOtp = useCallback(() => {
    window.requestAnimationFrame(() => {
      otpRef.current?.focus()
    })
  }, [])

  const focusFieldError = useCallback((errors: Partial<Record<FieldKey, string>>) => {
    window.requestAnimationFrame(() => {
      if (errors.phone) {
        phoneRef.current?.focus()
      } else if (errors.code) {
        otpRef.current?.focus()
      }
    })
  }, [])

  const focusAlert = useCallback(() => {
    window.requestAnimationFrame(() => {
      alertRef.current?.focus()
    })
  }, [])

  const resetErrors = () => {
    setFormError(null)
    setFieldErrors({})
    setErrorKind(null)
    setRequestId(null)
  }

  const onRequestCode = async () => {
    if (codeInFlightRef.current || requestingCode) return
    resetErrors()

    if (!phone.trim()) {
      const next = { phone: '请输入手机号' }
      setFieldErrors(next)
      setErrorKind('field-error')
      focusFieldError(next)
      return
    }

    codeInFlightRef.current = true
    setRequestingCode(true)
    try {
      const accepted = await requestChallenge({ phone: phone.trim() }, idempotencyKeyRef.current)
      setChallenge(accepted)
      saveChallenge(accepted)
      // Next independent "get code" uses a fresh key after this action completed.
      idempotencyKeyRef.current = crypto.randomUUID()
      setNowMs(Date.now())
      focusOtp()
    } catch (err) {
      if (err instanceof PhoneAuthClientError) {
        setRequestId(err.requestId ?? null)
        if (err.action === 'fix_fields' && err.fieldErrors) {
          const next: Partial<Record<FieldKey, string>> = {}
          for (const [k, msgs] of Object.entries(err.fieldErrors)) {
            if (k === 'phone' || k === 'code') {
              next[k] = msgs[0] ?? '无效'
            }
          }
          setFieldErrors(next)
          setFormError(err.message)
          setErrorKind('field-error')
          focusFieldError(next)
        } else if (err.action === 'wait_retry') {
          setFormError(err.message)
          setErrorKind('rate-limited')
          focusAlert()
        } else if (err.action === 'retry_later') {
          setFormError(err.message)
          setErrorKind('unavailable')
          focusAlert()
        } else {
          setFormError(err.message)
          setErrorKind('unavailable')
          focusAlert()
        }
        if (err.action === 'new_idempotency_key') {
          idempotencyKeyRef.current = crypto.randomUUID()
        }
      } else {
        setFormError('获取验证码失败')
        setErrorKind('unavailable')
        focusAlert()
      }
    } finally {
      codeInFlightRef.current = false
      setRequestingCode(false)
    }
  }

  const onSubmitLogin = async (e: FormEvent) => {
    e.preventDefault()
    if (loginInFlightRef.current || loggingIn || success) return
    resetErrors()

    const local: Partial<Record<FieldKey, string>> = {}
    if (!activeChallenge?.challenge_id) {
      setFormError('请先获取验证码')
      setErrorKind('field-error')
      focusAlert()
      return
    }
    if (!code) {
      local.code = '请输入验证码'
    } else if (!/^\d{6}$/.test(code)) {
      local.code = '验证码须为 6 位数字'
    }
    if (Object.keys(local).length) {
      setFieldErrors(local)
      setErrorKind('field-error')
      focusFieldError(local)
      return
    }

    loginInFlightRef.current = true
    setLoggingIn(true)
    const submittedCode = code
    const challengeId = activeChallenge.challenge_id
    // Clear OTP from the form as soon as submit starts (terminal for raw OTP value).
    setCode('')
    try {
      const sessionData = await createSession({
        challenge_id: challengeId,
        code: submittedCode,
      })
      clearChallenge()
      setChallenge(null)
      setSuccess(true)
      // Session summary + CSRF go only into AuthContext.
      auth.establishSession(sessionData)
      const target = safeInternalPath(locationState?.from)
      navigate(target, { replace: true })
    } catch (err) {
      if (err instanceof PhoneAuthClientError && err.action === 'complete_profile') {
        clearChallenge()
        setChallenge(null)
        setProfileStep(true)
        setFormError(null)
        setErrorKind(null)
        return
      }
      if (err instanceof PhoneAuthClientError) {
        setRequestId(err.requestId ?? null)
        if (err.action === 'fix_fields' && err.fieldErrors) {
          const next: Partial<Record<FieldKey, string>> = {}
          for (const [k, msgs] of Object.entries(err.fieldErrors)) {
            if (k === 'phone' || k === 'code') {
              next[k] = msgs[0] ?? '无效'
            }
          }
          setFieldErrors(next)
          setFormError(err.message)
          setErrorKind('field-error')
          focusFieldError(next)
        } else if (err.action === 'retry_code') {
          setFormError(err.message)
          setErrorKind('code-error')
          focusOtp()
        } else if (err.action === 'request_new_code') {
          const expired = err.code === 'CHALLENGE_EXPIRED' || /过期/.test(err.message)
          setFormError(err.message)
          setErrorKind(expired ? 'expired' : 'code-error')
          clearChallenge()
          setChallenge(null)
          focusAlert()
        } else if (err.action === 'wait_retry') {
          setFormError(err.message)
          setErrorKind('rate-limited')
          focusAlert()
        } else if (err.action === 'retry_later') {
          setFormError(err.message)
          setErrorKind('unavailable')
          focusAlert()
        } else {
          setFormError(err.message)
          setErrorKind('unavailable')
          focusAlert()
        }
      } else {
        setFormError('登录失败')
        setErrorKind('unavailable')
        focusAlert()
      }
    } finally {
      loginInFlightRef.current = false
      setLoggingIn(false)
    }
  }

  if (auth.status === 'authenticated') {
    return <Navigate to={safeInternalPath(locationState?.from)} replace />
  }

  const busy = requestingCode || loggingIn
  const getCodeLabel = requestingCode
    ? '提交中…'
    : !canResend
      ? `${resendSeconds} 秒后可重新获取`
      : '获取验证码'

  const phoneErrorId = fieldErrors.phone ? `${phoneId}-err` : undefined
  const codeErrorId = fieldErrors.code ? `${codeId}-err` : undefined
  const phoneDescribedBy = [phoneHelpId, phoneErrorId].filter(Boolean).join(' ')
  const codeDescribedBy = [codeHelpId, codeErrorId].filter(Boolean).join(' ')

  // Polite status region content — stable messages, no per-second countdown digits.
  const statusMessage =
    loginState === 'requesting'
      ? '正在提交验证码请求'
      : loginState === 'verifying'
        ? '正在验证并登录'
        : loginState === 'success'
          ? '登录成功'
          : loginState === 'countdown' || loginState === 'accepted'
            ? countdownAnnouncement
            : null

  return (
    <div className="card" data-login-state={loginState} data-testid="login-page">
      <h1>{profileStep ? '完成注册' : '登录'}</h1>
      <p id={`${phoneId}-intro`}>
        {profileStep
          ? '手机号已验证。请填写昵称和角色，完成后将自动登录。'
          : '使用手机号验证码登录或注册。验证前不会提示该号码是否已注册。'}
      </p>

      {profileStep ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            if (!nickname.trim() || !role) {
              setFormError('请填写昵称并选择角色')
              setErrorKind('field-error')
              return
            }
            try {
              const sessionData = await completeProfile(
                { nickname: nickname.trim(), role },
                profileKeyRef.current,
              )
              setSuccess(true)
              auth.establishSession(sessionData)
              navigate(safeInternalPath(locationState?.from), { replace: true })
            } catch (err) {
              const message =
                err instanceof PhoneAuthClientError ? err.message : '完成注册失败'
              setFormError(message)
              setErrorKind('unavailable')
            }
          }}
        >
          <label htmlFor={`${phoneId}-nick`}>昵称</label>
          <input
            id={`${phoneId}-nick`}
            value={nickname}
            onChange={(ev) => setNickname(ev.target.value)}
            autoComplete="nickname"
          />
          <label htmlFor={`${phoneId}-role`}>角色</label>
          <select
            id={`${phoneId}-role`}
            value={role}
            onChange={(ev) => setRole(ev.target.value as UserRole)}
          >
            <option value="">请选择</option>
            <option value="buyer">买家</option>
            <option value="seller">卖家</option>
            <option value="both">买家与卖家</option>
          </select>
          {formError ? (
            <div className="form-error" role="alert">
              {formError}
            </div>
          ) : null}
          <button type="submit">完成并登录</button>
        </form>
      ) : null}

      {!profileStep ? (
      <>
      {/* Low-noise live region: state transitions only, not ticking seconds.
          No role="status" here so the challenge accept status remains the sole status. */}
      <div id={statusId} className="sr-only" aria-live="polite" aria-atomic="true">
        {statusMessage}
      </div>

      {displayFormError ? (
        <div
          id={alertId}
          ref={alertRef}
          className="form-error"
          role="alert"
          tabIndex={-1}
          data-error-kind={displayErrorKind ?? undefined}
        >
          {displayFormError}
          {requestId ? <div>请求标识：{requestId}</div> : null}
        </div>
      ) : null}

      {activeChallenge ? (
        <div className="neutral-accept" data-testid="challenge-status">
          {/* Static accept copy only inside status — countdown stays outside to avoid SR spam. */}
          <div role="status" aria-live="polite" aria-atomic="true">
            <p>
              请求已受理。请向 <strong>{activeChallenge.phone_masked}</strong>{' '}
              对应终端查收验证码（若可接收），并在有效期内完成登录。
            </p>
            <p className="hint">受理结果不表示账户是否存在，也不保证短信一定送达。</p>
          </div>
          {/* Visual countdown only — not aria-live (avoids per-second SR noise). */}
          {!canResend ? (
            <p data-testid="resend-countdown" aria-hidden="true">
              {resendSeconds} 秒后可重新获取
            </p>
          ) : (
            <p data-testid="resend-ready">可以重新获取验证码</p>
          )}
        </div>
      ) : null}

      <form
        onSubmit={onSubmitLogin}
        noValidate
        aria-busy={busy || undefined}
        aria-describedby={statusMessage ? statusId : undefined}
      >
        <div className="form-field">
          <label htmlFor={phoneId}>手机号</label>
          <input
            ref={phoneRef}
            id={phoneId}
            name="phone"
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            value={phone}
            onChange={(ev) => setPhone(ev.target.value)}
            aria-invalid={fieldErrors.phone ? true : undefined}
            aria-describedby={phoneDescribedBy || undefined}
            disabled={busy}
          />
          <div id={phoneHelpId} className="field-help">
            中国大陆 11 位手机号，可含空格或 +86 前缀
          </div>
          {fieldErrors.phone ? (
            <div id={`${phoneId}-err`} className="field-error" role="alert">
              {fieldErrors.phone}
            </div>
          ) : null}
        </div>

        <div className="form-field form-field-inline">
          <button
            type="button"
            className="secondary"
            onClick={() => void onRequestCode()}
            disabled={busy || !canResend}
            aria-busy={requestingCode || undefined}
          >
            {getCodeLabel}
          </button>
        </div>

        <div className="form-field">
          <label htmlFor={codeId}>验证码</label>
          <input
            ref={otpRef}
            id={codeId}
            name="code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={6}
            value={code}
            onChange={(ev) => {
              // Allow leading zeros; keep digits only for paste hygiene but preserve length rules via validation.
              setCode(ev.target.value)
            }}
            aria-invalid={fieldErrors.code ? true : undefined}
            aria-describedby={codeDescribedBy || undefined}
            disabled={busy}
          />
          <div id={codeHelpId} className="field-help">
            6 位数字，前导零有效
          </div>
          {fieldErrors.code ? (
            <div id={`${codeId}-err`} className="field-error" role="alert">
              {fieldErrors.code}
            </div>
          ) : null}
        </div>

        <button
          className="primary"
          type="submit"
          disabled={busy}
          aria-busy={loggingIn || undefined}
        >
          {loggingIn ? '登录中…' : success ? '登录成功' : '登录'}
        </button>
      </form>

      <p className="auth-footer">
        还没有账户？<Link to="/register">前往注册</Link>（同一验证码流程）
      </p>
      </>
      ) : null}
    </div>
  )
}

export default Login
