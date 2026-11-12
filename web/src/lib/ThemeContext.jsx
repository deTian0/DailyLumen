// B11：主题 Context——启动读偏好 / 系统默认，切换时写 localStorage 并 applyTheme。
// E3 / B22：偏好可为 `auto`（跟随系统 light/dark，实时监听；omni 仅显式）。
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  applyTheme,
  loadThemePreference,
  resolveTheme,
  saveThemePreference,
  systemThemePreference,
} from './themePrefs'

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  // pref = 显式偏好（auto / light / dark / omni）；theme = 实际渲染主题
  const [pref, setPrefState] = useState(() => loadThemePreference() || 'auto')
  const [theme, setThemeState] = useState(() => resolveTheme(pref))

  const setTheme = useCallback((next) => {
    if (next !== 'auto' && next !== 'light' && next !== 'dark' && next !== 'omni') return
    saveThemePreference(next)
    setPrefState(next)
    const applied = resolveTheme(next)
    setThemeState(applyTheme(applied))
  }, [])

  // auto（或无显式偏好）时跟随系统 light/dark 变化；显式选 omni / light / dark 不跟
  useEffect(() => {
    const mql = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mql) return undefined
    const onChange = () => {
      const stored = loadThemePreference()
      if (stored && stored !== 'auto') return
      const applied = systemThemePreference(mql)
      setPrefState((p) => (p === 'auto' || !p ? 'auto' : p))
      setThemeState(applyTheme(applied))
    }
    mql.addEventListener?.('change', onChange)
    return () => mql.removeEventListener?.('change', onChange)
  }, [])

  const value = useMemo(() => ({ theme, pref, setTheme }), [theme, pref, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme 须在 ThemeProvider 内使用')
  return ctx
}
