import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './lib/api'
import { useAsync } from './lib/useAsync'
import { hashPage } from './lib/route'
import Today from './pages/Today.jsx'
import Reports from './pages/Reports.jsx'
import Analytics from './pages/Analytics.jsx'
import Doctor from './pages/Doctor.jsx'
import Life from './pages/Life.jsx'

const NAV = [
  { id: 'today', label: '今日看板', ico: '⌂', Page: Today },
  { id: 'life', label: '生活管家', ico: '♥', Page: Life },
  { id: 'reports', label: '复盘与报告', ico: '◎', Page: Reports },
  { id: 'analytics', label: '分析', ico: '▤', Page: Analytics },
  { id: 'doctor', label: '体检', ico: '✚', Page: Doctor },
]

// 轻量 hash 路由：无第三方依赖，刷新/收藏/前进后退都可用
// W12：允许 #/reports?tab=ctx 这类查询串（页内 tab 自己读 hashQuery）
const readHash = () => {
  const id = hashPage()
  return NAV.some((n) => n.id === id) ? id : 'today'
}

export default function App() {
  const [page, setPage] = useState(readHash)
  const [toastMsg, setToastMsg] = useState('')
  const timer = useRef(null)
  const health = useAsync((signal) => api.health({ signal }), [])

  useEffect(() => {
    const onHash = () => setPage(readHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const toast = useCallback((msg) => {
    setToastMsg(msg)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setToastMsg(''), 3200)
  }, [])

  const cur = NAV.find((n) => n.id === page) || NAV[0]
  const Page = cur.Page
  const h = health.data

  return (
    <div className="app">
      <a className="skip-link" href="#main">跳到主要内容</a>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">DL</div>
          DailyLumen
        </div>
        <nav aria-label="主导航" className="nav">
          {NAV.map((n) => (
            <a
              key={n.id}
              href={`#/${n.id}`}
              className={`nav-item ${n.id === page ? 'active' : ''}`}
              aria-current={n.id === page ? 'page' : undefined}
            >
              <span className="ico" aria-hidden="true">{n.ico}</span>
              {n.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="env" aria-live="polite">
            {health.error ? (
              <span className="env-bad">服务未连接</span>
            ) : h ? (
              <>
                <span className="env-ok">● 本机 · {h.readonly ? '只读' : '写已开启（预览后确认）'}</span>
                <span className="env-sub">v{h.version} · 无鉴权，仅限本机</span>
              </>
            ) : (
              <span className="env-sub">连接中…</span>
            )}
          </div>
        </div>
      </aside>

      <main className="main" id="main" tabIndex={-1}>
        {health.error && (
          <div className="banner banner-warn" role="alert">
            无法连接本机服务。请在仓库根执行 <code>uv run --extra web python -m review_tool serve</code> 后刷新页面。
          </div>
        )}
        <Page toast={toast} health={h} />
      </main>

      <div className={`toast ${toastMsg ? 'show' : ''}`} role="status" aria-live="polite">
        {toastMsg}
      </div>
    </div>
  )
}
