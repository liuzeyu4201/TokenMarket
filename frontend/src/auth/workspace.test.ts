import { afterEach, describe, expect, it } from 'vitest'
import { WORKSPACE_UI_KEY, clearWorkspaceUiState } from '../api/v1/phoneAuth'

describe('workspace UI state', () => {
  afterEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('clears previous workspace drafts', () => {
    sessionStorage.setItem(WORKSPACE_UI_KEY, 'filters')
    localStorage.setItem(WORKSPACE_UI_KEY, 'filters')
    clearWorkspaceUiState()
    expect(sessionStorage.getItem(WORKSPACE_UI_KEY)).toBeNull()
    expect(localStorage.getItem(WORKSPACE_UI_KEY)).toBeNull()
  })
})
