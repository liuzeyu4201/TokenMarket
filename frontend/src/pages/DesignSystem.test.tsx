import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { DesignSystem } from './DesignSystem'
import { assertNoSeriousA11y } from '../ui/assertA11y'

describe('DesignSystem catalog', () => {
  it('lists required component states', async () => {
    const user = userEvent.setup()
    const { container } = render(<DesignSystem />)
    expect(screen.getByRole('heading', { name: '组件目录' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '默认' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '禁用' })).toBeDisabled()
    expect(screen.getByLabelText('示例字段')).toBeInTheDocument()
    expect(screen.getByLabelText('错误字段')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('信息')).toBeInTheDocument()
    expect(screen.getByTestId('page-state-offline')).toBeInTheDocument()
    expect(screen.getByTestId('page-state-rate_limited')).toBeInTheDocument()
    expect(screen.getByTestId('page-state-forbidden')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '打开弹窗' }))
    expect(screen.getByRole('dialog', { name: '目录弹窗' })).toHaveAttribute('aria-modal', 'true')
    assertNoSeriousA11y(container)
  })
})
