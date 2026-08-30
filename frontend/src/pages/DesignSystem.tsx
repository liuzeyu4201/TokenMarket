import { useState } from 'react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { FormField } from '../ui/FormField'
import { Notice } from '../ui/Notice'
import { PageState } from '../ui/PageState'
import { Table } from '../ui/Table'
import { UnavailableAction } from '../ui/UnavailableAction'

export function DesignSystem() {
  const [open, setOpen] = useState(false)
  return (
    <div className="card" data-testid="design-system">
      <h1>组件目录</h1>
      <p>共享基础组件的可视状态。业务页应复用这些控件。</p>

      <h2>按钮</h2>
      <Button type="button">默认</Button>
      <Button type="button" disabled>
        禁用
      </Button>
      <Button type="button" loading>
        加载
      </Button>
      <Button type="button" variant="secondary">
        次要
      </Button>

      <h2>表单</h2>
      <FormField id="ds-name" label="示例字段" hint="说明文字" />
      <FormField id="ds-err" label="错误字段" error="必填" />

      <h2>通知</h2>
      <Notice tone="info">信息</Notice>
      <Notice tone="success">成功</Notice>
      <Notice tone="error">错误</Notice>
      <Notice tone="loading">加载中</Notice>

      <h2>页面状态</h2>
      <PageState kind="empty" />
      <PageState kind="forbidden" />
      <PageState kind="rate_limited" />
      <PageState kind="offline" />

      <h2>表格</h2>
      <Table caption="状态清单" headers={['组件', '状态']} rows={[['Button', 'default / focus / disabled / loading']]} />

      <h2>即将开放</h2>
      <UnavailableAction label="示例业务" />

      <h2>弹窗</h2>
      <Button type="button" variant="secondary" onClick={() => setOpen(true)}>
        打开弹窗
      </Button>
      <Dialog open={open} title="目录弹窗" onClose={() => setOpen(false)}>
        <p>用于演示焦点陷阱。</p>
      </Dialog>
    </div>
  )
}

export default DesignSystem
