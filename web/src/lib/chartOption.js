// W16：把 /api/charts/{kind}.json 的序列转成 ECharts option。
// 纯函数、不依赖 echarts，方便单测；颜色 / 序列名 / 单位全部来自后端 JSON（与 SVG 同源）。
// B5：图例 selected 优先读 localStorage 偏好（系列键集合不匹配则回退默认）。
// B11：坐标轴 / 图例 / tooltip / 目标带 chrome 跟随主题。

import { loadLegendSelected } from './legendPrefs'
import { isValidTheme, readDomTheme } from './themePrefs'

const baseGrid = { left: 56, right: 24, top: 40, bottom: 56 }

/** 图表 chrome 色（与 tokens.css --chart-* 对齐；纯函数可测） */
export function chartChrome(theme) {
  const t = isValidTheme(theme) ? theme : 'light'
  if (t === 'dark') {
    return {
      text: '#c8d0d8',
      axis: '#8a96a4',
      split: 'rgba(255,255,255,0.08)',
      tooltipBg: '#1e2836',
      tooltipBorder: 'rgba(255,255,255,0.12)',
      markArea: 'rgba(45, 212, 191, 0.18)',
      markLine: '#5eead4',
    }
  }
  if (t === 'omni') {
    return {
      text: '#3a3a3c',
      axis: '#8e8e93',
      split: 'rgba(60,60,67,0.1)',
      tooltipBg: '#ffffff',
      tooltipBorder: 'rgba(60,60,67,0.14)',
      markArea: 'rgba(52, 199, 89, 0.22)',
      markLine: '#248a3d',
    }
  }
  return {
    text: '#3a4a58',
    axis: '#6b7785',
    split: 'rgba(26,45,40,0.08)',
    tooltipBg: '#ffffff',
    tooltipBorder: 'rgba(26,45,40,0.12)',
    markArea: '#bbf7d0',
    markLine: '#15803d',
  }
}

function chromeStyles(theme) {
  const c = chartChrome(theme)
  const textStyle = { fontSize: 13, color: c.text }
  const legendStyle = {
    textStyle,
    itemWidth: 16,
    itemHeight: 10,
    itemGap: 16,
  }
  const axisCommon = {
    axisLine: { lineStyle: { color: c.axis } },
    axisTick: { lineStyle: { color: c.axis } },
    axisLabel: { color: c.axis },
    splitLine: { lineStyle: { color: c.split } },
  }
  const tooltip = {
    trigger: 'axis',
    textStyle,
    backgroundColor: c.tooltipBg,
    borderColor: c.tooltipBorder,
    borderWidth: 1,
  }
  return { c, textStyle, legendStyle, axisCommon, tooltip }
}

// 日期轴：自动抽稀并避免标签重叠，不再挤成一团
const dateAxis = (dates, axisCommon) => ({
  type: 'category',
  data: dates,
  boundaryGap: false,
  ...axisCommon,
  axisLabel: {
    ...axisCommon.axisLabel,
    formatter: shortDate,
    hideOverlap: true,
    interval: 'auto',
    fontSize: 11,
    margin: 10,
  },
  splitLine: { show: false },
})

function axisLabel(values, unit, axisCommon) {
  // 数值轴：null 透传给 echarts（自动断点）；单位拼到轴名
  return {
    type: 'value',
    name: unit && unit !== '0-10' ? unit : '',
    nameTextStyle: { color: axisCommon.axisLabel.color },
    ...axisCommon,
    axisLabel: {
      ...axisCommon.axisLabel,
      formatter: (v) => (v === null ? '-' : Number.isInteger(v) ? v : v.toFixed(1)),
    },
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

export function buildChartOption(data, theme) {
  if (!data || !data.series) return {}
  const { kind, dates, series, target } = data
  const t = isValidTheme(theme) ? theme : readDomTheme()
  const { c, textStyle, legendStyle, axisCommon, tooltip } = chromeStyles(t)

  if (kind === 'training') {
    const s = series[0]
    return {
      tooltip,
      legend: { show: false },
      grid: baseGrid,
      xAxis: dateAxis(dates, axisCommon),
      yAxis: axisLabel(s.values, s.unit, axisCommon),
      series: [{
        name: s.name, type: 'bar', data: s.values,
        itemStyle: { color: s.color }, barMaxWidth: 24,
      }],
      textStyle,
    }
  }

  if (kind === 'nutrition') {
    const pref = loadLegendSelected(kind, series)
    return {
      tooltip,
      legend: {
        show: true, top: 4, selectedMode: true, ...legendStyle,
        ...(pref ? { selected: pref } : {}),
      },
      grid: { ...baseGrid, right: 56 },
      xAxis: dateAxis(dates, axisCommon),
      yAxis: [
        axisLabel(series[0].values, series[0].unit, axisCommon),
        axisLabel(series[1].values, series[1].unit, axisCommon),
      ],
      series: series.map(lineSeries),
      textStyle,
    }
  }

  // trends / body：单轴多线；B5 偏好覆盖默认前 2 条
  const legendSelected = loadLegendSelected(kind, series) || defaultLegendSelected(series, kind)
  const opt = {
    tooltip,
    legend: {
      show: series.length > 1,
      top: 4,
      data: series.map((s) => s.name),
      selectedMode: true,
      ...legendStyle,
      ...(legendSelected ? { selected: legendSelected } : {}),
    },
    grid: baseGrid,
    xAxis: dateAxis(dates, axisCommon),
    yAxis: axisLabel(series[0].values, series[0].unit, axisCommon),
    series: series.map(lineSeries),
    textStyle,
  }

  if (kind === 'body' && target && target.low != null && target.high != null) {
    // 目标带：用第一条序列（体重）的 markArea
    opt.series[0].markArea = {
      silent: true,
      itemStyle: { color: c.markArea, opacity: t === 'dark' ? 1 : 0.45 },
      data: [[{ yAxis: target.low }, { yAxis: target.high }]],
    }
    opt.series[0].markLine = {
      silent: true, symbol: 'none',
      lineStyle: { color: c.markLine, type: 'dashed', width: 1 },
      data: [{ yAxis: target.low, label: { formatter: `${target.low}`, color: c.markLine } },
             { yAxis: target.high, label: { formatter: `${target.high}`, color: c.markLine } }],
    }
  }
  return opt
}

export function shortDate(iso) {
  if (!iso) return ''
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return m ? `${m[2]}-${m[3]}` : iso
}
