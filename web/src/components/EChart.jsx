// W16：ECharts 包装组件——在 div 上初始化、卸载时 dispose、窗口 resize 时重绘。
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

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
