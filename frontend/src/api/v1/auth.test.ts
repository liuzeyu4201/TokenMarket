import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from '../client'

describe('api client timeout', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('does not auto-retry on failure', async () => {
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        calls += 1
        return new Response(JSON.stringify({ code: '0', message: 'ok', data: {}, request_id: 'r', timestamp: '' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )
    await apiFetch('/x', { method: 'POST', body: '{}' })
    expect(calls).toBe(1)
  })

  it('maps abort to timeout ApiError', async () => {
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
    await expect(apiFetch('/slow', { timeoutMs: 5 })).rejects.toBeInstanceOf(ApiError)
  })
})
