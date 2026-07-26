import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  apiFetch,
  getApiBaseUrl,
  getBrowserAuthBaseUrl,
  isDirectApiHost,
  resolveApiUrl,
} from './client'

function jsonResponse(
  body: unknown,
  init: { status?: number; headers?: Record<string, string> } = {},
): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  })
}

describe('api client same-origin auth', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it('defaults to relative empty base (no direct API host fallback)', () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    expect(getApiBaseUrl()).toBe('')
    expect(resolveApiUrl('/api/v1/auth/register')).toBe('/api/v1/auth/register')
    expect(resolveApiUrl('/api/v1/auth/sessions')).not.toContain('127.0.0.1:8000')
    expect(resolveApiUrl('/api/v1/auth/sessions')).not.toContain('localhost:8000')
  })

  it('does not fall back to direct API host when VITE_API_BASE_URL is unset', () => {
    // Vitest: unsetting leaves import.meta.env value empty/undefined → relative base
    vi.stubEnv('VITE_API_BASE_URL', undefined as unknown as string)
    const base = getApiBaseUrl()
    expect(base).toBe('')
    expect(isDirectApiHost(base)).toBe(false)
    expect(getBrowserAuthBaseUrl()).toBe('')
    const url = resolveApiUrl('/api/v1/auth/verification-challenges', base)
    expect(url).toBe('/api/v1/auth/verification-challenges')
    expect(url.startsWith('/api')).toBe(true)
    expect(url.startsWith('http')).toBe(false)
  })

  it('forbids browser auth base when configured to a direct API host', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000')
    expect(isDirectApiHost(getApiBaseUrl())).toBe(true)
    expect(() => getBrowserAuthBaseUrl()).toThrow(/same-origin relative \/api/)
  })

  it('forbids any loopback absolute host for browser auth (any port)', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:18080')
    expect(isDirectApiHost(getApiBaseUrl())).toBe(true)
    expect(() => getBrowserAuthBaseUrl()).toThrow(/same-origin relative \/api/)
  })

  it('sameOriginAuth rejects direct API base and uses relative path when unset', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe('/api/v1/auth/session')
      return jsonResponse({ code: '0', message: 'ok', data: {}, request_id: 'r' })
    })
    vi.stubGlobal('fetch', fetchMock)
    await apiFetch('/api/v1/auth/session', { method: 'GET', sameOriginAuth: true })
    expect(fetchMock).toHaveBeenCalled()
  })

  it('uses relative /api paths in fetch URL', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      expect(url).toBe('/api/v1/auth/register')
      return jsonResponse({
        code: '0',
        message: 'success',
        data: {},
        request_id: 'srv-1',
        timestamp: '2026-01-01T00:00:00Z',
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138000' }),
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/auth/register')
    expect(url).not.toMatch(/^https?:\/\/127\.0\.0\.1:8000/)
  })

  it('always sends credentials: include', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ code: '0', message: 'ok', data: null, request_id: 'r' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/v1/auth/session', { method: 'GET' })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.credentials).toBe('include')
  })

  it('sends X-Request-ID as UUID on every request', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ code: '0', message: 'ok', data: null, request_id: 'r' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/v1/ping')

    const init = fetchMock.mock.calls[0][1] as RequestInit
    const headers = init.headers as Record<string, string>
    expect(headers['X-Request-ID']).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    )
  })

  it('aborts with 10s default timeout mapped to ApiError', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        })
      }),
    )

    const pending = apiFetch('/api/v1/slow')
    const expectation = expect(pending).rejects.toMatchObject({
      name: 'ApiError',
      message: '请求超时，请稍后重试',
      status: 0,
    })
    await vi.advanceTimersByTimeAsync(10_000)
    await expectation
  })

  it('parses unified envelope errors (code, message, request_id)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          {
            code: 'RATE_LIMITED',
            message: '请求过于频繁，请稍后再试',
            data: null,
            request_id: 'req-envelope-9',
            timestamp: '2026-01-01T00:00:00Z',
          },
          {
            status: 429,
            headers: { 'X-Request-ID': 'req-header-9' },
          },
        ),
      ),
    )

    try {
      await apiFetch('/api/v1/auth/verification-challenges', { method: 'POST', body: '{}' })
      expect.unreachable('should throw')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      const apiErr = err as ApiError
      expect(apiErr.code).toBe('RATE_LIMITED')
      expect(apiErr.message).toBe('请求过于频繁，请稍后再试')
      expect(apiErr.status).toBe(429)
      expect(apiErr.requestId).toBe('req-header-9')
      expect(apiErr.body).toMatchObject({
        code: 'RATE_LIMITED',
        request_id: 'req-envelope-9',
      })
    }
  })

  it('prefers body request_id when response header is absent', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          {
            code: 'VALIDATION_ERROR',
            message: 'invalid',
            data: { errors: { phone: ['required'] } },
            request_id: 'from-body',
            timestamp: '',
          },
          { status: 400 },
        ),
      ),
    )

    await expect(apiFetch('/api/v1/auth/register', { method: 'POST', body: '{}' })).rejects.toMatchObject({
      requestId: 'from-body',
      code: 'VALIDATION_ERROR',
    })
  })
})
