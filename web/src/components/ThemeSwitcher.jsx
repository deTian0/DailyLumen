// B11：三选一主题切换（胶囊轨，气质对齐 OmniClock segmented control）
import { THEMES, THEME_LABELS } from '../lib/themePrefs'
import { useTheme } from '../lib/ThemeContext'

export default function ThemeSwitcher({ className = '' }) {
  const { theme, setTheme } = useTheme()
  return (
    <div
      className={`theme-switch ${className}`.trim()}
      role="group"
      aria-label="主题"
    >
      {THEMES.map((id) => (
        <button
          key={id}
          type="button"
          className={`theme-switch-btn ${theme === id ? 'active' : ''}`}
          aria-pressed={theme === id}
          onClick={() => setTheme(id)}
        >
          {THEME_LABELS[id]}
        </button>
      ))}
    </div>
  )
}
