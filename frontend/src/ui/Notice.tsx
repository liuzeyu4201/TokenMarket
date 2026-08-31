import { forwardRef, type HTMLAttributes, type ReactNode } from 'react'

export type NoticeTone = 'info' | 'error' | 'success' | 'loading'

const CLASS: Record<NoticeTone, string> = {
  info: 'neutral-accept',
  error: 'form-error',
  success: 'success-box',
  loading: 'status-loading',
}

export const Notice = forwardRef<
  HTMLDivElement,
  { tone?: NoticeTone; children: ReactNode } & HTMLAttributes<HTMLDivElement>
>(function Notice({ tone = 'info', children, ...rest }, ref) {
  const alert = tone === 'error'
  return (
    <div
      {...rest}
      ref={ref}
      className={[CLASS[tone], rest.className].filter(Boolean).join(' ')}
      data-tone={tone}
      role={rest.role ?? (alert ? 'alert' : 'status')}
      aria-live={alert ? undefined : (rest['aria-live'] ?? 'polite')}
      aria-busy={tone === 'loading' ? true : undefined}
    >
      {children}
    </div>
  )
})

export default Notice
