import { FormEvent, useId, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { registerUser } from '../api/v1/auth'
import type { RegisterSuccessData, UserRole } from '../types/auth'

type FieldKey = 'phone' | 'nickname' | 'role'

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'buyer', label: '买家' },
  { value: 'seller', label: '卖家' },
  { value: 'both', label: '买家与卖家' },
]

function mapBusinessError(code: string, message: string): string {
  switch (code) {
    case 'PHONE_ALREADY_REGISTERED':
      return '该手机号已被注册'
    case 'ACCOUNT_UNAVAILABLE':
      return '账户不可用，请通过恢复流程处理'
    case 'RATE_LIMITED':
      return '请求过于频繁，请稍后再试'
    case 'IDEMPOTENCY_KEY_CONFLICT':
    case 'IDEMPOTENCY_KEY_EXPIRED':
    case 'IDEMPOTENCY_KEY_REQUIRED':
      return message || '请求无法安全重试，请刷新后重试'
    case 'SERVICE_UNAVAILABLE':
      return '服务暂时不可用，请稍后重试'
    default:
      return message || '注册失败'
  }
}

export function Register() {
  const phoneId = useId()
  const nickId = useId()
  const roleId = useId()
  const [phone, setPhone] = useState('')
  const [nickname, setNickname] = useState('')
  const [role, setRole] = useState<UserRole | ''>('')
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState<RegisterSuccessData | null>(null)
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID())

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    setFieldErrors({})
    const local: Partial<Record<FieldKey, string>> = {}
    if (!phone.trim()) local.phone = '请输入手机号'
    if (!nickname.trim()) local.nickname = '请输入昵称'
    if (!role) local.role = '请选择角色'
    if (Object.keys(local).length) {
      setFieldErrors(local)
      return
    }

    setSubmitting(true)
    try {
      const envelope = await registerUser(
        { phone, nickname, role: role as UserRole },
        idempotencyKeyRef.current,
      )
      if (envelope.code !== '0' || !envelope.data) {
        setFormError(mapBusinessError(envelope.code, envelope.message))
        setRequestId(envelope.request_id)
        return
      }
      setSuccess(envelope.data)
      setRequestId(envelope.request_id)
      // Next independent submit uses a new key
      idempotencyKeyRef.current = crypto.randomUUID()
    } catch (err) {
      if (err instanceof ApiError) {
        setRequestId(err.requestId ?? null)
        const body = err.body as {
          code?: string
          message?: string
          data?: { errors?: Record<string, string[]> }
        } | null
        if (body?.code === 'VALIDATION_ERROR' && body.data?.errors) {
          const next: Partial<Record<FieldKey, string>> = {}
          for (const [k, msgs] of Object.entries(body.data.errors)) {
            if (k === 'phone' || k === 'nickname' || k === 'role') {
              next[k] = msgs[0] ?? '无效'
            }
          }
          setFieldErrors(next)
          setFormError(body.message ?? '请求参数不合法')
        } else if (body?.code) {
          setFormError(mapBusinessError(body.code, body.message ?? err.message))
        } else {
          setFormError(err.message)
        }
      } else {
        setFormError('注册失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (success) {
    return (
      <div className="card success-box">
        <h1>注册成功</h1>
        <p>用户标识：{success.user_id}</p>
        <p>角色：{success.role}</p>
        {success.phone_masked ? <p>手机号：{success.phone_masked}</p> : null}
        <p>
          <strong>尚未登录。</strong>
          访问令牌与会话由后续登录功能签发，当前不会自动获得访问权限。
        </p>
        {requestId ? <p>请求标识：{requestId}</p> : null}
      </div>
    )
  }

  return (
    <div className="card">
      <h1>注册</h1>
      <p>填写手机号、昵称与角色创建账户。注册不会签发登录凭证。</p>
      {formError ? (
        <div className="form-error" role="alert">
          {formError}
          {requestId ? <div>请求标识：{requestId}</div> : null}
        </div>
      ) : null}
      <form onSubmit={onSubmit} noValidate>
        <div className="form-field">
          <label htmlFor={phoneId}>手机号</label>
          <input
            id={phoneId}
            name="phone"
            type="tel"
            autoComplete="tel"
            value={phone}
            onChange={(ev) => setPhone(ev.target.value)}
            aria-invalid={fieldErrors.phone ? true : undefined}
            aria-describedby={fieldErrors.phone ? `${phoneId}-err` : undefined}
            disabled={submitting}
          />
          {fieldErrors.phone ? (
            <div id={`${phoneId}-err`} className="field-error">
              {fieldErrors.phone}
            </div>
          ) : null}
        </div>
        <div className="form-field">
          <label htmlFor={nickId}>昵称</label>
          <input
            id={nickId}
            name="nickname"
            type="text"
            autoComplete="nickname"
            value={nickname}
            onChange={(ev) => setNickname(ev.target.value)}
            aria-invalid={fieldErrors.nickname ? true : undefined}
            aria-describedby={fieldErrors.nickname ? `${nickId}-err` : undefined}
            disabled={submitting}
          />
          {fieldErrors.nickname ? (
            <div id={`${nickId}-err`} className="field-error">
              {fieldErrors.nickname}
            </div>
          ) : null}
        </div>
        <div className="form-field">
          <label htmlFor={roleId}>角色</label>
          <select
            id={roleId}
            name="role"
            value={role}
            onChange={(ev) => setRole(ev.target.value as UserRole | '')}
            aria-invalid={fieldErrors.role ? true : undefined}
            aria-describedby={fieldErrors.role ? `${roleId}-err` : undefined}
            disabled={submitting}
          >
            <option value="">请选择</option>
            {ROLE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {fieldErrors.role ? (
            <div id={`${roleId}-err`} className="field-error">
              {fieldErrors.role}
            </div>
          ) : null}
        </div>
        <button className="primary" type="submit" disabled={submitting}>
          {submitting ? '提交中…' : '注册'}
        </button>
      </form>
    </div>
  )
}

export default Register
