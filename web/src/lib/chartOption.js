// W16：把 /api/charts/{kind}.json 的序列转成 ECharts option。
// 纯函数、不依赖 echarts，方便单测；颜色 / 序列名 / 单位全部来自后端 JSON（与 SVG 同源）。
// B5：图例 selected 优先读 localStorage 偏好（系列键集合不匹配则回退默认）。

import { loadLegendSelected } from './legendPrefs'

const baseGrid = { left: 56, right: 24, top: 40, bottom: 56 }

// 图例与刻度字号放大，避免分析页小字难读
const textStyle = { fontSize: 13 }
const legendStyle = { textStyle, itemWidth: 16, itemHeight: 10, itemGap: 16 }
// 日期轴：自动抽稀并避免标签重叠，不再挤成一团
const dateAxis = (dates) => ({
  type: 'category',
  data: dates,
  boundaryGap: false,
  axisLabel: { formatter: shortDate, hideOverlap: true, interval: 'auto', fontSize: 11, margin: 10 },
})

function axisLabel(values, unit) {
  // 数值轴：null 透传给 echarts（自动断点）；单位拼到轴名
  return {
    type: 'value',
    name: unit && unit !== '0-10' ? unit : '',
    axisLabel: { formatter: (v) => (v === null ? '-' : Number.isInteger(v) ? v : v.toFixed(1)) },
  }
}

function lineSeries(s) {
  return {
    name: s.name,
    type: 'line',
    data: s.values,
    yAxisIndex: s.yAxisIndex || 0,
    lineStyle: { color: s.color, width: s.dash ? 1.6 : 1.8, type: s.dash ? 'dashed' : 'solid' },
    itemStyle: { color: s.color },
    symbol: 'circle',
    symbolSize: 3,
    connectNulls: false,
    smooth: false,
  }
}

/** 多线默认只亮 1–2 条主系列，其余可点图例打开（降噪音） */
export function defaultLegendSelected(series, kind) {
  if (!series || series.length <= 2) return undefined
  // nutrition 双轴本来就两条；body 体重+均线也常一起看
  if (kind === 'nutrition' || kind === 'body') return undefined
  const selected = {}
  series.forEach((s, i) => {
    selected[s.name] = i < 2
  })
  return selected
}

export function buildChartOption(data) {
  if (!data || !data.series) return {}
  const { kind, dates, series, target } = data

  if (kind === 'training') {
    const s = series[0]
    return {
      tooltip: { trigger: 'axis', textStyle },
      legend: { show: false },
      grid: baseGrid,
      xAxis: dateAxis(dates),
      yAxis: axisLabel(s.values, s.unit),
      series: [{
        name: s.name, type: 'bar', data: s.values,
        itemStyle: { color: s.color }, barMaxWidth: 24,
      }],
    }
  }

  if (kind === 'nutrition') {
    const pref = loadLegendSelected(kind, series)
    return {
      tooltip: { trigger: 'axis', textStyle },
      legend: {
        show: true, top: 4, selectedMode: true, ...legendStyle,
        ...(pref ? { selected: pref } : {}),
      },
      grid: { ...baseGrid, right: 56 },
      xAxis: dateAxis(dates),
      yAxis: [axisLabel(series[0].values, series[0].unit), axisLabel(series[1].values, series[1].unit)],
      series: series.map(lineSeries),
    }
  }

  // trends / body：单轴多线；B5 偏好覆盖默认前 2 条
  const legendSelected = loadLegendSelected(kind, series) || defaultLegendSelected(series, kind)
  const opt = {
    tooltip: { trigger: 'axis', textStyle },
    legend: {
      show: series.length > 1,
      top: 4,
      data: series.map((s) => s.name),
      selectedMode: true,
      ...legendStyle,
      ...(legendSelected ? { selected: legendSelected } : {}),
    },
    grid: baseGrid,
    xAxis: dateAxis(dates),
    yAxis: axisLabel(series[0].values, series[0].unit),
    series: series.map(lineSeries),
  }

  if (kind === 'body' && target && target.low != null && target.high != null) {
    // 目标带：用第一条序列（体重）的 markArea
    opt.series[0].markArea = {
      silent: true,
      itemStyle: { color: '#bbf7d0', opacity: 0.45 },
      data: [[{ yAxis: target.low }, { yAxis: target.high }]],
    }
    opt.series[0].markLine = {
      silent: true, symbol: 'none',
      lineStyle: { color: '#15803d', type: 'dashed', width: 1 },
      data: [{ yAxis: target.low, label: { formatter: `${target.low}` } },
             { yAxis: target.high, label: { formatter: `${target.high}` } }],
    }
  }
  return opt
}

export function shortDate(iso) {
  if (!iso) return ''
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return m ? `${m[2]}-${m[3]}` : iso
}
