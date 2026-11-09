import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  keysMatch,
  legendPrefsKey,
  loadLegendSelected,
  saveLegendSelected,
} from './legendPrefs'
import { buildChartOption, defaultLegendSelected } from './chartOption'

const threeSeries = [
  { key: 'system_score', name: '系统分', color: '#2563eb', unit: '0-10', values: [4, 5], type: 'line' },
  { key: 'health_score', name: '健康', color: '#16a34a', unit: '0-10', values: [3, 4], type: 'line' },
  { key: 'work_score', name: '工作', color: '#ea580c', unit: '0-10', values: [5, 6], type: 'line' },
]

describe('legendPrefs key / keysMatch', () => {
  it('key 带 kind 与版本 v1', () => {
    expect(legendPrefsKey('trends')).toBe('dailylumen.legend.trends.v1')
  })

  it('键集合完全一致才匹配', () => {
    expect(keysMatch({ 系统分: true, 健康: false, 工作: true }, threeSeries)).toBe(true)
    expect(keysMatch({ 系统分: true, 健康: true }, threeSeries)).toBe(false)
    expect(keysMatch({ 系统分: true, 健康: true, 生活: false }, threeSeries)).toBe(false)
    expect(keysMatch(null, threeSeries)).toBe(false)
  })
})

describe('loadLegendSelected / saveLegendSelected', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('有合法偏好 → 覆盖默认前 2 条', () => {
    const pref = { 系统分: false, 健康: true, 工作: true }
    saveLegendSelected('trends', pref)
    expect(loadLegendSelected('trends', threeSeries)).toEqual(pref)

    const opt = buildChartOption({
      kind: 'trends',
      dates: ['2026-11-01', '2026-11-02'],
      series: threeSeries,
      target: null,
    })
    expect(opt.legend.selected).toEqual(pref)
    expect(defaultLegendSelected(threeSeries, 'trends')).toEqual({
      系统分: true, 健康: true, 工作: false,
    })
  })

  it('无偏好 → 回退 defaultLegendSelected', () => {
    expect(loadLegendSelected('trends', threeSeries)).toBeNull()
    const opt = buildChartOption({
      kind: 'trends',
      dates: ['2026-11-01'],
      series: threeSeries,
      target: null,
    })
    expect(opt.legend.selected).toEqual({ 系统分: true, 健康: true, 工作: false })
  })

  it('JSON 损坏 → null，不抛错', () => {
    localStorage.setItem(legendPrefsKey('trends'), '{not-json')
    expect(() => loadLegendSelected('trends', threeSeries)).not.toThrow()
    expect(loadLegendSelected('trends', threeSeries)).toBeNull()
  })

  it('系列键集合变了 → 失效回退默认', () => {
    saveLegendSelected('trends', { 系统分: true, 健康: false, 工作: true })
    const renamed = [
      ...threeSeries.slice(0, 2),
      { ...threeSeries[2], name: '工作时长' },
    ]
    expect(loadLegendSelected('trends', renamed)).toBeNull()
    const opt = buildChartOption({
      kind: 'trends',
      dates: ['2026-11-01'],
      series: renamed,
      target: null,
    })
    expect(opt.legend.selected).toEqual({ 系统分: true, 健康: true, 工作时长: false })
  })

  it('保存失败（localStorage 不可用）不抛错', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    expect(() => saveLegendSelected('trends', { 系统分: true })).not.toThrow()
    spy.mockRestore()
  })
})
