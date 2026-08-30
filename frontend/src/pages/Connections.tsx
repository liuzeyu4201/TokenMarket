import { FormEvent, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import {
  createConnection,
  deleteConnection,
  listConnections,
  replaceConnectionCredential,
  lifecycleAction,
  verifyConnection,
  type ProviderConnection,
} from '../api/v1/connections'
import type { ProjectMode, ProtocolName } from '../api/v1/projects'
import { Button } from '../ui/Button'
import { FormField } from '../ui/FormField'
import { Notice } from '../ui/Notice'
import { PageState } from '../ui/PageState'
import { Table } from '../ui/Table'

const PROVIDERS: ProtocolName[] = ['openai', 'anthropic', 'vertex']
const MODES: ProjectMode[] = ['shared', 'dedicated']

const PROVIDER_LABEL: Record<ProtocolName, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  vertex: 'Vertex',
}

const HEALTH_LABEL: Record<string, string> = {
  unknown: '未知',
  healthy: '健康',
  degraded: '降级',
  unhealthy: '不健康',
}

const LIFE_LABEL: Record<string, string> = {
  draft: '草稿',
  verified: '已验证',
  listed: '已上架',
  bound: '已绑定',
  paused: '已暂停',
  draining: '排空中',
  retired: '已退役',
}

