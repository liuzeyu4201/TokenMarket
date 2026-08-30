/** Lightweight serious/critical a11y gates without extra lockfile deps. */

export function collectA11yViolations(root: ParentNode): string[] {
  const violations: string[] = []
  root.querySelectorAll('button').forEach((el) => {
    const name =
      el.getAttribute('aria-label') ||
      el.getAttribute('title') ||
      el.textContent?.replace(/\s+/g, ' ').trim()
    if (!name) violations.push('button-missing-name')
  })
  root.querySelectorAll('input, select, textarea').forEach((el) => {
    const id = el.getAttribute('id')
    const labelled =
      el.getAttribute('aria-label') ||
      el.getAttribute('aria-labelledby') ||
      (id ? root.querySelector(`label[for="${id}"]`) : null)
    if (!labelled) violations.push('control-missing-label')
  })
  root.querySelectorAll('[role="dialog"]').forEach((el) => {
    if (el.getAttribute('aria-modal') !== 'true') violations.push('dialog-missing-modal')
    if (!el.getAttribute('aria-labelledby') && !el.getAttribute('aria-label')) {
      violations.push('dialog-missing-title')
    }
  })
  root.querySelectorAll('img').forEach((el) => {
    if (el.getAttribute('alt') === null) violations.push('img-missing-alt')
  })
  return violations
}

export function assertNoSeriousA11y(root: ParentNode): void {
  const v = collectA11yViolations(root)
  if (v.length) {
    throw new Error(`a11y serious/critical: ${v.join(', ')}`)
  }
}
