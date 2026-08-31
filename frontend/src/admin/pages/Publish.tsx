import { FormEvent, useState } from 'react'
import { Button } from '../../ui/Button'
import { FormField } from '../../ui/FormField'
import { Notice } from '../../ui/Notice'
import { approveDraft, createDraft, diffDraft, publishDraft, simulateDraft } from '../api'

export function Publish() {
  const [kind, setKind] = useState<'price' | 'route'>('price')
  const [buyer, setBuyer] = useState('9500')
  const [seller, setSeller] = useState('8000')
  const [reason, setReason] = useState('')
  const [diff, setDiff] = useState<string>('')
  const [sim, setSim] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [draftId, setDraftId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const draft = await createDraft(kind, {
        buyer_bps: Number(buyer),
        seller_max_bps: Number(seller),
        weights: { health: 40, latency: 30, price: 30 },
      })
      setDraftId(draft.draft_id)
      const d = await diffDraft(draft.draft_id)
      setDiff(JSON.stringify(d.changes, null, 2))
      const s = await simulateDraft(draft.draft_id)
      setSim(s.ok ? `仿真通过，线上版本 ${s.active_version}` : `仿真失败：${s.reason}`)
      if (s.ok) {
        await approveDraft(draft.draft_id)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '发布准备失败')
    } finally {
      setBusy(false)
    }
  }

  const onPublish = async () => {
    if (!draftId) return
    setBusy(true)
    try {
      const out = await publishDraft(draftId, reason)
      setSim(`已发布版本 ${out.version}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '发布失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" data-testid="admin-publish">
      <h1>配置发布</h1>
      <p>草稿 → 差异 → 仿真 → 审批 → 发布。不能直接修改线上版本。</p>
      {error ? (
        <Notice tone="error">
          <p>{error}</p>
        </Notice>
      ) : null}
      <form onSubmit={(e) => void run(e)}>
        <FormField
          id="cfg-kind"
          label="类型"
          as="select"
          value={kind}
          onChange={(ev) => setKind(ev.target.value as 'price' | 'route')}
        >
          <option value="price">价格</option>
          <option value="route">路由</option>
        </FormField>
        <FormField
          id="cfg-buyer"
          label="buyer_bps"
          value={buyer}
          onChange={(ev) => setBuyer(ev.target.value)}
        />
        <FormField
          id="cfg-seller"
          label="seller_max_bps"
          value={seller}
          onChange={(ev) => setSeller(ev.target.value)}
        />
        <Button type="submit" loading={busy}>
          生成差异并仿真
        </Button>
      </form>
      {diff ? (
        <section data-testid="config-diff">
          <h2>语义差异</h2>
          <pre>{diff}</pre>
        </section>
      ) : null}
      {sim ? (
        <Notice tone={sim.startsWith('仿真失败') ? 'error' : 'info'}>
          <p data-testid="config-sim">{sim}</p>
        </Notice>
      ) : null}
      <FormField
        id="cfg-reason"
        label="发布原因"
        value={reason}
        onChange={(ev) => setReason(ev.target.value)}
      />
      <Button
        type="button"
        onClick={() => void onPublish()}
        disabled={!draftId || !reason}
        loading={busy}
      >
        发布
      </Button>
    </div>
  )
}
