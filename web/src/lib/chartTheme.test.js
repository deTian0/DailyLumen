import { describe, expect, it } from 'vitest'
import { paletteFor, seriesColor } from './chartTheme'

function luminance(hex) {
  const h = hex.replace('#', '')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  const f = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const SURFACE = { light: '#ffffff', dark: '#1a2330', omni: '#ffffff' }

describe('chartTheme', () => {
  it('light / omni 用浅色系映射，dark 用提亮映射', () => {
    expect(paletteFor('light')).toBe(paletteFor('omni'))
    expect(paletteFor('light')).not.toBe(paletteFor('dark'))
    expect(seriesColor({ key: 'learn_score', color: '#9333ea' }, 'dark')).toBe('#c084fc')
    expect(seriesColor({ key: 'work_score', color: '#ca8a04' }, 'light')).toBe('#a16207')
  })

  it('未知 key 回退后端 color；无 color 时用兜底色', () => {
    expect(seriesColor({ key: 'future_series', color: '#123456' }, 'dark')).toBe('#123456')
    expect(seriesColor({ key: 'future_series' }, 'light')).toBe('#109485')
    expect(seriesColor(null, 'light')).toBe('#109485')
  })

  it('每个映射色在对应主题表面 ≥ 3:1（图形对比度）', () => {
    for (const theme of ['light', 'dark']) {
      const palette = paletteFor(theme)
      for (const [key, color] of Object.entries(palette)) {
        const ratio = contrast(color, SURFACE[theme])
        expect(ratio, `${theme}/${key} ${color} vs ${SURFACE[theme]}`).toBeGreaterThanOrEqual(3)
      }
    }
  })
})
