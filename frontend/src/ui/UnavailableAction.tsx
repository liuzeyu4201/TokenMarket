export function UnavailableAction({ label }: { label: string }) {
  return (
    <button type="button" className="secondary" disabled aria-disabled="true" title="即将开放">
      {label}（即将开放）
    </button>
  )
}

export default UnavailableAction