export function Connections() {
  const auth = useAuth()
  const [items, setItems] = useState<ProviderConnection[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [provider, setProvider] = useState<ProtocolName>('openai')
  const [mode, setMode] = useState<ProjectMode>('shared')
  const [secret, setSecret] = useState('')
  const [projectNumber, setProjectNumber] = useState('')
  const [location, setLocation] = useState('')
  const [busy, setBusy] = useState(false)
  const [replaceSecret, setReplaceSecret] = useState<Record<string, string>>({})

  const workspace = auth.session?.workspace

  const refresh = () =>
    listConnections().then((rows) => {
      setItems(rows)
    })

  useEffect(() => {
    if (auth.status !== 'authenticated') return
    if (workspace !== 'seller') return
    let cancelled = false
    void listConnections()
      .then((rows) => {
        if (!cancelled) setItems(rows)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '无法加载连接')
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
      <div className="card" data-testid="connections-forbidden">
        <h1>提供商连接</h1>
        <PageState kind="forbidden" detail="请切换到卖家工作区后再管理连接凭据。" />
      </div>
    )
  }

  const onCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const credential: CreateBodyCredential = { secret }
      if (provider === 'vertex') {
        credential.project_number = projectNumber
        credential.location = location
      }
      await createConnection({ provider, supply_mode: mode, credential }, auth.getCsrfToken())
      setSecret('')
      setProjectNumber('')
      setLocation('')
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  const onReplace = async (row: ProviderConnection) => {
    const next = (replaceSecret[row.connection_id] || '').trim()
    if (!next || busy) return
    setBusy(true)
    setError(null)
    try {
      await replaceConnectionCredential(
        row.connection_id,
        { secret: next, expected_version: row.credential_version },
        auth.getCsrfToken(),
      )
      setReplaceSecret((cur) => ({ ...cur, [row.connection_id]: '' }))
      await refresh()
    } catch (err: unknown) {
      const code = err instanceof ApiError ? err.code : undefined
      if (code === 'VERSION_CONFLICT') {
        setError('凭据版本冲突，请刷新后重试')
      } else {
        setError(err instanceof Error ? err.message : '替换失败')
      }
    } finally {
      setBusy(false)
    }
  }

  const onLife = async (
    row: ProviderConnection,
    action: 'list' | 'pause' | 'resume' | 'drain' | 'retire',
  ) => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await lifecycleAction(row.connection_id, action, auth.getCsrfToken())
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const onVerify = async (row: ProviderConnection) => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await verifyConnection(row.connection_id, auth.getCsrfToken())
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '验证失败')
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async (row: ProviderConnection) => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await deleteConnection(row.connection_id, auth.getCsrfToken())
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '删除失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" data-testid="connections-page">
      <h1>提供商连接</h1>
      <p>凭据提交后立即加密，页面与接口都不会回显明文。请自行保管原始密钥。</p>
      {error ? (
        <Notice tone="error">
          <p>{error}</p>
        </Notice>
      ) : null}
      <form onSubmit={(e) => void onCreate(e)} data-testid="connection-create-form">
        <FormField
          id="connection-provider"
          label="提供商"
          as="select"
          value={provider}
          onChange={(ev) => setProvider(ev.target.value as ProtocolName)}
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {PROVIDER_LABEL[p]}
            </option>
          ))}
        </FormField>
        <FormField
          id="connection-mode"
          label="供给模式"
          as="select"
          value={mode}
          onChange={(ev) => setMode(ev.target.value as ProjectMode)}
        >
          {MODES.map((m) => (
            <option key={m} value={m}>
              {m === 'shared' ? '共享' : '专享'}
            </option>
          ))}
        </FormField>
        <FormField
          id="connection-secret"
          label="凭据"
          type="password"
          autoComplete="new-password"
          value={secret}
          onChange={(ev) => setSecret(ev.target.value)}
          required
          hint="提交后不可回读"
        />
        {provider === 'vertex' ? (
          <>
            <FormField
              id="connection-project-number"
              label="Vertex project_number"
              value={projectNumber}
              onChange={(ev) => setProjectNumber(ev.target.value)}
              required
            />
            <FormField
              id="connection-location"
              label="Vertex location"
              value={location}
              onChange={(ev) => setLocation(ev.target.value)}
              required
            />
          </>
        ) : null}
        <Button type="submit" loading={busy} disabled={!secret.trim()}>
          创建连接
        </Button>
      </form>
      {items === null ? (
        <PageState kind="loading" />
      ) : (
        <Table
          caption="已登记的提供商连接"
          headers={['提供商', '模式', '指纹', '健康', '生命周期', '版本', '操作']}
          empty="还没有连接。"
          rows={items.map((row) => [
            PROVIDER_LABEL[row.provider],
            row.supply_mode === 'shared' ? '共享' : '专享',
            <span key={row.connection_id} data-testid="connection-fingerprint">
              {row.credential_fingerprint}
            </span>,
            <span key={`${row.connection_id}-health`} data-testid="connection-health">
              {HEALTH_LABEL[row.health_state || 'unknown'] ?? row.health_state}
            </span>,
            <span key={`${row.connection_id}-life`} data-testid="connection-lifecycle">
              {LIFE_LABEL[row.lifecycle_state || 'draft'] ?? row.lifecycle_state}
            </span>,
            String(row.credential_version),
            <div key={`${row.connection_id}-ops`}>
              <FormField
                id={`replace-${row.connection_id}`}
                label="新凭据"
                type="password"
                autoComplete="new-password"
                value={replaceSecret[row.connection_id] || ''}
                onChange={(ev) =>
                  setReplaceSecret((cur) => ({
                    ...cur,
                    [row.connection_id]: ev.target.value,
                  }))
                }
              />
              {row.lifecycle_state === 'verified' ? (
                <Button type="button" variant="secondary" onClick={() => void onLife(row, 'list')}>
                  上架
                </Button>
              ) : null}
              {row.lifecycle_state === 'listed' || row.lifecycle_state === 'bound' ? (
                <Button type="button" variant="secondary" onClick={() => void onLife(row, 'pause')}>
                  暂停
                </Button>
              ) : null}
              {row.lifecycle_state === 'paused' ? (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void onLife(row, 'resume')}
                >
                  恢复
                </Button>
              ) : null}
              <Button type="button" variant="secondary" onClick={() => void onVerify(row)}>
                立即复验
              </Button>
              <Button type="button" variant="secondary" onClick={() => void onReplace(row)}>
                整体替换
              </Button>
              <Button type="button" variant="secondary" onClick={() => void onDelete(row)}>
                删除
              </Button>
            </div>,
          ])}
        />
      )}
    </div>
  )
}

type CreateBodyCredential = {
  secret: string
  project_number?: string
  location?: string
}

export default Connections
