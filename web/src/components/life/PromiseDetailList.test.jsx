import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PromiseDetailList, pickAttentionItems } from './PromiseDetailList'

const sample = {
  rate: 0.5,
  counts: { fulfilled: 1, missed: 2, unmapped: 1, no_data: 1, declined: 0 },
  items: [
    {
      date: '2026-11-10', kind: 'plan', seq: 1, text: '脂肪≤70g', status: 'missed',
      evidence: '脂肪 82g / 上限 70g', bucket_label: '饮食',
    },
    {
      date: '2026-11-11', kind: 'plan', seq: 1, text: '23:30 前睡', status: 'missed',
      evidence: '入睡 00:10 / 目标 ≤23:30', bucket_label: '睡眠',
    },
    {
      date: '2026-11-12', kind: 'plan', seq: 1, text: '学习 60min', status: 'no_data',
      evidence: '对账日尚未结束', bucket_label: '学习',
    },
    {
      date: '2026-11-09', kind: 'plan', seq: 1, text: '深度工作', status: 'unmapped',
      evidence: '工作类承诺需写具体时长', bucket_label: '工作',
    },
    {
      date: '2026-11-08', kind: 'plan', seq: 1, text: '运动 40min', status: 'fulfilled',
      evidence: '运动 45min / 目标 40min', bucket_label: '运动',
    },
  ],
}

describe('pickAttentionItems', () => {
  it('未兑现优先于待判定，排除已兑现与无法判定', () => {
    const got = pickAttentionItems(sample.items)
    expect(got.map((r) => r.text)).toEqual(['23:30 前睡', '脂肪≤70g', '学习 60min'])
  })
})

describe('PromiseDetailList', () => {
  it('列出关注项与状态标，空态友好', () => {
    const { rerender } = render(<PromiseDetailList data={sample} />)
    expect(screen.getByRole('heading', { name: '近期关注' })).toBeTruthy()
    expect(screen.getByText('脂肪≤70g')).toBeTruthy()
    expect(screen.getAllByText('未兑现').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('待判定')).toBeTruthy()
    expect(screen.queryByText('深度工作')).toBeNull()
    expect(screen.queryByText('运动 40min')).toBeNull()

    rerender(<PromiseDetailList data={{ items: [], counts: {} }} />)
    expect(screen.getByText(/还没有承诺记录/)).toBeTruthy()

    rerender(
      <PromiseDetailList
        data={{
          items: [
            {
              date: '2026-11-01', kind: 'plan', seq: 1, text: '已兑', status: 'fulfilled',
              evidence: 'ok', bucket_label: '运动',
            },
          ],
        }}
      />,
    )
    expect(screen.getByText(/没有未兑现或待判定/)).toBeTruthy()
  })
})
