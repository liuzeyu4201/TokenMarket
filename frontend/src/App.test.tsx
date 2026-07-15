import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App smoke tests', () => {
  it('renders a minimal accessible page without crashing', () => {
    const { container } = render(<App />)
    expect(container.querySelector('main, [role="main"]')).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy()
  })

  it('displays version information', () => {
    render(<App />)
    const version = screen.getByTestId('app-version')
    expect(version.textContent).toMatch(/\d+\.\d+\.\d+/)
  })

  it('does not expose business interactions', () => {
    render(<App />)
    const body = document.body.textContent?.toLowerCase() ?? ''
    expect(body).not.toContain('buy')
    expect(body).not.toContain('sell')
    expect(body).not.toContain('provider')
    expect(body).not.toContain('key')
    expect(body).not.toContain('billing')
    expect(body).not.toContain('meter')
  })

  it('does not render secrets or environment values', () => {
    render(<App />)
    const body = document.body.textContent ?? ''
    expect(body).not.toMatch(/sk-[a-zA-Z0-9]{20,}/)
    expect(body).not.toMatch(/password/i)
    expect(body).not.toMatch(/token=/i)
  })
})
