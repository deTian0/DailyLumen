// B19：主题 token 的自动回归——对比度、变量完整性、硬编码色。
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const STYLE_DIR = dirname(fileURLToPath(import.meta.url))
const TOKENS_CSS = readFileSync(join(STYLE_DIR, 'tokens.css'), 'utf8')

function themeBlock(selector) {
  const idx = TOKENS_CSS.indexOf(selector)
  if (idx < 0) throw new Error(`未找到主题块：${selector}`)
  const start = TOKENS_CSS.indexOf('{', idx)
  let depth = 0
  for (let i = start; i < TOKENS_CSS.length; i += 1) {
    if (TOKENS_CSS[i] === '{') depth += 1
    if (TOKENS_CSS[i] === '}') {
      depth -= 1
      if (depth === 0) return TOKENS_CSS.slice(start + 1, i)
    }
  }
  throw new Error(`主题块未闭合：${selector}`)
}

function tokensOf(block) {
  const map = {}
  for (const m of block.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
    map[`--${m[1]}`] = m[2].trim()
  }
  return map
}

const THEMES = {
  light: tokensOf(themeBlock('[data-theme="light"]')),
  dark: tokensOf(themeBlock('[data-theme="dark"]')),
  omni: tokensOf(themeBlock('[data-theme="omni"]')),
}

function parseColor(value) {
  const v = value.trim()
  if (v.startsWith('#')) {
    const h = v.slice(1)
    if (h.length === 3) {
      return { r: parseInt(h[0] + h[0], 16), g: parseInt(h[1] + h[1], 16), b: parseInt(h[2] + h[2], 16), a: 1 }
    }
    if (h.length === 6) {
      return {
        r: parseInt(h.slice(0, 2), 16),
        g: parseInt(h.slice(2, 4), 16),
        b: parseInt(h.slice(4, 6), 16),
        a: 1,
      }
    }
  }
  const m = v.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)$/i)
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] }
  throw new Error(`无法解析颜色：${value}`)
}

function over(fg, bg) {
  const a = fg.a ?? 1
  return {
    r: Math.round(fg.r * a + bg.r * (1 - a)),
    g: Math.round(fg.g * a + bg.g * (1 - a)),
    b: Math.round(fg.b * a + bg.b * (1 - a)),
    a: 1,
  }
}

function luminance({ r, g, b }) {
  const f = (c) => {
    const x = c / 255
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function contrast(fg, bg) {
  const [hi, lo] = [luminance(fg), luminance(bg)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

function ratio(tokens, fgToken, bgToken) {
  const surface = parseColor(tokens['--surface'])
  let bg = parseColor(tokens[bgToken])
  if (bg.a < 1) bg = over(bg, surface)
  let fg = parseColor(tokens[fgToken])
  if (fg.a < 1) fg = over(fg, bg)
  return contrast(fg, bg)
}

const PAIRS = [
  ['--text', '--surface', 4.5],
  ['--text', '--bg', 4.5],
  ['--text', '--surface-2', 4.5],
  ['--muted', '--surface', 4.5],
  ['--muted', '--bg', 4.5],
  ['--muted', '--surface-2', 4.5],
  ['--accent-ink', '--surface', 4.5],
  ['--accent-ink', '--bg', 4.5],
  ['--accent-ink', '--accent-soft', 4.5],
  ['--on-accent', '--accent-strong', 4.5],
  ['--on-status', '--ink-green', 4.5],
  ['--ink-green', '--surface', 4.5],
  ['--ink-red', '--surface', 4.5],
  ['--ink-amber', '--surface', 4.5],
  ['--ink-blue', '--accent-soft', 4.5],
  ['--border-input', '--surface', 3.0],
]

describe('tokens.css 对比度', () => {
  for (const [theme, tokens] of Object.entries(THEMES)) {
    it(`${theme} 主题：正文 ≥4.5、输入框边界 ≥3.0`, () => {
      for (const [fg, bg, min] of PAIRS) {
        expect(tokens[fg], `${theme} 缺少 ${fg}`).toBeTruthy()
        expect(tokens[bg], `${theme} 缺少 ${bg}`).toBeTruthy()
        expect(ratio(tokens, fg, bg), `${theme}: ${fg} on ${bg}`).toBeGreaterThanOrEqual(min)
      }
    })
  }

  it('三套主题都定义了 accent 三层与 on 色', () => {
    for (const tokens of Object.values(THEMES)) {
      for (const key of ['--accent', '--accent-strong', '--accent-ink', '--on-accent', '--on-status']) {
        expect(tokens[key], `缺少 ${key}`).toBeTruthy()
      }
    }
  })
})

describe('样式变量完整性', () => {
  const files = readdirSync(STYLE_DIR).filter((f) => f.endsWith('.css'))
  const css = files.map((f) => readFileSync(join(STYLE_DIR, f), 'utf8')).join('\n')
  const defined = new Set([...css.matchAll(/--([\w-]+)\s*:/g)].map((m) => `--${m[1]}`))
  const referenced = new Set([...css.matchAll(/var\(--([\w-]+)/g)].map((m) => `--${m[1]}`))

  it('所有 var(--x) 都有定义', () => {
    expect([...referenced].filter((x) => !defined.has(x))).toEqual([])
  })

  it('tokens.css 之外没有业务硬编码色', () => {
    for (const file of files.filter((f) => f !== 'tokens.css')) {
      const text = readFileSync(join(STYLE_DIR, file), 'utf8')
      expect(text, `${file} 含 hex`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
      expect(text, `${file} 含 rgba`).not.toMatch(/rgba?\(/)
    }
  })
})
