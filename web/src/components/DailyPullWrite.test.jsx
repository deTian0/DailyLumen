import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DailyPullWrite } from './DailyPullWrite'

vi.mock('../lib/api', () => ({
  api: {
    writePlanBody: vi.fn(async () => ({
      action: 'daily_pull',
      token: 'tok',
      expires_in: 300,
      cli: 'python -m review_tool daily-pull --date 2026-11-12 --apply',
      preview: {
        date: '2026-11-12',
        step_count: 3,
        steps: [
          { name: '练练素材 → 复盘 md + 入库', cli: 'python -m review_tool keepstrong --date 2026-11-12 --write --ingest' },
          { name: '习惯快照（ClickUp → habit_logs）', cli: 'python -m review_tool habits --sync 2026-11-12' },
          { name: '全量入库（保护模式，补当日手填字段）', cli: 'python -m review_tool ingest' },
        ],
        disclaimer: '确认后会打网',
      },
    })),
    writeConfirm: vi.fn(),
  },
  errText: (e) => String(e?.message || e),
}))

describe('DailyPullWrite', () => {
  it('预览列出三步且无代勾文案', async () => {
    render(<DailyPullWrite health={{ readonly: false }} toast={() => {}} />)
    expect(screen.getByRole('heading', { name: /夜间采集拉齐/ })).toBeTruthy()
    const btn = screen.getByRole('button', { name: /预览.*夜间拉齐/ })
    btn.click()
    expect(await screen.findByText(/练练素材/)).toBeTruthy()
    expect(screen.getAllByText(/习惯快照/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/全量入库/)).toBeTruthy()
    expect(screen.getByText(/不含代勾练练健身/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /确认拉齐/ })).toBeTruthy()
  })
})
