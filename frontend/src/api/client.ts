/**
 * Same-origin browser API client for TokenMarket.
 *
 * Auth traffic must use relative `/api/...` paths so Vite (local HTTPS) or
 * frontend Nginx (deploy) proxies to the API. Never fall back to a direct
 * API host when `VITE_API_BASE_URL` is unset — Secure cookies require same origin.
 */

const DEFAULT_TIMEOUT_MS = 10_000

/** Known loopback API fallbacks (any port) — never use for browser auth cookies. */
const DIRECT_API_FALLBACK_HOSTS = [
  'http://127.0.0.1:8000',
  'http://localhost:8000',
  'https://127.0.0.1:8000',
  'https://localhost:8000',
] as const

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
    readonly requestId?: string,
    readonly code?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Resolve the API base URL for non-auth tooling requests.
 *
 * Default is an empty string so paths like `/api/v1/...` hit the same-origin
 * proxy. Does **not** fall back to `http://127.0.0.1:8000` when unset.
 */
export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (typeof raw === 'string' && raw.trim() !== '') {
    return raw.replace(/\/$/, '')
  }
  return ''
}

/** True when `base` targets a loopback API host (any port) unsuitable for auth. */
export function isDirectApiHost(base: string): boolean {
  const normalized = base.replace(/\/$/, '')
  if ((DIRECT_API_FALLBACK_HOSTS as readonly string[]).includes(normalized)) {
    return true
  }
  try {
    const url = new URL(normalized)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return false
    }
    // Any absolute loopback URL is a direct host (not relative same-origin /api).
    return url.hostname === '127.0.0.1' || url.hostname === 'localhost'
  } catch {
    return false
  }
}

/**
 * Auth-safe base URL for browser session/cookie traffic.
 *
 * Always relative same-origin when unset. Throws if `VITE_API_BASE_URL` points
 * at a loopback API host — Secure cookie + CSRF require Vite/nginx `/api` proxy.
 */
export function getBrowserAuthBaseUrl(): string {
  const base = getApiBaseUrl()
  if (base === '') {
    return ''
  }
  if (isDirectApiHost(base)) {
    throw new Error(
      'Browser auth must use same-origin relative /api (Vite/nginx proxy); ' +
        'do not set VITE_API_BASE_URL to a direct API host',
    )
  }
  return base
}

/** Join base + path for fetch. Paths should start with `/api` for same-origin proxy. */
export function resolveApiUrl(path: string, base: string = getApiBaseUrl()): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${base}${normalized}`
}

type EnvelopeLike = {
  code?: string
  message?: string
  request_id?: string
  data?: unknown
}

function parseEnvelopeBody(text: string): unknown {
  if (!text) {
    return null
  }
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

function envelopeFields(body: unknown): EnvelopeLike {
  if (body && typeof body === 'object') {
    return body as EnvelopeLike
  }
  return {}
}

export type ApiFetchInit = RequestInit & {
  timeoutMs?: number
  /** When true, force same-origin auth URL resolution (cookie/CSRF paths). */
  sameOriginAuth?: boolean
}

export async function apiFetch<T>(
  path: string,
  init: ApiFetchInit = {},
): Promise<{ data: T; requestId: string }> {
  const {
    timeoutMs = DEFAULT_TIMEOUT_MS,
    headers,
    credentials,
    sameOriginAuth = false,
    ...rest
  } = init
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const requestId = crypto.randomUUID()
  const base = sameOriginAuth ? getBrowserAuthBaseUrl() : getApiBaseUrl()
  const url = resolveApiUrl(path, base)

  try {
    const res = await fetch(url, {
      ...rest,
      credentials: credentials ?? 'include',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': requestId,
        ...(headers as Record<string, string>),
      },
    })

    const text = await res.text()
    const body = parseEnvelopeBody(text)
    const fields = envelopeFields(body)
    const rid =
      res.headers.get('X-Request-ID') ??
      (typeof fields.request_id === 'string' && fields.request_id
        ? fields.request_id
        : requestId)

    if (!res.ok) {
      const message =
        typeof fields.message === 'string' && fields.message
          ? fields.message
          : res.statusText || '请求失败'
      throw new ApiError(
        message,
        res.status,
        body,
        rid,
        typeof fields.code === 'string' ? fields.code : undefined,
      )
    }

    return { data: body as T, requestId: rid }
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError('请求超时，请稍后重试', 0, null, requestId)
    }
    throw new ApiError('网络错误，请稍后重试', 0, null, requestId)
  } finally {
    clearTimeout(timer)
  }
}
