import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type Ref,
  type SelectHTMLAttributes,
} from 'react'

interface Shared {
  id: string
  label: string
  hint?: string
  error?: string
}

type InputProps = Shared &
  Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> & {
    as?: 'input'
  }

type SelectProps = Shared &
  Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> & {
    as: 'select'
    children: ReactNode
  }

export type FormFieldProps = InputProps | SelectProps

function FieldChrome({
  id,
  label,
  hint,
  error,
  className,
  control,
}: Shared & { className?: string; control: ReactNode }) {
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-err` : undefined
  return (
    <div className={['form-field', className].filter(Boolean).join(' ')}>
      <label htmlFor={id}>{label}</label>
      {control}
      {hint ? (
        <div id={hintId} className="field-help">
          {hint}
        </div>
      ) : null}
      {error ? (
        <div id={errorId} className="field-error" role="alert">
          {error}
        </div>
      ) : null}
    </div>
  )
}

export const FormField = forwardRef<HTMLInputElement | HTMLSelectElement, FormFieldProps>(
  function FormField(props, ref) {
    const hintId = props.hint ? `${props.id}-hint` : undefined
    const errorId = props.error ? `${props.id}-err` : undefined
    const describedBy =
      [props['aria-describedby'], hintId, errorId].filter(Boolean).join(' ') || undefined
    const invalid = props.error ? true : props['aria-invalid']

    if (props.as === 'select') {
      const { id, label, hint, error, className, children, ...rest } = props
      const dom = rest as SelectHTMLAttributes<HTMLSelectElement>
      return (
        <FieldChrome
          id={id}
          label={label}
          hint={hint}
          error={error}
          className={className}
          control={
            <select
              {...dom}
              ref={ref as Ref<HTMLSelectElement>}
              id={id}
              aria-invalid={invalid}
              aria-describedby={describedBy}
            >
              {children}
            </select>
          }
        />
      )
    }

    const { id, label, hint, error, className, ...rest } = props
    const dom = rest as InputHTMLAttributes<HTMLInputElement>
    return (
      <FieldChrome
        id={id}
        label={label}
        hint={hint}
        error={error}
        className={className}
        control={
          <input
            {...dom}
            ref={ref as Ref<HTMLInputElement>}
            id={id}
            aria-invalid={invalid}
            aria-describedby={describedBy}
          />
        }
      />
    )
  },
)

export default FormField
