import { Notice } from './Notice'
import { Button } from './Button'

export type PageStateKind = 'loading' | 'empty' | 'error' | 'forbidden' | 'rate_limited' | 'offline'

const COPY: Record<PageStateKind, { title: string; tone: 'info' | 'error' | 'loading' }> = {
  loading: { title: '正在加载', tone: 'loading' },
  empty: { title: '暂无内容', tone: 'info' },
  error: { title: '部分内容无法显示', tone: 'error' },
  forbidden: { title: '没有权限查看此内容', tone: 'error' },
  rate_limited: { title: '请求过于频繁，请稍后再试', tone: 'error' },
  offline: { title: '当前离线，请检查网络后重试', tone: 'error' },
}

export function PageState({
  kind,
  detail,
  onRetry,
}: {
  kind: PageStateKind
  detail?: string
  onRetry?: () => void
}) {
  const cfg = COPY[kind]
  return (
    <Notice tone={cfg.tone} data-testid={`page-state-${kind}`}>
      <p>
        <strong>{cfg.title}</strong>
      </p>
      {detail ? <p>{detail}</p> : null}
      {onRetry ? (
        <Button variant="secondary" type="button" onClick={onRetry}>
          重试
        </Button>
      ) : null}
    </Notice>
  )
}

export default PageState
