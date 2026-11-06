import { useState } from 'react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Markdown } from '../lib/markdown'
import { Card, ErrorBox, Loading, Stat } from '../components/Common'

const TABS = [
  { id: 'week', label: '周报' },
  { id: 'month', label: '月报' },
  { id: 'ctx', label: '昨日上下文' },
]

const fmtMonth = (m) => `${String(m).slice(0, 4)}-${String(m).slice(4)}`

function Summary({ s }) {
  if (!s) return null
  const dims = Object.entries(s.dims || {})
  return (
    <section className="stats" aria-label="报告摘要">
      <Stat label="系统分均值" value={s.system_avg ?? '—'} sub={`${s.days} 天记录 · 完整度 ${s.completeness?.rate_pct ?? '—'}%`} />
      {dims.map(([k, v]) => (
        <Stat key={k} label={k} value={v ?? '—'} tone={s.worst_dim?.name === k ? 'amber' : undefined}
          sub={s.worst_dim?.name === k ? '本期最弱维' : undefined} />
      ))}
    </section>
  )
}

function WeekView() {
  const weeks = useAsync((signal) => api.weeks({ signal }), [])
  const [sel, setSel] = useState(null)
  const cur = sel || weeks.data?.[0]
  const rep = useAsync(
    (signal) => (cur ? api.week(cur.year, cur.week, { signal }) : Promise.resolve(null)),
    [cur?.year, cur?.week],
  )
  if (weeks.error) return <ErrorBox error={weeks.error} onRetry={weeks.reload} />
  if (!weeks.data) return <Loading />
  return (
    <>
      <div className="toolbar">
        <label>
          选择周
          <select value={cur ? `${cur.year}-${cur.week}` : ''}
            onChange={(e) => setSel(weeks.data.find((w) => `${w.year}-${w.week}` === e.target.value))}>
            {weeks.data.map((w) => (
              <option key={`${w.year}-${w.week}`} value={`${w.year}-${w.week}`}>
                {w.year} 第 {w.week} 周
              </option>
            ))}
          </select>
        </label>
        {cur && (
          <a className="btn-ghost" href={api.weekMdUrl(cur.year, cur.week)} download>
            下载 .md
          </a>
        )}
      </div>
      <ReportBody rep={rep} />
    </>
  )
}

function MonthView() {
  const months = useAsync((signal) => api.months({ signal }), [])
  const [sel, setSel] = useState(null)
  const cur = sel || months.data?.[0]
  const rep = useAsync((signal) => (cur ? api.month(cur, { signal }) : Promise.resolve(null)), [cur])
  if (months.error) return <ErrorBox error={months.error} onRetry={months.reload} />
  if (!months.data) return <Loading />
  return (
    <>
      <div className="toolbar">
        <label>
          选择月
          <select value={cur || ''} onChange={(e) => setSel(Number(e.target.value))}>
            {months.data.map((m) => (
              <option key={m} value={m}>{fmtMonth(m)}</option>
            ))}
          </select>
        </label>
        {cur && (
          <a className="btn-ghost" href={api.monthMdUrl(cur)} download>
            下载 .md
          </a>
        )}
      </div>
      <ReportBody rep={rep} />
    </>
  )
}

function ReportBody({ rep }) {
  if (rep.error) return <ErrorBox error={rep.error} onRetry={rep.reload} />
  if (rep.loading && !rep.data) return <Loading label="正在生成报告…" />
  if (!rep.data) return null
  return (
    <div aria-busy={rep.loading}>
      <Summary s={rep.data.summary} />
      <Card title="报告全文" meta={rep.data.filename}>
        <Markdown source={rep.data.markdown} />
      </Card>
    </div>
  )
}

function CtxView() {
  const ctx = useAsync((signal) => api.aiContext(undefined, { signal }), [])
  if (ctx.error) return <ErrorBox error={ctx.error} onRetry={ctx.reload} />
  if (!ctx.data) return <Loading />
  return (
    <Card title={`复盘上下文 · ${ctx.data.date}`} meta="复盘前先读：当日事实 / 近 7 日 / 规则关注点">
      <Markdown source={ctx.data.markdown} />
    </Card>
  )
}

export default function Reports() {
  const [tab, setTab] = useState('week')
  return (
    <>
      <header className="topbar">
        <div>
          <h1>复盘与报告</h1>
          <p className="subtitle">与 CLI `week` / `month` / `ai-context` 同源，只读</p>
        </div>
      </header>
      <div className="tabs" role="tablist" aria-label="报告类型">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'week' && <WeekView />}
        {tab === 'month' && <MonthView />}
        {tab === 'ctx' && <CtxView />}
      </div>
    </>
  )
}
