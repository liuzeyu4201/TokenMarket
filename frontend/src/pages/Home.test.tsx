import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { Home } from './Home'
import { assertNoSeriousA11y } from '../ui/assertA11y'

describe('Home public site', () => {
  it('explains three protocols, shared/dedicated, and test credits', () => {
    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )
    expect(screen.getByText(/平台首页占位/)).toBeInTheDocument()
    expect(screen.getByText(/OpenAI/)).toBeInTheDocument()
    expect(screen.getByText(/Anthropic/)).toBeInTheDocument()
    expect(screen.getByText(/Vertex/)).toBeInTheDocument()
    expect(screen.getByText(/透传/)).toBeInTheDocument()
    expect(screen.getByText(/共享/)).toBeInTheDocument()
    expect(screen.getByText(/专享/)).toBeInTheDocument()
    expect(screen.getByText(/测试额度/)).toBeInTheDocument()
    expect(screen.getByText(/不可购买/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /创建买家 Project/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /接入卖家连接/ })).toBeDisabled()
    assertNoSeriousA11y(container)
  })

  it('does not submit unavailable business actions', async () => {
    const user = userEvent.setup()
    let submitted = false
    const { container } = render(
      <MemoryRouter>
        <div
          onSubmit={() => {
            submitted = true
          }}
        >
          <Home />
        </div>
      </MemoryRouter>,
    )
    await user.click(screen.getByRole('button', { name: /创建买家 Project/ }))
    expect(submitted).toBe(false)
    assertNoSeriousA11y(container)
  })
})
