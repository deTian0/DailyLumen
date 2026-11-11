import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  applyTheme,
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
    expect(themePrefsKey()).toBe('dailylumen.theme.v1')
    expect(THEMES).toEqual(['light', 'dark', 'omni'])
    expect(isValidTheme('omni')).toBe(true)
    expect(isValidTheme('purple')).toBe(false)
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
})
