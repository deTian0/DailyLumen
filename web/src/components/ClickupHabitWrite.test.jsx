import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authKey, todayStr } from '../lib/api'
import { ClickupHabitWrite } from './ClickupHabitWrite'

const jsonRes = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const WRITABLE = { readonly: false }

const planWould = {
  action: 'clickup_habit',
  token: 'tok-b15',
  expires_in: 300,
  cli: 'python -m review_tool clickup-habit --habit lianlian --date 2026-11-08 --apply',
  preview: {
    date: '2026-11-08',
    habit_key: 'lianlian',
    label: '练练健身',
    task_id: 't1',
    name: '练练健身',
    action: 'would_complete',
    closed: false,
    disclaimer: '⚠️ 这是 ClickUp「习惯与打卡」勾选（Continuity）',
    keepstrong_hint: { message: '练练旁证：当日有 1 条 completed 训练（仅提示，非门槛）' },
  },
}

const planSkip = {
  ...planWould,
  token: 'tok-skip',
  cli: 'x',
  preview: {
    ...planWould.preview,
    action: 'skip_closed',
    closed: true,
    keepstrong_hint: { message: '练练旁证：未检查' },
  },
}

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  authKey.set('test-key')
})

describe('ClickupHabitWrite plan → confirm', () => {
  it('预览后可确认会写 ClickUp；文案含习惯≠训练', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonRes(200, planWould))
      .mockResolvedValueOnce(jsonRes(200, {
        action: 'clickup_habit',
        date: '2026-11-08',
        cli: planWould.cli,
        result: { written: true, db_changed: false },
      }))
    const toast = vi.fn()
    render(<ClickupHabitWrite health={WRITABLE} toast={toast} />)

    fireEvent.click(screen.getByRole('button', { name: /预览：代勾练练健身/ }))
    expect(await screen.findByText(/将勾选/)).toBeTruthy()
    expect(screen.getAllByText(/Continuity/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/habit_logs/).length).toBeGreaterThan(0)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/write/clickup-habit/plan')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      habit: 'lianlian', date: todayStr(),
    })

    fireEvent.click(screen.getByRole('button', { name: /确认勾选：代勾练练健身/ }))
    await waitFor(() => expect(fetchMock.mock.calls[1][0]).toBe('/api/write/confirm'))
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ token: 'tok-b15' })
    expect(toast).toHaveBeenCalled()
  })

  it('已完成幂等时不给确认按钮', async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(200, planSkip))
    render(<ClickupHabitWrite health={WRITABLE} toast={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /预览：代勾练练健身/ }))
    expect(await screen.findByText(/幂等/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /确认勾选/ })).toBeNull()
  })
})
