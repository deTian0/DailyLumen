import { describe, expect, it } from 'vitest'
import { hashPage, hashQuery } from './route'

describe('hash 路由', () => {
  it('解析页面 id（有无前导斜杠 / 查询串）', () => {
    window.location.hash = '#/reports?tab=ctx'
    expect(hashPage()).toBe('reports')
    window.location.hash = '#life'
    expect(hashPage()).toBe('life')
    window.location.hash = ''
    expect(hashPage()).toBe('')
  })

  it('读取查询参数，缺失为 null', () => {
    window.location.hash = '#/reports?tab=ctx&date=2026-11-05'
    expect(hashQuery('tab')).toBe('ctx')
    expect(hashQuery('date')).toBe('2026-11-05')
    expect(hashQuery('nope')).toBeNull()
    window.location.hash = '#/today'
    expect(hashQuery('tab')).toBeNull()
  })
})
