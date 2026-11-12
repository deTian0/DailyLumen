import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EveningGuideStrip } from './EveningGuideStrip'

const evening = {
  text: '…',
  data: {
    slot: 'evening',
    as_of: '2026-11-12',
    day_in_db: true,
    steps: [
      { id: 'intake', title: '走 daily-review-intake 全流程', note: '确认归属日…', cmd: null },
      { id: 'clickup', title: '拉 ClickUp', cmd: 'python -m review_tool clickup' },
      { id: 'training', title: '练练同步训练日与明细', note: '先落 md', cmd: 'python -m review_tool keepstrong --write' },
      { id: 'doctor', title: '收尾体检', cmd: 'python -m review_tool doctor' },
    ],
  },
}

describe('EveningGuideStrip', () => {
  it('展示三步并深链到 Life / Reports，无写按钮', () => {
    render(<EveningGuideStrip evening={evening} />)
    expect(screen.getByRole('heading', { name: /今晚三步/ })).toBeTruthy()
    expect(screen.getByText(/1\. 走 daily-review-intake/)).toBeTruthy()
    expect(screen.getByText(/2\. 练练同步/)).toBeTruthy()
    expect(screen.getByText(/3\. 收尾体检/)).toBeTruthy()

    const full = screen.getByRole('link', { name: /完整夜间指引/ })
    expect(full.getAttribute('href')).toBe('#/life?tab=evening')

    expect(screen.getByRole('link', { name: /一日三步 →/ }).getAttribute('href')).toContain('tab=day-help')
    expect(screen.getByRole('link', { name: /去同步 md/ }).getAttribute('href')).toContain('focus=keepstrong-sync')
    expect(screen.getByRole('link', { name: /去体检/ }).getAttribute('href')).toBe('#/doctor')

    expect(screen.queryByRole('button', { name: /确认|写入|同步/ })).toBeNull()
  })

  it('无 steps 时空态一句，仍给夜间指引入口', () => {
    render(<EveningGuideStrip evening={{ text: '', data: { as_of: '2026-11-12', steps: [] } }} />)
    expect(screen.getByText(/暂无结构化步骤/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /完整夜间指引/ }).getAttribute('href')).toBe('#/life?tab=evening')
  })

  it('evening 为空时不渲染', () => {
    const { container } = render(<EveningGuideStrip evening={null} />)
    expect(container.firstChild).toBeNull()
  })
})
