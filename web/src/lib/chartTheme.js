// B19：图表系列色的主题映射。
// 后端 JSON / SVG 仍是数据与默认色的单一来源；这里只调整前端展示色，
// 让浅色/暗色表面上的折线都达到图形 3:1。未知 key 回退后端 color。
//
// 取值原则：同 hue 加深（light / omni）或提亮（dark），不改变系列语义。

const LIGHT = {
  system_score: '#1d4ed8',
  health_score: '#15803d',
  work_score: '#a16207',
  learn_score: '#7e22ce',
  life_score: '#be185d',
  sleep_h: '#0e7490',
  phone_h: '#c2410c',
  weight_kg: '#1d4ed8',
  ma7: '#c2410c',
  exercise_min: '#15803d',
  diet_kcal: '#c2410c',
}

const DARK = {
  system_score: '#60a5fa',
  health_score: '#4ade80',
  work_score: '#facc15',
  learn_score: '#c084fc',
  life_score: '#f472b6',
  sleep_h: '#22d3ee',
  phone_h: '#fb923c',
  weight_kg: '#60a5fa',
  ma7: '#fb923c',
  exercise_min: '#4ade80',
  diet_kcal: '#fb923c',
}

const FALLBACK = '#109485'

export function paletteFor(theme) {
  return theme === 'dark' ? DARK : LIGHT
}

export function seriesColor(series, theme) {
  const palette = paletteFor(theme)
  return (series && palette[series.key]) || series?.color || FALLBACK
}
