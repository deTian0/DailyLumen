// W16 / B3：ECharts 包装——echarts/core 按需注册（对照 chartOption.js 实际字段）。
// B5：监听 legendselectchanged，防抖后按 kind 写入 localStorage。
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
} from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { saveLegendSelected } from '../lib/legendPrefs'

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  SVGRenderer,
])

const SAVE_DEBOUNCE_MS = 300

export function EChart({ option, className, style, ariaLabel, kind }) {
  const ref = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current, null, { renderer: 'svg' })
    chartRef.current = chart
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    if (chartRef.current && option) {
      chartRef.current.setOption(option, true)
    }
  }, [option])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !kind) return undefined
    let timer = null
    const onLegend = (params) => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        saveLegendSelected(kind, params?.selected)
      }, SAVE_DEBOUNCE_MS)
    }
    chart.on('legendselectchanged', onLegend)
    return () => {
      if (timer) clearTimeout(timer)
      chart.off('legendselectchanged', onLegend)
    }
  }, [kind])

  return (
    <div ref={ref} className={className} role="img" aria-label={ariaLabel || '图表'}
      style={{ width: '100%', height: 360, ...style }} />
  )
}
