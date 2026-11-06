import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WriteFlow } from './WriteFlow'

const jsonRes = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const WRITABLE = { readonly: false }
const plan = (token) => ({ token, preview: { n: 1 }, cli: 'python -m review_tool x --apply', expires_in: 300 })

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

const urls = () => fetchMock.mock.calls.map(([u, o]) => `${o.method} ${u}`)

function setup(props = {}) {
  const toast = vi.fn()
  const onDone = vi.fn()
  render(
    <WriteFlow action="habits" params={{ date: '2026-11-05' }} health={WRITABLE} toast={toast}
      title="同步习惯" desc="说明" renderPreview={(p) => <div>预览 n={p.n}</div>} onDone={onDone} {...props} />,
  )
  return { toast, onDone }
}

describe('WriteFlow 预览 → 确认', () => {
  it('预览后显示等价 CLI，确认用预览拿到的 token', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonRes(200, plan('tok-A')))
      .mockResolvedValueOnce(jsonRes(200, { cli: 'python -m review_tool x --apply', result: { backup: 'b.db' } }))
    const { toast, onDone } = setup()
    fireEvent.click(screen.getByRole('button', { name: '预览：同步习惯' }))
    expect(await screen.findByText('预览 n=1')).toBeTruthy()
    expect(screen.getByText('python -m review_tool x --apply')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '确认写入：同步习惯' }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(urls()).toEqual(['POST /api/write/habits/plan?date=2026-11-05', 'POST /api/write/confirm'])
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ token: 'tok-A' })
    expect(toast).toHaveBeenCalledWith('已写入，回读校验通过')
    expect(screen.getByRole('status').textContent).toContain('库已先备份：b.db')
  })

  it('确认失败：旧预览收起（不可复用 token），重试会重新预览拿新 token', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonRes(200, plan('tok-A')))
      .mockResolvedValueOnce(jsonRes(502, { error: { code: 'upstream_unreachable', message: 'x' } }))
      .mockResolvedValueOnce(jsonRes(200, plan('tok-B')))
      .mockResolvedValueOnce(jsonRes(200, { cli: 'c', result: {} }))
    const { onDone } = setup()
    fireEvent.click(screen.getByRole('button', { name: '预览：同步习惯' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认写入：同步习惯' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('ClickUp 网络不可达')
    expect(screen.queryByRole('button', { name: '确认写入：同步习惯' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认写入：同步习惯' }))
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))
    expect(urls()).toEqual([
      'POST /api/write/habits/plan?date=2026-11-05',
      'POST /api/write/confirm',
      'POST /api/write/habits/plan?date=2026-11-05',
      'POST /api/write/confirm',
    ])
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ token: 'tok-B' })
  })

  it('canConfirm=false 时不给确认按钮', async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(200, plan('tok-A')))
    setup({ canConfirm: () => false })
    fireEvent.click(screen.getByRole('button', { name: '预览：同步习惯' }))
    await screen.findByText('预览 n=1')
    expect(screen.queryByRole('button', { name: '确认写入：同步习惯' })).toBeNull()
    expect(screen.getByRole('button', { name: '关闭：同步习惯' })).toBeTruthy()
  })

  it('带 body 的动作走 JSON plan', async () => {
    fetchMock.mockResolvedValueOnce(jsonRes(200, plan('tok-A')))
    setup({ action: 'task_create', body: { name: '买菜' }, params: undefined })
    fireEvent.click(screen.getByRole('button', { name: '预览：同步习惯' }))
    await screen.findByText('预览 n=1')
    expect(urls()).toEqual(['POST /api/write/task_create/plan'])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ name: '买菜' })
  })
})

describe('WriteFlow 门禁', () => {
  it('只读启动时折叠成一行，不发请求', () => {
    setup({ health: { readonly: true } })
    expect(screen.getByText('同步习惯')).toBeTruthy()
    expect(screen.getByText(/serve --enable-write/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '预览：同步习惯' })).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('前置门禁原因优先展示', () => {
    setup({ blockedReason: '需要 deepseek mode' })
    expect(screen.getByText('需要 deepseek mode')).toBeTruthy()
  })
})
