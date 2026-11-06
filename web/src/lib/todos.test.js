import { describe, expect, it } from 'vitest'
import { groupTodos, weekDays } from './todos'

const t = (id, due = null) => ({ id, name: `任务${id}`, due })

describe('groupTodos 待办分组', () => {
  it('逾期 / 今日到期·进行中 / 无截止，逾期默认折叠', () => {
    const groups = groupTodos({
      overdue: [t('o1', '2026-11-01')],
      in_progress: [t('p1')],
      open: [t('a1', '2026-11-06'), t('a2')],
    })
    expect(groups.map((g) => g.id)).toEqual(['overdue', 'due', 'nodue'])
    expect(groups[0].open).toBe(false)
    expect(groups[1].open).toBe(true)
    expect(groups[0].items).toEqual([[t('o1', '2026-11-01'), 'overdue']])
    // 进行中排在有截止的 open 前面；kind 标签随行
    expect(groups[1].items.map(([x, k]) => `${x.id}:${k}`)).toEqual(['p1:in_progress', 'a1:open'])
    expect(groups[2].items.map(([x]) => x.id)).toEqual(['a2'])
  })

  it('空分组不渲染', () => {
    const groups = groupTodos({ overdue: [], in_progress: [], open: [t('a2')] })
    expect(groups.map((g) => g.id)).toEqual(['nodue'])
    expect(groupTodos({ overdue: [], in_progress: [], open: [] })).toEqual([])
  })
})

describe('weekDays', () => {
  it('周一开头的 7 天（含跨月）', () => {
    expect(weekDays('2026-11-06')).toEqual([
      '2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06', '2026-11-07', '2026-11-08',
    ])
    expect(weekDays('2026-11-01')[0]).toBe('2026-10-26')
  })
})
