import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
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

  useEffect(() => {
    if (auth.status !== 'authenticated' || !projectId) return
    let cancelled = false
    void getProject(projectId)
      .then((p) => {
        if (cancelled) return
        setItem(p)
        setName(p.display_name)
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
