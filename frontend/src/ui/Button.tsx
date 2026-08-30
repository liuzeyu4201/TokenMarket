import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'link'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  loading?: boolean
}

const CLASS: Record<Variant, string> = {
  primary: 'primary',
  secondary: 'secondary',
  link: 'link-button',
}

export function Button({
  variant = 'primary',
  loading = false,
  disabled,
  children,
  className,
  ...rest
}: ButtonProps) {
  const busy = loading || rest['aria-busy']
  return (
    <button
      {...rest}
      className={[CLASS[variant], className].filter(Boolean).join(' ')}
      disabled={disabled || loading}
      aria-busy={busy ? true : undefined}
      data-variant={variant}
    >
      {loading ? '处理中…' : children}
    </button>
  )
}

export default Button
