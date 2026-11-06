import { describe, expect, it } from 'vitest'
import { buildChartOption, defaultLegendSelected, shortDate } from './chartOption'

const series = (over = {}) => ({
  kind: 'trends',
  dates: ['2026-11-01', '2026-11-02', '2026-11-03'],
  series: [
    { key: 'system_score', name: '系统分', color: '#2563eb', unit: '0-10',
      values: [4.0, null, 5.0], type: 'line' },
    { key: 'health_score', name: '健康', color: '#16a34a', unit: '0-10',
      values: [3.0, 4.0, 4.0], type: 'line' },
  ],
  target: null,
  ...over,
})

describe('buildChartOption trends', () => {
  it('多线、x 轴 category=dates、y 轴单位取首序列、legend 多于 1 条才显示', () => {
    const opt = buildChartOption(series())
    expect(opt.xAxis.type).toBe('category')
    expect(opt.xAxis.data).toEqual(['2026-11-01', '2026-11-02', '2026-11-03'])
    expect(opt.yAxis.type).toBe('value')
    expect(opt.series).toHaveLength(2)
    expect(opt.series[0].name).toBe('系统分')
    expect(opt.series[0].lineStyle.color).toBe('#2563eb')
    expect(opt.series[0].data).toEqual([4.0, null, 5.0])
    expect(opt.series[0].connectNulls).toBe(false)
    expect(opt.legend.show).toBe(true)
  })

  it('单序列时 legend 不显示', () => {
    const opt = buildChartOption({ ...series(), series: [series().series[0]] })
    expect(opt.legend.show).toBe(false)
  })

  it('≥3 条时默认只选前两条，其余图例可切', () => {
    const three = {
      ...series(),
      series: [
        ...series().series,
        { key: 'work_score', name: '工作', color: '#ea580c', unit: '0-10', values: [5, 5, 6], type: 'line' },
      ],
    }
    const opt = buildChartOption(three)
    expect(opt.legend.selected).toEqual({ 系统分: true, 健康: true, 工作: false })
    expect(defaultLegendSelected(three.series, 'trends')).toEqual({ 系统分: true, 健康: true, 工作: false })
  })
})

describe('buildChartOption training', () => {
  it('柱状图：type=bar、颜色来自序列、y 轴单位=分钟', () => {
    const opt = buildChartOption({
      kind: 'training',
      dates: ['2026-11-01'],
      series: [{ key: 'exercise_min', name: '训练量', color: '#16a34a',
        unit: '分钟', values: [30], type: 'bar' }],
      target: null,
    })
    expect(opt.series[0].type).toBe('bar')
    expect(opt.series[0].itemStyle.color).toBe('#16a34a')
    expect(opt.yAxis.name).toBe('分钟')
    expect(opt.legend.show).toBe(false)
  })
})

describe('buildChartOption nutrition', () => {
  it('双轴：yAxis 长度 2、各序列 yAxisIndex 0/1、grid 右侧留 56', () => {
    const opt = buildChartOption({
      kind: 'nutrition',
      dates: ['2026-11-01'],
      series: [
        { key: 'diet_kcal', name: '热量', color: '#ea580c', unit: 'kcal', values: [1800], type: 'line', yAxisIndex: 0 },
        { key: 'weight_kg', name: '体重', color: '#2563eb', unit: 'kg', values: [62], type: 'line', yAxisIndex: 1 },
      ],
      target: null,
    })
    expect(opt.yAxis).toHaveLength(2)
    expect(opt.series[0].yAxisIndex).toBe(0)
    expect(opt.series[1].yAxisIndex).toBe(1)
    expect(opt.grid.right).toBe(56)
  })
})

describe('buildChartOption body 目标带', () => {
  it('有 target 时给首序列加 markArea + markLine', () => {
    const opt = buildChartOption({
      kind: 'body',
      dates: ['2026-11-01'],
      series: [
        { key: 'weight_kg', name: '体重', color: '#2563eb', unit: 'kg', values: [62], type: 'line' },
        { key: 'ma7', name: '7日均', color: '#ea580c', unit: 'kg', values: [62], type: 'line', dash: true },
      ],
      target: { low: 60, high: 65 },
    })
    expect(opt.series[0].markArea).toBeDefined()
    expect(opt.series[0].markLine).toBeDefined()
    expect(opt.series[1].lineStyle.type).toBe('dashed')
  })

  it('无 target 时不加 markArea', () => {
    const opt = buildChartOption({
      kind: 'body', dates: ['2026-11-01'],
      series: [{ key: 'weight_kg', name: '体重', color: '#2563eb', unit: 'kg', values: [62], type: 'line' }],
      target: null,
    })
    expect(opt.series[0].markArea).toBeUndefined()
  })
})

describe('shortDate', () => {
  it('ISO 日期 → MM-DD', () => {
    expect(shortDate('2026-11-06')).toBe('11-06')
    expect(shortDate('')).toBe('')
  })
})
