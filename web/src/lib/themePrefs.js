// B11：主题偏好（light / dark / omni）；版本化 localStorage，损坏或非法值回退系统默认。
// E3 / B22：新增第四态偏好 `auto`（跟随系统，light/dark 二选一；omni 仅显式）。
// 记忆 key 升 v2：读 v1 值迁移 —— light/dark 直接继承为显式；omni 保留显式；auto 不存在于 v1。

export const THEMES = ['light', 'dark', 'omni']
export const THEME_LABELS = {
  auto: '系统',
  light: '青绿',
  dark: '暗色',
  omni: 'Omni',
}

// 切换器呈现顺序：auto 放最前（默认态）
export const PREFS = ['auto', 'light', 'dark', 'omni']

const PREFIX = 'dailylumen.theme.'
const VERSION = 'v2'
// v1 key（读迁移用，不写）
const LEGACY_KEY = `${PREFIX}v1`

export function themePrefsKey() {
  return `${PREFIX}${VERSION}`
}

export function isValidTheme(theme) {
  return THEMES.includes(theme)
}

export function isValidPref(pref) {
  return pref === 'auto' || isValidTheme(pref)
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

/** 解析记忆 JSON（字符串 / {theme}）；非法 → null */
function parsePref(raw) {
  const parsed = JSON.parse(raw)
  const theme = typeof parsed === 'string' ? parsed : parsed?.theme
  return isValidPref(theme) ? theme : null
}

/** 读显式偏好（含 auto）；缺失 / 损坏 → null。v1 记忆自动迁移：light/dark/omni 直接继承。 */
export function loadThemePreference(storage) {
  const store = storage || (typeof localStorage !== 'undefined' ? localStorage : null)
  if (!store) return null
  try {
    const raw = store.getItem(themePrefsKey())
    if (raw) return parsePref(raw)
    // v2 缺失时读 v1 并迁移（lazy：读到即写回 v2）
    const legacy = store.getItem(LEGACY_KEY)
    if (!legacy) return null
    const parsed = JSON.parse(legacy)
    const theme = typeof parsed === 'string' ? parsed : parsed?.theme
    if (isValidTheme(theme)) {
      try {
        store.setItem(themePrefsKey(), JSON.stringify({ theme }))
      } catch {
        // 迁移写失败不影响本次读
      }
      return theme
    }
    return null
  } catch {
    return null
  }
}

/** 写 `{ theme }`（pref ∈ auto/light/dark/omni）；storage 不可用时静默 */
export function saveThemePreference(pref, storage) {
  if (!isValidPref(pref)) return
  const store = storage || (typeof localStorage !== 'undefined' ? localStorage : null)
  if (!store) return
  try {
    store.setItem(themePrefsKey(), JSON.stringify({ theme: pref }))
  } catch {
    // ignore quota / privacy mode
  }
}

/** 偏好 → 实际主题：auto 跟系统；显式直接用 */
export function resolveTheme(pref, mql) {
  if (pref === 'auto') return systemThemePreference(mql)
  if (isValidTheme(pref)) return pref
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

/**
 * E2 / B20：index.html 首屏内联脚本的同源纯函数（两处逻辑必须一致，测试锁定）。
 * 与 loadThemePreference/systemThemePreference 的差异：零依赖、可内联展开（不 import）。
 * localStorage 不可用 / JSON 损坏 / 非法值 → 回退（系统 dark → 'dark'，否则 'light'）。
 * 注：内联脚本只认 v1 三主题（v2 的 auto 在首屏等价于「无显式记忆」——系统判断）。
 */
export function bootTheme(rawStored, prefersDark) {
  if (rawStored) {
    try {
      const parsed = JSON.parse(rawStored)
      const theme = typeof parsed === 'string' ? parsed : parsed?.theme
      if (isValidTheme(theme)) return theme
    } catch {
      // 落到系统判断
    }
  }
  return prefersDark ? 'dark' : 'light'
}
