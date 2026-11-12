// E1 / FR-K3：DraftsWrite 预览→确认落收件箱；blocked（已存在同名）不给确认按钮。
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DraftWrite } from './DraftsWrite'

const health = { readonly: false }

function mockFetch(planBody, confirmBody) {
  return vi.fn((url, opts) => {
    if (url.includes('/plan')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(planBody) })
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(confirmBody) })
  })
}

const planBody = {
  action: 'promise_draft',
  token: 'tok-e1',
  expires_in: 300,
  cli: 'python -m review_tool promise-draft --date 2026-11-13 --stdout',
  preview: {
    date: '2026-11-13',
    file: '明日候选-2026-11-13.md',
    candidates: [{ list: '工作', name: '看课 1.5h' }],
    count: 1,
    bytes: 300,
    writes: 'inbox_md',
    disclaimer: '草稿只落收件箱，不入库。',
  },
}

describe('DraftsWrite', () => {
  beforeEach(() => {
    localStorage.clear(); sessionStorage.clear()
  })

  it('预览零写盘提示 + 候选列表；确认后提示去复盘 md 勾选回填', async () => {
    const toast = vi.fn()
    const confirmBody = { action: 'promise_draft', cli: planBody.cli, result: { file: planBody.preview.file, db_changed: false } }
    vi.stubGlobal('fetch', mockFetch(planBody, confirmBody))
    render(<DraftWrite kind="promise-draft" health={health} toast={toast} title="明日 Top 3 候选" desc="d" />)
    fireEvent.click(screen.getByRole('button', { name: /预览：明日 Top 3 候选/ }))
    await waitFor(() => expect(screen.getByText('看课 1.5h')).toBeTruthy())
    expect(screen.getByText(/收件箱\/明日候选-2026-11-13\.md/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /确认落收件箱：明日 Top 3 候选/ }))
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.stringContaining('已落收件箱')))
  })

  it('blocked（同名草稿已存在）时不给确认按钮', async () => {
    const blocked = { ...planBody, preview: { ...planBody.preview, blocked_reason: 'draft_exists', exists: true } }
    vi.stubGlobal('fetch', mockFetch(blocked, {}))
    render(<DraftWrite kind="promise-draft" health={health} toast={vi.fn()} title="明日 Top 3 候选" desc="d" />)
    fireEvent.click(screen.getByRole('button', { name: /预览：明日 Top 3 候选/ }))
    await waitFor(() => expect(screen.getByText(/拒绝写入/)).toBeTruthy())
    expect(screen.queryByRole('button', { name: /确认落收件箱/ })).toBeNull()
  })

  it('只读启动时整卡折叠为门禁一行', () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<DraftWrite kind="improve-draft" health={{ readonly: true }} toast={vi.fn()} title="改进点取数骨架" desc="d" />)
    expect(screen.getByText(/看板以只读启动/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /预览/ })).toBeNull()
  })
})
