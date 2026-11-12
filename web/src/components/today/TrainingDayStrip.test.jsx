import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TrainingDayStrip } from './TrainingDayStrip'

const base = {
  date: '2026-11-12',
  keepstrong: { checked: true, completed: true, count: 1, message: '练练旁证：当日有 1 条' },
  md_exists: true,
  md_synced: false,
  next: 'sync_md',
  links: {
    sync: '#/life?tab=coach&focus=keepstrong-sync',
    habit: '#/life?tab=coach&focus=clickup-habit',
    coach: '#/life?tab=coach',
  },
  note: '只读',
}

describe('TrainingDayStrip', () => {
  it('有 completed 且未同步时引导去同步 md，不诱导代勾为主 CTA', () => {
    render(<TrainingDayStrip status={base} />)
    expect(screen.getByRole('heading', { name: '今日训练日' })).toBeTruthy()
    const sync = screen.getByRole('link', { name: /去同步复盘 md/ })
    expect(sync.getAttribute('href')).toContain('focus=keepstrong-sync')
    expect(screen.queryByRole('link', { name: /代勾/ })).toBeNull()
  })

  it('已同步时给出可选代勾；无 completed 不诱导代勾', () => {
    const { rerender } = render(
      <TrainingDayStrip status={{ ...base, md_synced: true, next: 'habit_optional' }} />,
    )
    expect(screen.getByRole('link', { name: /代勾练练健身/ })).toBeTruthy()
    rerender(
      <TrainingDayStrip
        status={{
          ...base,
          keepstrong: { checked: true, completed: false, count: 0, message: '无 completed' },
          md_synced: true,
          next: 'none',
        }}
      />,
    )
    expect(screen.getByText(/无 completed 不诱导/)).toBeTruthy()
    expect(screen.queryByRole('link', { name: /代勾/ })).toBeNull()
  })
})
