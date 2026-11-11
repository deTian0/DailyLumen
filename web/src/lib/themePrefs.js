// B11：主题偏好（light / dark / omni）；版本化 localStorage，损坏或非法值回退系统默认。

export const THEMES = ['light', 'dark', 'omni']
export const THEME_LABELS = {
  light: '青绿',
  dark: '暗色',
  omni: 'Omni',
}

const PREFIX = 'dailylumen.theme.'
const VERSION = 'v1'

export function themePrefsKey() {
  return `${PREFIX}${VERSION}`
}

export function isValidTheme(theme) {
  return THEMES.includes(theme)
}

/** prefers-color-scheme 只映射 light/dark；omni 永不由系统自动选中 */
export function systemThemePreference(mql) {
  try {
    const media = mql || (typeof window !== 'undefined'
      ? window.matchMedia?.('(prefers-color-scheme: dark)')
      : null)
    if (media?.matches) return 'dark'
  } catch {
    // jsdom / 无 matchMedia
  }
  return 'light'
}

/** 合法偏好 → 主题 id；缺失 / 损坏 / 非法 → null */
export function loadThemePreference(storage) {
  const store = storage || (typeof localStorage !== 'undefined' ? localStorage : null)
  if (!store) return null
  try {
    const raw = store.getItem(themePrefsKey())
    if (!raw) return null
    const parsed = JSON.parse(raw)
    const theme = typeof parsed === 'string' ? parsed : parsed?.theme
    return isValidTheme(theme) ? theme : null
  } catch {
    return null
  }
}

/** 写 `{ theme }`；storage 不可用时静默 */
export function saveThemePreference(theme, storage) {
  if (!isValidTheme(theme)) return
  const store = storage || (typeof localStorage !== 'undefined' ? localStorage : null)
  if (!store) return
  try {
    store.setItem(themePrefsKey(), JSON.stringify({ theme }))
  } catch {
    // ignore quota / privacy mode
  }
}

/** 有记忆用记忆；否则系统 light/dark */
export function resolveTheme(stored, mql) {
  if (isValidTheme(stored)) return stored
  return systemThemePreference(mql)
}

/** 写到 <html data-theme> + color-scheme（原生控件） */
export function applyTheme(theme) {
  const t = isValidTheme(theme) ? theme : 'light'
  if (typeof document === 'undefined') return t
  document.documentElement.setAttribute('data-theme', t)
  document.documentElement.style.colorScheme = t === 'dark' ? 'dark' : 'light'
  return t
}

/** 读当前 DOM 主题（无则 light） */
export function readDomTheme() {
  if (typeof document === 'undefined') return 'light'
  const t = document.documentElement.getAttribute('data-theme')
  return isValidTheme(t) ? t : 'light'
}
