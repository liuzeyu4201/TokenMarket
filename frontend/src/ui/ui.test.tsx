import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './Button'
import { FormField } from './FormField'
import { Notice } from './Notice'
import { Dialog } from './Dialog'
import { Table } from './Table'
import { PageState } from './PageState'
import { ErrorBoundary } from './ErrorBoundary'
import { Breadcrumbs } from './Breadcrumbs'
import { UnavailableAction } from './UnavailableAction'
import { assertNoSeriousA11y } from './assertA11y'

function Boom() {
  throw new Error('boom')
  return null
}

function DialogHarness() {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <Button type="button" onClick={() => setOpen(true)}>
        打开说明
      </Button>
      <Dialog open={open} title="示例弹窗" onClose={() => setOpen(false)}>
        <p>弹窗内容</p>
      </Dialog>
    </div>
  )
}

describe('foundation components', () => {
  it('Button exposes default, disabled and loading states', () => {
    const { container, rerender } = render(<Button>保存</Button>)
    expect(screen.getByRole('button', { name: '保存' })).toHaveAttribute('data-variant', 'primary')
    rerender(
      <Button disabled loading>
        保存
      </Button>,
    )
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true')
    assertNoSeriousA11y(container)
  })

  it('FormField wires label, hint and error', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <FormField id="nick" label="昵称" hint="1–50 字" error="请填写昵称" />,
    )
    const input = screen.getByLabelText('昵称')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('请填写昵称')).toBeInTheDocument()
    await user.click(input)
    expect(input).toHaveFocus()
    assertNoSeriousA11y(container)
  })

  it('Notice tones cover info error success loading', () => {
    const { rerender, container } = render(<Notice tone="info">提示</Notice>)
    expect(screen.getByRole('status')).toHaveAttribute('data-tone', 'info')
    rerender(<Notice tone="error">失败</Notice>)
    expect(screen.getByRole('alert')).toHaveAttribute('data-tone', 'error')
    rerender(<Notice tone="success">完成</Notice>)
    rerender(<Notice tone="loading">加载</Notice>)
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
    assertNoSeriousA11y(container)
  })

  it('Dialog traps focus and restores it on close', async () => {
    const user = userEvent.setup()
    const { container } = render(<DialogHarness />)
    const opener = screen.getByRole('button', { name: '打开说明' })
    await user.click(opener)
    const dialog = screen.getByRole('dialog', { name: '示例弹窗' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(opener).toHaveFocus()
    assertNoSeriousA11y(container)
  })

  it('Table has caption and empty state', () => {
    const { container } = render(
      <Table caption="组件状态" headers={['状态']} rows={[]} empty="暂无数据" />,
    )
    expect(screen.getByText('组件状态')).toBeInTheDocument()
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
    assertNoSeriousA11y(container)
  })

  it('PageState covers required kinds', () => {
    const kinds = ['loading', 'empty', 'error', 'forbidden', 'rate_limited', 'offline'] as const
    for (const kind of kinds) {
      const { unmount, container } = render(<PageState kind={kind} />)
      expect(screen.getByTestId(`page-state-${kind}`)).toBeInTheDocument()
      assertNoSeriousA11y(container)
      unmount()
    }
  })

  it('ErrorBoundary shows recover control', async () => {
    const user = userEvent.setup()
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { container } = render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('page-state-error')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重试' }))
    spy.mockRestore()
    assertNoSeriousA11y(container)
  })

  it('Breadcrumbs mark the current page', () => {
    const { container } = render(
      <MemoryRouter>
        <Breadcrumbs items={[{ label: '首页', to: '/' }, { label: '工作台' }]} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('navigation', { name: '面包屑' })).toBeInTheDocument()
    expect(screen.getByText('工作台')).toHaveAttribute('aria-current', 'page')
    assertNoSeriousA11y(container)
  })

  it('UnavailableAction cannot be submitted', async () => {
    const user = userEvent.setup()
    const { container } = render(<UnavailableAction label="创建 Project" />)
    const btn = screen.getByRole('button', { name: /创建 Project/ })
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('title', '即将开放')
    await user.click(btn)
    assertNoSeriousA11y(container)
  })
})
