import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authKey } from '../lib/api'
import { KeepstrongSyncWrite } from './KeepstrongSyncWrite'

const jsonRes = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const WRITABLE = { readonly: false }

const planChanged = {
  action: 'keepstrong_sync',
  token: 'tok-d1',
  expires_in: 300,
  cli: 'python -m review_tool keepstrong --date 2026-09-09 --write',
  preview: {
    date: '2026-09-09',
    file: '2026-09-09.md',
    records_raw: 1,
    records_day: 1,
    training_written: true,
    training_replaced: false,
    training_day: true,
    weight_kg: 82.5,
    weight_written: true,
    changed: true,
    empty_note: null,
    writes: 'local_review_md',
    does_not: ['keepstrong_app', 'reviews.db', 'habit_logs'],
    disclaimer: '写入本地复盘 md（训练块/训练日/体重），不是练练 App 写回；入库请另确认 ingest。',
    next_ingest_cli: 'python -m review_tool ingest 复盘/2026-09/2026-09-09.md',
  },
}

const planUnchanged = {
  ...planChanged,
  token: 'tok-same',
  preview: { ...planChanged.preview, changed: false, training_written: true },
}

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  authKey.set('test-key')
})

describe('KeepstrongSyncWrite', () => {
  it('预览后可确认写 md；文案区分 App 写回；确认后自动预览 ingest', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonRes(200, planChanged))
      .mockResolvedValueOnce(jsonRes(200, {
        action: 'keepstrong_sync',
        date: '2026-09-09',
        cli: planChanged.cli,
        result: { written: true, db_changed: false },
      }))
      .mockResolvedValueOnce(jsonRes(200, {
        action: 'ingest',
        token: 'tok-ing',
        expires_in: 300,
        cli: 'python -m review_tool ingest x.md',
        preview: {
          date: '2026-09-09', file: '2026-09-09.md', rel: 'x', pending: false,
          allow_ai_draft: false, will_skip: false, fields: {},
        },
      }))
    const toast = vi.fn()
    render(<KeepstrongSyncWrite health={WRITABLE} toast={toast} />)

    expect(screen.getByText(/不是上方「练练写回」/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /预览：同步复盘 md/ }))
    expect(await screen.findByText(/写入本地复盘 md/)).toBeTruthy()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/write/keepstrong-sync/plan')

    fireEvent.click(screen.getByRole('button', { name: /确认写入 md：同步复盘 md/ }))
    await waitFor(() => expect(fetchMock.mock.calls[1][0]).toBe('/api/write/confirm'))
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ token: 'tok-d1' })
    expect(toast).toHaveBeenCalled()
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => c[0] === '/api/write/ingest/plan')).toBe(true))
  })

  it('无变更时不给确认按钮', async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(200, planUnchanged))
    render(<KeepstrongSyncWrite health={WRITABLE} toast={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /预览：同步复盘 md/ }))
    expect(await screen.findByText(/写入本地复盘 md/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /确认写入 md/ })).toBeNull()
  })
})
