import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AppShell } from './layouts/AppShell'
import { Home } from './pages/Home'
import { NotFound } from './pages/NotFound'
import { Register } from './pages/Register'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Home />} />
          <Route path="register" element={<Register />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('app shell routes', () => {
  it('shows home placeholder not register form on /', () => {
    renderAt('/')
    expect(screen.getByText(/平台首页占位/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '注册' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: '注册' }).length).toBeGreaterThanOrEqual(1)
  })

  it('shows register form on /register', () => {
    renderAt('/register')
    expect(screen.getByLabelText('手机号')).toBeInTheDocument()
    expect(screen.getByLabelText('昵称')).toBeInTheDocument()
    expect(screen.getByLabelText('角色')).toBeInTheDocument()
  })

  it('shows not found for unknown path', () => {
    renderAt('/no-such-page')
    expect(screen.getByText(/页面未找到或暂未开放/)).toBeInTheDocument()
  })
})
