// B11 三主题 → E3 / B22：四态切换（系统 / 青绿 / 暗色 / Omni；胶囊轨）。
// 「系统」= 跟随 prefers-color-scheme（light/dark 二选一，实时变）；omni 仅显式。
import { PREFS, THEME_LABELS } from '../lib/themePrefs'
import { useTheme } from '../lib/ThemeContext'

export default function ThemeSwitcher({ className = '' }) {
  const { pref, theme, setTheme } = useTheme()
  return (
    <div
      className={`theme-switch ${className}`.trim()}
      role="group"
      aria-label="主题"
    >
      {PREFS.map((id) => (
        <button
          key={id}
          type="button"
          className={`theme-switch-btn ${pref === id ? 'active' : ''}`}
          aria-pressed={pref === id}
          title={id === 'auto' ? `跟随系统（当前 ${THEME_LABELS[theme]}）` : undefined}
          onClick={() => setTheme(id)}
        >
          {THEME_LABELS[id]}
        </button>
      ))}
    </div>
  )
}
