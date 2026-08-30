import { FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import {
  MODE_CONSEQUENCE,
  createProject,
  listProjects,
  type Project,
  type ProjectMode,
  type ProtocolName,
} from '../api/v1/projects'
import { Button } from '../ui/Button'
import { FormField } from '../ui/FormField'
import { Notice } from '../ui/Notice'
import { PageState } from '../ui/PageState'
import { Table } from '../ui/Table'

const PROTOCOLS: ProtocolName[] = ['openai', 'anthropic', 'vertex']

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  active: '已激活',
  suspended: '已暂停',
  archived: '已归档',
}

const MODE_LABEL: Record<ProjectMode, string> = {
  shared: '共享',
  dedicated: '专享',
}

export function Projects() {
  const auth = useAuth()
  const [items, setItems] = useState<Project[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [mode, setMode] = useState<ProjectMode>('shared')
  const [protocols, setProtocols] = useState<ProtocolName[]>(['openai'])
  const [busy, setBusy] = useState(false)

  const workspace = auth.session?.workspace

  useEffect(() => {
    if (auth.status !== 'authenticated') return
    if (workspace !== 'buyer') return
    let cancelled = false
    void listProjects()
      .then((rows) => {
        if (!cancelled) setItems(rows)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '无法加载 Project')
        setItems([])
      })
    return () => {
      cancelled = true
    }
  }, [auth.status, workspace])

  if (auth.status === 'checking') {
    return <PageState kind="loading" />
  }

  if (workspace !== 'buyer') {
    return (
      <div className="card" data-testid="projects-forbidden">
        <h1>我的 Project</h1>
        <PageState kind="forbidden" detail="请切换到买家工作区后再管理 Project。" />
      </div>
    )
  }

  const toggleProtocol = (p: ProtocolName) => {
    setProtocols((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]))
  }

  const onCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await createProject(
        { display_name: name, mode, enabled_protocols: protocols },
        auth.getCsrfToken(),
      )
      setName('')
      const rows = await listProjects()
      setItems(rows)
    } catch (err: unknown) {
      const code = err instanceof ApiError ? err.code : undefined
      if (code === 'MODE_IMMUTABLE') {
        setError('模式在创建后不可修改')
      } else {
        setError(err instanceof Error ? err.message : '创建失败')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" data-testid="projects-page">
      <h1>我的 Project</h1>
      <p>Project 是后续 Binding、Key 与路由的隔离边界。模式一旦选定不可更改。</p>
      {error ? (
        <Notice tone="error">
          <p>{error}</p>
        </Notice>
      ) : null}
      <form onSubmit={(e) => void onCreate(e)} data-testid="project-create-form">
        <FormField
          id="project-name"
          label="显示名称"
          value={name}
          onChange={(ev) => setName(ev.target.value)}
          required
          maxLength={128}
          hint="同一账号内名称不可重复（忽略大小写）。"
        />
        <FormField
          id="project-mode"
          as="select"
          label="模式"
          value={mode}
          onChange={(ev) => setMode(ev.target.value as ProjectMode)}
          hint={MODE_CONSEQUENCE[mode]}
        >
          <option value="shared">共享</option>
          <option value="dedicated">专享</option>
        </FormField>
        <fieldset>
          <legend>协议</legend>
          {PROTOCOLS.map((p) => (
            <label key={p} htmlFor={`proto-${p}`}>
              <input
                id={`proto-${p}`}
                type="checkbox"
                checked={protocols.includes(p)}
                onChange={() => toggleProtocol(p)}
              />{' '}
              {p}
            </label>
          ))}
        </fieldset>
        <Button type="submit" loading={busy} disabled={!name || protocols.length === 0}>
          创建 Project
        </Button>
      </form>
      {items === null ? (
        <PageState kind="loading" />
      ) : (
        <Table
          caption="已创建的 Project"
          headers={['名称', '模式', '状态', '协议']}
          empty="还没有 Project"
          rows={items.map((p) => [
            <Link key={p.project_id} to={`/projects/${p.project_id}`}>
              {p.display_name}
            </Link>,
            MODE_LABEL[p.mode],
            STATUS_LABEL[p.status] ?? p.status,
            p.enabled_protocols.join(', '),
          ])}
        />
      )}
    </div>
  )
}

export default Projects
