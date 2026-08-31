import { FormEvent, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { listWorkbench, setCapacity, submitQuote, type WorkbenchCard } from '../api/v1/workbench'
import { Button } from '../ui/Button'
import { FormField } from '../ui/FormField'
import { Notice } from '../ui/Notice'
import { PageState } from '../ui/PageState'
import { Table } from '../ui/Table'

export function Supply() {
  const auth = useAuth()
  const [items, setItems] = useState<WorkbenchCard[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [bps, setBps] = useState<Record<string, string>>({})
  const [cap, setCap] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const workspace = auth.session?.workspace

  const refresh = () => listWorkbench().then(setItems)

  useEffect(() => {
    if (auth.status !== 'authenticated' || workspace !== 'seller') return
    let cancelled = false
    void listWorkbench()
      .then((rows) => {
        if (!cancelled) setItems(rows)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '无法加载工作台')
        setItems([])
      })
    return () => {
      cancelled = true
    }
  }, [auth.status, workspace])

  if (auth.status === 'checking') {
    return <PageState kind="loading" />
  }
  if (workspace !== 'seller') {
    return (
      <div className="card" data-testid="supply-forbidden">
        <h1>供给工作台</h1>
        <PageState kind="forbidden" detail="请切换到卖家工作区。" />
      </div>
    )
  }

  const onQuote = async (e: FormEvent, id: string) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await submitQuote(id, Number(bps[id]), auth.getCsrfToken())
      setBps((m) => ({ ...m, [id]: '' }))
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '报价失败')
    } finally {
      setBusy(false)
    }
  }

  const onCap = async (e: FormEvent, id: string) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await setCapacity(id, Number(cap[id]), auth.getCsrfToken())
      setCap((m) => ({ ...m, [id]: '' }))
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '容量更新失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" data-testid="supply-page">
      <h1>供给工作台</h1>
      <p className="hint">报价仅影响新请求。测试收益不可提现。工作台不含买家身份或平台倍率。</p>
      {error ? (
        <Notice tone="error" data-testid="supply-error">
          {error}
        </Notice>
      ) : null}
      {items === null ? (
        <PageState kind="loading" />
      ) : (
        <Table
          caption="我的供给"
          headers={[
            '连接',
            '健康',
            '生命周期',
            '报价',
            '容量',
            '接新请求',
            '已结算',
            '未决',
            '操作',
          ]}
          empty="还没有连接。请先在提供商连接中登记。"
          rows={items.map((row) => [
            <span key={`${row.connection_id}-id`} data-testid="supply-connection">
              {row.provider} / {row.supply_mode}
            </span>,
            row.health_state,
            row.lifecycle_state,
            row.quote ? `${row.quote.multiplier_bps} bps` : '未报价',
            row.declared_capacity ?? '未声明',
            row.admits_new ? '是' : '否',
            String(row.earnings.settled_minor),
            row.earnings.unresolved_count
              ? `${row.earnings.unresolved_count}（${row.earnings.unresolved_reasons.join(', ')}）`
              : '0',
            <div key={`${row.connection_id}-ops`}>
              <form onSubmit={(e) => void onQuote(e, row.connection_id)}>
                <FormField
                  id={`quote-${row.connection_id}`}
                  label="报价倍率 bps"
                  value={bps[row.connection_id] ?? ''}
                  onChange={(ev) => setBps((m) => ({ ...m, [row.connection_id]: ev.target.value }))}
                  hint={`${row.bounds.seller_quote_min_bps}–${row.bounds.seller_quote_max_bps}`}
                />
                <Button type="submit" loading={busy}>
                  提交报价
                </Button>
              </form>
              <form onSubmit={(e) => void onCap(e, row.connection_id)}>
                <FormField
                  id={`cap-${row.connection_id}`}
                  label="声明容量"
                  value={cap[row.connection_id] ?? ''}
                  onChange={(ev) => setCap((m) => ({ ...m, [row.connection_id]: ev.target.value }))}
                />
                <Button type="submit" loading={busy}>
                  更新容量
                </Button>
              </form>
            </div>,
          ])}
        />
      )}
    </div>
  )
}

export default Supply
