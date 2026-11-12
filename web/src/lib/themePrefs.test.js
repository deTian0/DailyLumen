import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  applyTheme,
  bootTheme,
  isValidPref,
  isValidTheme,
  loadThemePreference,
  resolveTheme,
  saveThemePreference,
  systemThemePreference,
  themePrefsKey,
  THEMES,
} from './themePrefs'

describe('themePrefs key / validity', () => {
  it('版本化 key 与合法集合', () => {
    expect(themePrefsKey()).toBe('dailylumen.theme.v2')
    expect(THEMES).toEqual(['light', 'dark', 'omni'])
    expect(isValidTheme('omni')).toBe(true)
    expect(isValidTheme('purple')).toBe(false)
    expect(isValidPref('auto')).toBe(true)
    expect(isValidPref('neon')).toBe(false)
  })
})

describe('systemThemePreference', () => {
  it('仅映射 light/dark，不返回 omni', () => {
    expect(systemThemePreference({ matches: true })).toBe('dark')
    expect(systemThemePreference({ matches: false })).toBe('light')
    expect(systemThemePreference(null)).toBe('light')
  })
})

describe('load / save / resolve', () => {
  let store
  beforeEach(() => {
    store = {
      _data: {},
      getItem(k) { return Object.prototype.hasOwnProperty.call(this._data, k) ? this._data[k] : null },
      setItem(k, v) { this._data[k] = String(v) },
      removeItem(k) { delete this._data[k] },
    }
  })

  it('缺省 → null；resolve 回退系统', () => {
    expect(loadThemePreference(store)).toBeNull()
    expect(resolveTheme(null, { matches: true })).toBe('dark')
    expect(resolveTheme(null, { matches: false })).toBe('light')
  })

  it('合法 JSON 记忆优先于系统', () => {
    saveThemePreference('omni', store)
    expect(loadThemePreference(store)).toBe('omni')
    expect(resolveTheme(loadThemePreference(store), { matches: true })).toBe('omni')
  })

  it('损坏 JSON / 非法主题 → null', () => {
    store.setItem(themePrefsKey(), '{not-json')
    expect(loadThemePreference(store)).toBeNull()
    store.setItem(themePrefsKey(), JSON.stringify({ theme: 'neon' }))
    expect(loadThemePreference(store)).toBeNull()
    store.setItem(themePrefsKey(), JSON.stringify('neon'))
    expect(loadThemePreference(store)).toBeNull()
  })

  it('兼容纯字符串偏好', () => {
    store.setItem(themePrefsKey(), JSON.stringify('dark'))
    expect(loadThemePreference(store)).toBe('dark')
  })

  it('非法 save 不写盘', () => {
    saveThemePreference('nope', store)
    expect(store.getItem(themePrefsKey())).toBeNull()
  })

  it('E3/B22：auto 合法且可存取', () => {
    saveThemePreference('auto', store)
    expect(loadThemePreference(store)).toBe('auto')
  })

  it('E3/B22：v1 记忆迁移到 v2（light/dark/omni 直接继承）', () => {
    store.setItem('dailylumen.theme.v1', JSON.stringify({ theme: 'dark' }))
    expect(loadThemePreference(store)).toBe('dark')
    expect(JSON.parse(store.getItem(themePrefsKey())).theme).toBe('dark')
    // 迁移是一次性的：v2 已写则不再读 v1 —— 先清 v2 再测第二个迁移
    store.removeItem(themePrefsKey())
    store.setItem('dailylumen.theme.v1', JSON.stringify('omni'))
    expect(loadThemePreference(store)).toBe('omni')
  })
})

describe('applyTheme', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
  })

  it('写 data-theme 与 color-scheme', () => {
    applyTheme('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
    applyTheme('omni')
    expect(document.documentElement.getAttribute('data-theme')).toBe('omni')
    expect(document.documentElement.style.colorScheme).toBe('light')
  })

  it('非法主题回退 light', () => {
    applyTheme('zzz')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})

describe('matchMedia 跟随（无记忆时）', () => {
  it('有记忆时 resolve 不跟系统', () => {
    expect(resolveTheme('light', { matches: true })).toBe('light')
  })
  it('E3/B22：auto 跟系统；omni 不被 auto 吞（显式优先）', () => {
    expect(resolveTheme('auto', { matches: true })).toBe('dark')
    expect(resolveTheme('auto', { matches: false })).toBe('light')
    expect(resolveTheme('omni', { matches: false })).toBe('omni')
  })
})

describe('bootTheme（E2 / B20：index.html 内联脚本同源纯函数）', () => {
  it('合法记忆优先；纯字符串兼容', () => {
    expect(bootTheme(JSON.stringify({ theme: 'omni' }), true)).toBe('omni')
    expect(bootTheme(JSON.stringify('dark'), false)).toBe('dark')
  })
  it('无记忆 → 系统 light/dark', () => {
    expect(bootTheme(null, true)).toBe('dark')
    expect(bootTheme(null, false)).toBe('light')
    expect(bootTheme(undefined, true)).toBe('dark')
  })
  it('损坏 JSON / 非法值 → 系统回退', () => {
    expect(bootTheme('{not-json', true)).toBe('dark')
    expect(bootTheme(JSON.stringify({ theme: 'neon' }), false)).toBe('light')
  })
})
