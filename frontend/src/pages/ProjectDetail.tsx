import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import {
  createBinding,
  getSdkHint,
  listBindings,
  publishBinding,
  type Binding,
  type SdkHint,
} from '../api/v1/bindings'
import { issueProjectKey, listProjectKeys, type ProxyKeyPublic } from '../api/v1/proxyKeys'
import {
  MODE_CONSEQUENCE,
  deleteProject,
  getProject,
  renameProject,
  setProtocolEnabled,
  transitionProject,
  type Project,
  type ProtocolName,
} from '../api/v1/projects'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { FormField } from '../ui/FormField'
import { Notice } from '../ui/Notice'
import { PageState } from '../ui/PageState'

const PROTOCOLS: ProtocolName[] = ['openai', 'anthropic', 'vertex']

export function ProjectDetail() {
  const { projectId = '' } = useParams()
  const auth = useAuth()
  const navigate = useNavigate()
  const [item, setItem] = useState<Project | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [bindings, setBindings] = useState<Binding[]>([])
  const [hint, setHint] = useState<SdkHint | null>(null)
  const [bindProtocol, setBindProtocol] = useState<ProtocolName>('openai')
  const [bindModels, setBindModels] = useState('gpt-test')
  const [keys, setKeys] = useState<ProxyKeyPublic[]>([])
  const [onceSecret, setOnceSecret] = useState<string | null>(null)
  const [keyName, setKeyName] = useState('dev')

  useEffect(() => {
    if (auth.status !== 'authenticated' || !projectId) return
    let cancelled = false
    void Promise.all([
      getProject(projectId),
      listBindings(projectId),
      listProjectKeys(projectId).catch(() => []),
    ])
      .then(([p, rows, keyRows]) => {
        if (cancelled) return
        setItem(p)
        setName(p.display_name)
        setBindings(rows)
        setKeys(keyRows)
        setNotFound(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && (err.status === 404 || err.code === 'NOT_FOUND')) {
          setNotFound(true)
          return
        }
        setError(err instanceof Error ? err.message : '无法加载')
      })
    return () => {
      cancelled = true
    }
  }, [auth.status, projectId])

  if (auth.session?.workspace !== 'buyer') {
    return <PageState kind="forbidden" detail="请切换到买家工作区。" />
  }
  if (notFound) {
    return <PageState kind="error" detail="找不到该 Project。" />
  }
  if (!item) {
    return <PageState kind="loading" />
  }

  const refresh = async () => {
    const p = await getProject(item.project_id)
    setItem(p)
    setName(p.display_name)
  }

  const run = async (fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await fn()
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const onRename = (e: FormEvent) => {
    e.preventDefault()
    void run(() => renameProject(item.project_id, name, auth.getCsrfToken()))
  }

  return (
    <div className="card" data-testid="project-detail">
      <p>
        <Link to="/projects">返回列表</Link>
      </p>
      <h1>{item.display_name}</h1>
      <p data-testid="project-mode">模式：{item.mode === 'shared' ? '共享' : '专享'}</p>
      <Notice tone="info">
        <p>{MODE_CONSEQUENCE[item.mode]}</p>
      </Notice>
      <p>状态：{item.status}</p>
      {error ? (
        <Notice tone="error">
          <p>{error}</p>
        </Notice>
      ) : null}
      <form onSubmit={onRename}>
        <FormField
          id="rename-project"
          label="显示名称"
          value={name}
          onChange={(ev) => setName(ev.target.value)}
        />
        <Button type="submit" loading={busy}>
          重命名
        </Button>
      </form>
      <div>
        {item.status === 'draft' || item.status === 'suspended' ? (
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              void run(() => transitionProject(item.project_id, 'activate', auth.getCsrfToken()))
            }
          >
            激活
          </Button>
        ) : null}
        {item.status === 'active' ? (
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              void run(() => transitionProject(item.project_id, 'suspend', auth.getCsrfToken()))
            }
          >
            暂停
          </Button>
        ) : null}
        {item.status !== 'archived' ? (
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              void run(() => transitionProject(item.project_id, 'archive', auth.getCsrfToken()))
            }
          >
            归档
          </Button>
        ) : null}
        <Button type="button" variant="secondary" onClick={() => setConfirmDelete(true)}>
          删除
        </Button>
      </div>
      <h2>Provider Binding</h2>
      <p>每个协议一份生效配置。模式必须与 Project 一致。不会显示上游凭据。</p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run(async () => {
            const models = bindModels
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean)
            const created = await createBinding(
              item.project_id,
              {
                protocol: bindProtocol,
                supply_mode: item.mode,
                allowed_models: item.mode === 'shared' ? models : undefined,
              },
              auth.getCsrfToken(),
            )
            const published = await publishBinding(
              item.project_id,
              created.binding_id,
              auth.getCsrfToken(),
            )
            const sdk = await getSdkHint(item.project_id, published.binding_id)
            setHint(sdk)
            setBindings(await listBindings(item.project_id))
          })
        }}
        data-testid="binding-form"
      >
        <FormField
          id="bind-protocol"
          as="select"
          label="协议"
          value={bindProtocol}
          onChange={(ev) => setBindProtocol(ev.target.value as ProtocolName)}
        >
          {PROTOCOLS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </FormField>
        {item.mode === 'shared' ? (
          <FormField
            id="bind-models"
            label="允许的模型"
            value={bindModels}
            onChange={(ev) => setBindModels(ev.target.value)}
            hint="逗号分隔。创建后不可跨协议映射。"
          />
        ) : (
          <p>专享 Binding 需可用 Connection，本页不回显凭据。</p>
        )}
        <Button type="submit" loading={busy}>
          发布 Binding
        </Button>
      </form>
      {hint ? (
        <Notice tone="info" data-testid="sdk-hint">
          <p>
            SDK：{hint.protocol} {hint.base_url}（{hint.auth_scheme} / {hint.protocol_version}）
          </p>
        </Notice>
      ) : null}
      <ul data-testid="binding-list">
        {bindings.map((b) => (
          <li key={b.binding_id}>
            {b.protocol} · {b.status} · v{b.version}
          </li>
        ))}
      </ul>
      <h2>代理 Key</h2>
      <p>明文只显示一次。列表仅前后缀，不能用于认证。</p>
      <form
        data-testid="proxy-key-form"
        onSubmit={(e) => {
          e.preventDefault()
          void run(async () => {
            const issued = await issueProjectKey(
              item.project_id,
              {
                name: keyName,
                protocols: ['openai'],
                allowed_models: bindModels
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              },
              auth.getCsrfToken(),
            )
            setOnceSecret(issued.secret ?? null)
            setKeys(await listProjectKeys(item.project_id))
          })
        }}
      >
        <FormField
          id="key-name"
          label="Key 名称"
          value={keyName}
          onChange={(ev) => setKeyName(ev.target.value)}
        />
        <Button type="submit" loading={busy}>
          签发代理 Key
        </Button>
      </form>
      {onceSecret ? (
        <Notice tone="info" data-testid="key-secret-once">
          <p>请立即保存：{onceSecret}</p>
        </Notice>
      ) : null}
      <ul data-testid="proxy-key-list">
        {keys.map((k) => (
          <li key={k.key_id}>
            {k.masked_prefix}****{k.masked_suffix} · {k.status}
          </li>
        ))}
      </ul>
      <h2>协议</h2>
      <ul>
        {PROTOCOLS.map((p) => {
          const row = item.protocols.find((x) => x.protocol === p)
          const on = row?.enabled ?? false
          return (
            <li key={p}>
              {p}：{on ? '已启用' : '未启用'}
              <Button
                type="button"
                variant="link"
                onClick={() =>
                  void run(() => setProtocolEnabled(item.project_id, p, !on, auth.getCsrfToken()))
                }
              >
                {on ? '停用' : '启用'}
              </Button>
            </li>
          )
        })}
      </ul>
      <Dialog open={confirmDelete} title="确认删除" onClose={() => setConfirmDelete(false)}>
        <p>存在有效 Key、在途任务或未结算分录时将拒绝删除。</p>
        <Button
          type="button"
          onClick={() => {
            void (async () => {
              try {
                await deleteProject(item.project_id, auth.getCsrfToken())
                navigate('/projects')
              } catch (err: unknown) {
                setError(err instanceof Error ? err.message : '删除失败')
                setConfirmDelete(false)
              }
            })()
          }}
        >
          确认删除
        </Button>
      </Dialog>
    </div>
  )
}

export default ProjectDetail
