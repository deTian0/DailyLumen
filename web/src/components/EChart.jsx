// W16 / B3：ECharts 包装——echarts/core 按需注册（对照 chartOption.js 实际字段）。
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

export function EChart({ option, className, style, ariaLabel }) {
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

  return (
    <div ref={ref} className={className} role="img" aria-label={ariaLabel || '图表'}
      style={{ width: '100%', height: 360, ...style }} />
  )
}
