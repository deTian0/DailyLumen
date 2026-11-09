import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authKey } from '../lib/api'
import { KeepStrongWrite } from './KeepStrongWrite'

const jsonRes = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const WRITABLE = { readonly: false }
const ACTIONS = '[{"actionId":"act_x","groups":[{"sets":3}]}]'
const plan = (token, preview = { name: '全身A', note: '写回不落库' }) => ({
  token, preview, cli: 'python -m review_tool keepstrong --schedule --yes', expires_in: 300,
})

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  authKey.set('test-key')
})

const urls = () => fetchMock.mock.calls.map(([u, o]) => `${o.method} ${u}`)

function fillSchedule() {
  const root = screen.getByLabelText('排课表单')
  const inputs = within(root).getAllByRole('textbox')
  // 日期、课名、actions textarea
  fireEvent.change(inputs[0], { target: { value: '2026-11-06' } })
  fireEvent.change(inputs[1], { target: { value: '全身A' } })
  fireEvent.change(inputs[2], { target: { value: ACTIONS } })
  return root
}

describe('KeepStrongWrite 排课 plan → confirm', () => {
  it('预览带 actions JSON 体，确认用 token；文案含不落库/不可撤销', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonRes(200, plan('tok-sched')))
      .mockResolvedValueOnce(jsonRes(200, {
        cli: 'python -m review_tool keepstrong --schedule --yes',
        result: { written: true, db_changed: false },
      }))
    const toast = vi.fn()
    render(<KeepStrongWrite health={WRITABLE} toast={toast} />)
    expect(screen.getAllByText(/写回不落库、不可撤销/).length).toBeGreaterThan(0)

    fillSchedule()
    fireEvent.click(screen.getByRole('button', { name: '预览：排课' }))
    expect(await screen.findByText(/不落库、不可撤销、不作系统状态/)).toBeTruthy()
    expect(urls()).toEqual(['POST /api/write/ks-schedule/plan'])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      day: '2026-11-06', name: '全身A', actions: [{ actionId: 'act_x', groups: [{ sets: 3 }] }],
    })

    fireEvent.click(screen.getByRole('button', { name: '确认写回：排课' }))
    await waitFor(() => expect(toast).toHaveBeenCalled())
    expect(urls()).toEqual(['POST /api/write/ks-schedule/plan', 'POST /api/write/confirm'])
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ token: 'tok-sched' })
  })

  it('actions JSON 非法时禁用预览（前端校验，不发请求）', () => {
    render(<KeepStrongWrite health={WRITABLE} toast={vi.fn()} />)
    const root = screen.getByLabelText('排课表单')
    const inputs = within(root).getAllByRole('textbox')
    fireEvent.change(inputs[0], { target: { value: '2026-11-06' } })
    fireEvent.change(inputs[1], { target: { value: '全身A' } })
    fireEvent.change(inputs[2], { target: { value: '{' } })
    expect(within(root).getByRole('alert').textContent).toMatch(/语法/)
    expect(screen.getByRole('button', { name: '预览：排课' }).disabled).toBe(true)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('KeepStrongWrite 后端错误回显', () => {
  it('422 invalid_param 回显服务端文案', async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(422, {
      error: { code: 'invalid_param', message: '排课 actions 不能为空' },
    }))
    render(<KeepStrongWrite health={WRITABLE} toast={vi.fn()} />)
    fillSchedule()
    fireEvent.click(screen.getByRole('button', { name: '预览：排课' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('排课 actions 不能为空')
  })

  it('401 upstream_auth 回显且不清看板 key', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonRes(200, plan('tok-A')))
      .mockResolvedValueOnce(jsonRes(401, {
        error: { code: 'upstream_auth', message: '练练 API Key 已过期' },
      }))
    render(<KeepStrongWrite health={WRITABLE} toast={vi.fn()} />)
    fillSchedule()
    fireEvent.click(screen.getByRole('button', { name: '预览：排课' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认写回：排课' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toMatch(/上游拒绝访问|练练 API Key/)
    expect(authKey.get()).toBe('test-key')
    expect(screen.queryByRole('button', { name: '确认写回：排课' })).toBeNull()
  })
})

describe('KeepStrongWrite 计划命令', () => {
  it('command 仅允许 4 值；预览 body 含 running_plan_id', async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(200, plan('tok-cmd', { command: 'delay' })))
    render(<KeepStrongWrite health={WRITABLE} toast={vi.fn()} />)
    const root = screen.getByLabelText('计划命令表单')
    const select = within(root).getByDisplayValue('delay')
    const opts = within(select).getAllByRole('option').map((o) => o.value)
    expect(opts).toEqual(['delay', 'cancel_rest', 'add_alternative', 'add_temporary_workout'])
    fireEvent.change(within(root).getByPlaceholderText('pln_xxx'), { target: { value: 'pln_abc1' } })
    fireEvent.click(screen.getByRole('button', { name: '预览：计划命令' }))
    await screen.findByText(/不落库、不可撤销、不作系统状态/)
    expect(urls()).toEqual(['POST /api/write/ks-plan-command/plan'])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      running_plan_id: 'pln_abc1', command: 'delay',
    })
  })
})
