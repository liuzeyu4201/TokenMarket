import { Component, type ErrorInfo, type ReactNode } from 'react'
import { PageState } from './PageState'

interface Props {
  children: ReactNode
}

interface State {
  message: string | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { message: null }

  static getDerivedStateFromError(error: Error): State {
    return { message: error.message || '渲染失败' }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('ui-error-boundary', error, info.componentStack)
  }

  render(): ReactNode {
    if (this.state.message) {
      return (
        <PageState
          kind="error"
          detail="页面局部出错，导航仍可用。"
          onRetry={() => this.setState({ message: null })}
        />
      )
    }
    return this.props.children
  }
}

export default ErrorBoundary
