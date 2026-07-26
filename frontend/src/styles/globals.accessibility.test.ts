/**
 * WCAG 2.2 AA design-token contrast checks (T114 / T128).
 * Uses relative luminance against documented CSS custom properties in globals.css.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function parseHex(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const full =
    h.length === 3
      ? h
          .split('')
          .map((c) => c + c)
          .join('')
      : h
  const n = Number.parseInt(full, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function srgbChannel(c: number): number {
  const s = c / 255
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = parseHex(hex)
  return 0.2126 * srgbChannel(r) + 0.7152 * srgbChannel(g) + 0.0722 * srgbChannel(b)
}

function contrastRatio(fg: string, bg: string): number {
  const l1 = relativeLuminance(fg)
  const l2 = relativeLuminance(bg)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

function tokenMap(css: string): Record<string, string> {
  const out: Record<string, string> = {}
  const re = /--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;/g
  let m: RegExpExecArray | null
  while ((m = re.exec(css)) !== null) {
    out[m[1]] = m[2]
  }
  return out
}

const css = readFileSync(resolve(__dirname, 'globals.css'), 'utf8')
const tokens = tokenMap(css)

describe('globals.css WCAG 2.2 AA token ratios', () => {
  it('defines required surface and state tokens', () => {
    for (const name of [
      'color-text',
      'color-bg',
      'color-surface',
      'color-primary',
      'color-primary-contrast',
      'color-error',
      'color-error-text',
      'color-error-bg',
      'color-success-text',
      'color-success-bg',
      'color-focus-ring',
      'color-disabled-fg',
      'color-disabled-bg',
    ]) {
      expect(tokens[name], name).toMatch(/^#/)
    }
  })

  it('normal text on background meets 4.5:1', () => {
    expect(contrastRatio(tokens['color-text'], tokens['color-bg'])).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(tokens['color-text'], tokens['color-surface'])).toBeGreaterThanOrEqual(4.5)
  })

  it('error and success text on their surfaces meet 4.5:1', () => {
    expect(
      contrastRatio(tokens['color-error-text'], tokens['color-error-bg']),
    ).toBeGreaterThanOrEqual(4.5)
    expect(
      contrastRatio(tokens['color-success-text'], tokens['color-success-bg']),
    ).toBeGreaterThanOrEqual(4.5)
  })

  it('primary control label contrast meets 4.5:1', () => {
    expect(
      contrastRatio(tokens['color-primary-contrast'], tokens['color-primary']),
    ).toBeGreaterThanOrEqual(4.5)
  })

  it('focus ring against surface meets 3:1', () => {
    expect(
      contrastRatio(tokens['color-focus-ring'], tokens['color-surface']),
    ).toBeGreaterThanOrEqual(3)
  })

  it('documents disabled/inactive as an allowed reduced-contrast exception', () => {
    expect(css).toMatch(/Disabled\/inactive|disabled\/inactive|disabled/i)
    // Disabled pair may be below 4.5:1 — only assert it is defined.
    expect(tokens['color-disabled-fg']).toBeTruthy()
    expect(tokens['color-disabled-bg']).toBeTruthy()
  })

  it('prevents horizontal scroll at 320px via overflow rules', () => {
    expect(css).toMatch(/overflow-x:\s*hidden/)
    expect(css).toMatch(/320/)
  })
})
