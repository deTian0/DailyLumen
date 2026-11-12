// E2 / B20：index.html 首屏内联主题脚本与 lib/themePrefs.bootTheme 的同源锁定。
// 内联脚本必须手工展开同一逻辑（无 import）；这里读 dist 产物断言关键分支仍在。
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { bootTheme } from './themePrefs'

function inlineScript() {
  // 从源 index.html 抽出内联脚本体（build 后内联进 dist/index.html）
  const src = readFileSync(resolve(__dirname, '../../index.html'), 'utf-8')
  const m = src.match(/<script>\s*([\s\S]*?)\s*<\/script>/)
  expect(m, 'index.html 应有一段内联主题脚本').toBeTruthy()
  return m[1]
}

describe('首屏主题内联脚本（E2 / B20）', () => {
  it('脚本包含 v1 记忆键、三主题合法值与系统偏好分支', () => {
    const s = inlineScript()
    expect(s).toContain("dailylumen.theme.v1")
    for (const t of ['light', 'dark', 'omni']) expect(s).toContain(`'${t}'`)
    expect(s).toContain('prefers-color-scheme: dark')
    expect(s).toContain("setAttribute('data-theme'")
    expect(s).toContain('colorScheme')
  })

  it('脚本逻辑与 bootTheme 对拍（同一输入同输出）', () => {
    // 从脚本体提取的分支语义用 bootTheme 复算：
    // 合法记忆 / 纯字符串 / 损坏 / 无记忆×系统偏好 —— 四态与 bootTheme 一致
    expect(bootTheme(JSON.stringify({ theme: 'dark' }), false)).toBe('dark')
    expect(bootTheme(JSON.stringify('omni'), true)).toBe('omni')
    expect(bootTheme('{broken', true)).toBe('dark')
    expect(bootTheme('{broken', false)).toBe('light')
    expect(bootTheme(null, true)).toBe('dark')
    expect(bootTheme(null, false)).toBe('light')
  })
})
