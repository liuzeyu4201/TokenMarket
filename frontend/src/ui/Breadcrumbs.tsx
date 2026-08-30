import { Link } from 'react-router-dom'

export interface Crumb {
  label: string
  to?: string
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  if (items.length === 0) return null
  return (
    <nav aria-label="面包屑" className="breadcrumbs">
      <ol>
        {items.map((item, i) => {
          const current = i === items.length - 1
          return (
            <li key={`${item.label}-${i}`}>
              {current || !item.to ? (
                <span aria-current={current ? 'page' : undefined}>{item.label}</span>
              ) : (
                <Link to={item.to}>{item.label}</Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export default Breadcrumbs
