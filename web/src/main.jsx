import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/app.css'
import App from './App.jsx'
import { ThemeProvider } from './lib/ThemeContext'
import { applyTheme, loadThemePreference, resolveTheme } from './lib/themePrefs'

// B11：首屏前应用主题，减少闪烁
applyTheme(resolveTheme(loadThemePreference()))

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
)
