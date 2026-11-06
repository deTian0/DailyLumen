// W16：把 /api/charts/{kind}.json 的序列转成 ECharts option。
// 纯函数、不依赖 echarts，方便单测；颜色 / 序列名 / 单位全部来自后端 JSON（与 SVG 同源）。

const baseGrid = { left: 56, right: 24, top: 36, bottom: 56 }

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
    symbolSize: 4,
    connectNulls: false,
    smooth: false,
  }
}

export function buildChartOption(data) {
  if (!data || !data.series) return {}
  const { kind, dates, series, target } = data

  if (kind === 'training') {
    const s = series[0]
    return {
      tooltip: { trigger: 'axis' },
      legend: { show: false },
      grid: baseGrid,
      xAxis: { type: 'category', data: dates, axisLabel: { formatter: shortDate } },
      yAxis: axisLabel(s.values, s.unit),
      series: [{
        name: s.name, type: 'bar', data: s.values,
        itemStyle: { color: s.color }, barMaxWidth: 24,
      }],
    }
  }

  if (kind === 'nutrition') {
    return {
      tooltip: { trigger: 'axis' },
      legend: { show: true, top: 4 },
      grid: { ...baseGrid, right: 56 },
      xAxis: { type: 'category', data: dates, axisLabel: { formatter: shortDate } },
      yAxis: [axisLabel(series[0].values, series[0].unit), axisLabel(series[1].values, series[1].unit)],
      series: series.map(lineSeries),
    }
  }

  // trends / body：单轴多线
  const opt = {
    tooltip: { trigger: 'axis' },
    legend: { show: series.length > 1, top: 4, data: series.map((s) => s.name) },
    grid: baseGrid,
    xAxis: { type: 'category', data: dates, axisLabel: { formatter: shortDate } },
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
