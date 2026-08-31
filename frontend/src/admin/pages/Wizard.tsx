import { FormEvent, useState } from 'react'
import { Button } from '../../ui/Button'
import { FormField } from '../../ui/FormField'
import { Notice } from '../../ui/Notice'
import { cancelWizard, confirmWizard, startWizard, type Wizard } from '../api'

export function WizardPage() {
  const [kind, setKind] = useState('force_logout')
  const [target, setTarget] = useState('')
  const [reason, setReason] = useState('')
  const [wizard, setWizard] = useState<Wizard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const onStart = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      setWizard(await startWizard(kind, target, reason))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '无法启动向导')
    } finally {
      setBusy(false)
    }
  }

  const onConfirm = async () => {
    if (!wizard) return
    setBusy(true)
    try {
      setWizard(await confirmWizard(wizard.wizard_id, reason))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '确认失败')
    } finally {
      setBusy(false)
    }
  }

  const onCancel = async () => {
    if (!wizard) return
    setBusy(true)
    try {
      setWizard(await cancelWizard(wizard.wizard_id))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '取消失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" data-testid="admin-wizard">
      <h1>高风险向导</h1>
      <p>取消或超时不会留下半完成状态。成功结果可用 request ID 追踪。</p>
      {error ? (
        <Notice tone="error">
          <p>{error}</p>
        </Notice>
      ) : null}
      <form onSubmit={(e) => void onStart(e)}>
        <FormField
          id="wiz-kind"
          label="类型"
          as="select"
          value={kind}
          onChange={(ev) => setKind(ev.target.value)}
        >
          <option value="force_logout">强退会话</option>
          <option value="replace_dedicated">专享更换</option>
          <option value="reverse">冲正</option>
        </FormField>
        <FormField
          id="wiz-target"
          label="目标"
          value={target}
          onChange={(ev) => setTarget(ev.target.value)}
          required
        />
        <FormField
          id="wiz-reason"
          label="原因"
          value={reason}
          onChange={(ev) => setReason(ev.target.value)}
          required
        />
        <Button type="submit" loading={busy}>
          开始
        </Button>
      </form>
      {wizard ? (
        <section data-testid="wizard-panel">
          <p data-testid="wizard-status">状态：{wizard.status}</p>
          <ul>
            {wizard.impact.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {wizard.request_id ? (
            <p data-testid="wizard-request-id">request ID：{wizard.request_id}</p>
          ) : null}
          {wizard.status === 'pending' ? (
            <>
              <Button type="button" onClick={() => void onConfirm()} loading={busy}>
                确认执行
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void onCancel()}
                loading={busy}
              >
                取消
              </Button>
            </>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
