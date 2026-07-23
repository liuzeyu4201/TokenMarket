const DEFAULT_TIMEOUT_MS = 10_000

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
    readonly requestId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<{ data: T; requestId: string }> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, headers, ...rest } = init
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const requestId = crypto.randomUUID()
  try {
    const res = await fetch(`${getApiBaseUrl()}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': requestId,
        ...(headers as Record<string, string>),
      },
    })
    const body = (await res.json()) as T & { request_id?: string; message?: string }
    const rid =
      res.headers.get('X-Request-ID') ??
      (typeof body === 'object' && body && 'request_id' in body
        ? String((body as { request_id?: string }).request_id)
        : requestId)
    if (!res.ok) {
      throw new ApiError(
        (body as { message?: string }).message ?? res.statusText,
        res.status,
        body,
        rid,
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
