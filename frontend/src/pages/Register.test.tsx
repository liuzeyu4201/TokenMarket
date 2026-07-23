import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Register } from './Register'

const registerUser = vi.fn()

vi.mock('../api/v1/auth', () => ({
  registerUser: (...args: unknown[]) => registerUser(...args),
}))

describe('Register page', () => {
  beforeEach(() => {
    registerUser.mockReset()
  })

  it('shows client required field hints', async () => {
    const user = userEvent.setup()
    render(<Register />)
    await user.click(screen.getByRole('button', { name: '注册' }))
    expect(screen.getByText('请输入手机号')).toBeInTheDocument()
    expect(screen.getByText('请输入昵称')).toBeInTheDocument()
    expect(screen.getByText('请选择角色')).toBeInTheDocument()
  })

  it('associates labels with controls', () => {
    render(<Register />)
    expect(screen.getByLabelText('手机号')).toBeEnabled()
    expect(screen.getByLabelText('昵称')).toBeEnabled()
    expect(screen.getByLabelText('角色')).toBeEnabled()
  })

  async function fillValid(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText('手机号'), '13800138000')
    await user.type(screen.getByLabelText('昵称'), '测试')
    await user.selectOptions(screen.getByLabelText('角色'), 'buyer')
  }

  it('maps PHONE_ALREADY_REGISTERED to form error with request_id', async () => {
    const user = userEvent.setup()
    const { ApiError } = await import('../api/client')
    registerUser.mockRejectedValue(
      new ApiError('conflict', 409, {
        code: 'PHONE_ALREADY_REGISTERED',
        message: '该手机号已被注册',
        data: null,
        request_id: 'req-occupied',
        timestamp: '',
      }, 'req-occupied'),
    )
    render(<Register />)
    await fillValid(user)
    await user.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('该手机号已被注册')
      expect(screen.getByRole('alert')).toHaveTextContent('req-occupied')
    })
  })

  it('maps ACCOUNT_UNAVAILABLE distinctly', async () => {
    const user = userEvent.setup()
    const { ApiError } = await import('../api/client')
    registerUser.mockRejectedValue(
      new ApiError('unavailable', 409, {
        code: 'ACCOUNT_UNAVAILABLE',
        message: '账户不可用，请通过恢复流程处理',
        request_id: 'req-soft',
      }, 'req-soft'),
    )
    render(<Register />)
    await fillValid(user)
    await user.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('账户不可用')
    })
  })

  it('maps RATE_LIMITED', async () => {
    const user = userEvent.setup()
    const { ApiError } = await import('../api/client')
    registerUser.mockRejectedValue(
      new ApiError('limited', 429, {
        code: 'RATE_LIMITED',
        message: '请求过于频繁，请稍后再试',
        request_id: 'req-rl',
      }, 'req-rl'),
    )
    render(<Register />)
    await fillValid(user)
    await user.click(screen.getByRole('button', { name: '注册' }))
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('请求过于频繁')
    })
  })

  it('disables submit while in flight', async () => {
    const user = userEvent.setup()
    let resolvePromise: (v: unknown) => void = () => {}
    registerUser.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePromise = resolve
        }),
    )
    render(<Register />)
    await fillValid(user)
    const btn = screen.getByRole('button', { name: '注册' })
    await user.click(btn)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '提交中…' })).toBeDisabled()
    })
    resolvePromise({
      code: '0',
      message: 'success',
      data: {
        user_id: 'u1',
        role: 'buyer',
        status: 'active',
        created_at: new Date().toISOString(),
      },
      request_id: 'r1',
      timestamp: '',
    })
    await waitFor(() => {
      expect(screen.getByText('注册成功')).toBeInTheDocument()
    })
  })
})
