import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Button } from '../../ui/Button'
import { FormField } from '../../ui/FormField'
import { Notice } from '../../ui/Notice'
import { PageState } from '../../ui/PageState'
import { Table } from '../../ui/Table'
import { exportOpsItem, getOpsItem, listOps, type OpsItem, type OpsKind } from '../api'

const KINDS: OpsKind[] = [
  'user',
  'session',
  'connection',
  'project',
  'price',
  'route',
  'ledger',
  'alert',
  'audit',
]

function healthLabel(item: OpsItem): string {
  if (item.freshness === 'stale' || item.freshness === 'unknown' || item.health === 'unknown') {
    return '未知（过期）'
  }
  if (item.health === 'healthy') return '健康'
  if (item.health === 'degraded') return '降级'
  if (item.health === 'unhealthy') return '不健康'
  return String(item.status ?? item.state ?? '—')
}

export function Catalog() {
  const { kind = 'connection', id } = useParams<{ kind: OpsKind; id?: string }>()
  const [params, setParams] = useSearchParams()
  const cursor = params.get('cursor') ?? ''
  const q = params.get('q') ?? ''
  const [items, setItems] = useState<OpsItem[] | null>(null)
  const [next, setNext] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<string>('')
  const [query, setQuery] = useState(q)

  const safeKind: OpsKind = KINDS.includes(kind as OpsKind) ? (kind as OpsKind) : 'connection'

  useEffect(() => {
    let cancelled = false
    void listOps(safeKind, { cursor, q, limit: 50 })
      .then((page) => {
        if (cancelled) return
        setItems(page.items)
        setNext(page.next_cursor)
        setTotal(page.total)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '无法加载列表')
        setItems([])
      })
    return () => {
      cancelled = true
    }
  }, [safeKind, cursor, q])

  useEffect(() => {
    if (!id) return
    let cancelled = false
    void getOpsItem(safeKind, id)
      .then(async (row) => {
        const exported = await exportOpsItem(safeKind, id)
        if (cancelled) return
        setDetail(JSON.stringify({ ...row, export: exported }, null, 2))
      })
      .catch((err: unknown) => {
        if (!cancelled) setDetail(err instanceof Error ? err.message : '无法加载详情')
      })
    return () => {
      cancelled = true
    }
  }, [safeKind, id])

  const rows = useMemo(() => {
    return (items ?? []).map((item) => [
      <Link key={item.id} to={`/admin/ops/${safeKind}/${item.id}`}>
        {item.id}
      </Link>,
      item.fingerprint ?? '—',
      <span
        key={`${item.id}-h`}
        data-testid={
          item.freshness === 'stale' || item.health === 'unknown' ? 'health-unknown' : 'health-live'
        }
      >
        {healthLabel(item)}
      </span>,
      String(item.protocol ?? item.version ?? '—'),
    ])
  }, [items, safeKind])

  const leak = detail.toLowerCase()
  const leaked = leak.includes('sk-') || leak.includes('api_key') || leak.includes('plaintext')

  return (
    <div className="card" data-testid="admin-catalog">
      <h1>运营目录</h1>
      <p>服务端分页。连接只展示指纹与健康，不含凭据明文。</p>
      {error ? (
        <Notice tone="error">
          <p>{error}</p>
        </Notice>
      ) : null}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          setParams({ q: query })
        }}
      >
        <FormField
          id="ops-q"
          label="筛选"
          value={query}
          onChange={(ev) => setQuery(ev.target.value)}
        />
        <Button type="submit" variant="secondary">
          查询
        </Button>
      </form>
      {items === null ? (
        <PageState kind="loading" />
      ) : (
        <Table
          caption={`${safeKind}（共 ${total}）`}
          headers={['编号', '指纹', '健康', '协议/版本']}
          rows={rows}
        />
      )}
      {next ? (
        <Button type="button" variant="secondary" onClick={() => setParams({ cursor: next, q })}>
          下一页
        </Button>
      ) : null}
      {id ? (
        <section data-testid="ops-detail">
          <h2>详情</h2>
          {leaked ? (
            <Notice tone="error">
              <p>导出含敏感字段，已阻止显示</p>
            </Notice>
          ) : (
            <pre>{detail}</pre>
          )}
        </section>
      ) : null}
    </div>
  )
}
