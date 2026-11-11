// B11：主题 Context——启动读偏好 / 系统默认，切换时写 localStorage 并 applyTheme。
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
  const [theme, setThemeState] = useState(() => {
    const initial = resolveTheme(loadThemePreference())
    applyTheme(initial)
    return initial
  })

  const setTheme = useCallback((next) => {
    const applied = applyTheme(next)
    saveThemePreference(applied)
    setThemeState(applied)
  }, [])

  // 无手动偏好时，跟随系统 light/dark 变化（omni 仅显式）
  useEffect(() => {
    const mql = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mql) return undefined
    const onChange = () => {
      if (loadThemePreference() != null) return
      const next = systemThemePreference(mql)
      applyTheme(next)
      setThemeState(next)
    }
    mql.addEventListener?.('change', onChange)
    return () => mql.removeEventListener?.('change', onChange)
  }, [])

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme 须在 ThemeProvider 内使用')
  return ctx
}
