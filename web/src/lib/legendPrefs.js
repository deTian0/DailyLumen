// B5：图表图例开关按 kind 持久到 localStorage；系列键集合变化或损坏时失效。

const PREFIX = 'dailylumen.legend.'
const VERSION = 'v1'

export function legendPrefsKey(kind) {
  return `${PREFIX}${kind}.${VERSION}`
}

function seriesNames(series) {
  return (series || []).map((s) => s.name)
}

/** selected 的键集合须与当前 series 名完全一致，否则视为失效 */
export function keysMatch(selected, series) {
  if (!selected || typeof selected !== 'object' || Array.isArray(selected)) return false
  const names = seriesNames(series)
  const keys = Object.keys(selected)
  if (keys.length !== names.length) return false
  const set = new Set(names)
  return keys.every((k) => set.has(k))
}

/** 合法偏好 → 对象；缺失 / 损坏 / 系列变更 → null（调用方回退 defaultLegendSelected） */
export function loadLegendSelected(kind, series) {
  if (!kind) return null
  try {
    const raw = localStorage.getItem(legendPrefsKey(kind))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!keysMatch(parsed, series)) return null
    return parsed
  } catch {
    return null
  }
}

/** 写前 stringify；localStorage 不可用时静默 */
export function saveLegendSelected(kind, selected) {
  if (!kind || !selected || typeof selected !== 'object') return
  try {
    localStorage.setItem(legendPrefsKey(kind), JSON.stringify(selected))
  } catch {
    // ignore quota / privacy mode
  }
}
