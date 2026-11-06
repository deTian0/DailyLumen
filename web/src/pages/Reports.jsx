import { useState } from 'react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Markdown } from '../lib/markdown'
import { Card, CopyButton, Empty, ErrorBox, Loading, Stat } from '../components/Common'

const TABS = [
  { id: 'week', label: '周报' },
  { id: 'month', label: '月报' },
  { id: 'ctx', label: '昨日上下文' },
]

const DIM_NAME = { health: '健康', work: '工作', learn: '学习', life: '生活' }
const fmtMonth = (m) => `${String(m).slice(0, 4)}-${String(m).slice(4)}`

function Summary({ s }) {
  if (!s) return null
  const dims = Object.entries(s.dims || {})
  return (
    <section className="stats" aria-label="报告摘要">
      <Stat label="系统分均值" value={s.system_avg ?? '—'}
        sub={`${s.days ?? '—'} 天记录 · 完整度 ${s.completeness?.rate_pct ?? '—'}%`} />
      {dims.map(([k, v]) => (
        <Stat key={k} label={DIM_NAME[k] || k} value={v ?? '—'}
          tone={s.worst_dim?.name === k ? 'amber' : undefined}
          sub={s.worst_dim?.name === k ? '本期最弱维' : undefined} />
      ))}
    </section>
  )
}

// 上一期 / 下一期 + 下拉：列表按新→旧排列，index 0 为最新
function Picker({ label, items, index, onPick, fmt }) {
  return (
    <div className="picker" role="group" aria-label={label}>
      <button type="button" className="btn-ghost" disabled={index >= items.length - 1}
        onClick={() => onPick(index + 1)} aria-label={`上一${label.slice(-1)}`}>‹</button>
      <label>
        <span className="visually-hidden">{label}</span>
        <select value={index} onChange={(e) => onPick(Number(e.target.value))}>
          {items.map((it, i) => <option key={i} value={i}>{fmt(it)}</option>)}
        </select>
      </label>
      <button type="button" className="btn-ghost" disabled={index <= 0}
        onClick={() => onPick(index - 1)} aria-label={`下一${label.slice(-1)}`}>›</button>
    </div>
  )
}

function ReportBody({ rep, toast, mdUrl }) {
  if (rep.error && !rep.data) return <ErrorBox error={rep.error} onRetry={rep.reload} />
  if (rep.loading && !rep.data) return <Loading label="正在生成报告…" />
  if (!rep.data) return null
  return (
    <div aria-busy={rep.loading}>
      {rep.error && (
        <div className="banner banner-warn" role="alert">切换失败，仍显示上一份报告。</div>
      )}
      <Summary s={rep.data.summary} />
      <Card title="报告全文" meta={rep.data.filename}
        actions={
          <div className="card-actions">
            <CopyButton text={rep.data.markdown} toast={toast} />
            <a className="btn-ghost" href={mdUrl} download={rep.data.filename}>下载 .md</a>
          </div>
        }>
        <Markdown source={rep.data.markdown} />
      </Card>
    </div>
  )
}

function WeekView({ toast }) {
  const weeks = useAsync((signal) => api.weeks({ signal }), [])
  const [idx, setIdx] = useState(0)
  const cur = weeks.data?.[idx]
  const rep = useAsync(
    (signal) => (cur ? api.week(cur.year, cur.week, { signal }) : Promise.resolve(null)),
    [cur?.year, cur?.week],
  )
  if (weeks.error) return <ErrorBox error={weeks.error} onRetry={weeks.reload} />
  if (!weeks.data) return <Loading />
  if (!weeks.data.length) return <Empty>库里还没有任何周的数据</Empty>
  return (
    <>
      <div className="toolbar">
        <Picker label="选择周" items={weeks.data} index={idx} onPick={setIdx}
          fmt={(w) => `${w.year} 第 ${w.week} 周`} />
      </div>
      <ReportBody rep={rep} toast={toast} mdUrl={api.weekMdUrl(cur.year, cur.week)} />
    </>
  )
}

function MonthView({ toast }) {
  const months = useAsync((signal) => api.months({ signal }), [])
  const [idx, setIdx] = useState(0)
  const cur = months.data?.[idx]
  const rep = useAsync((signal) => (cur ? api.month(cur, { signal }) : Promise.resolve(null)), [cur])
  if (months.error) return <ErrorBox error={months.error} onRetry={months.reload} />
  if (!months.data) return <Loading />
  if (!months.data.length) return <Empty>库里还没有任何月的数据</Empty>
  return (
    <>
      <div className="toolbar">
        <Picker label="选择月" items={months.data} index={idx} onPick={setIdx} fmt={fmtMonth} />
      </div>
      <ReportBody rep={rep} toast={toast} mdUrl={api.monthMdUrl(cur)} />
    </>
  )
}

function CtxView({ toast }) {
  const ctx = useAsync((signal) => api.aiContext(undefined, { signal }), [])
  if (ctx.error) return <ErrorBox error={ctx.error} onRetry={ctx.reload} />
  if (!ctx.data) return <Loading />
  return (
    <Card title={`复盘上下文 · ${ctx.data.date}`} meta="当日事实 / 近 7 日 / 规则关注点"
      actions={<CopyButton text={ctx.data.markdown} toast={toast} />}>
      <Markdown source={ctx.data.markdown} />
    </Card>
  )
}

export default function Reports({ toast }) {
  const [tab, setTab] = useState('week')
  // tablist 键盘：左右方向键切换（WAI-ARIA Tabs 模式）
  function onKey(e) {
    const i = TABS.findIndex((t) => t.id === tab)
    let n = null
    if (e.key === 'ArrowRight') n = (i + 1) % TABS.length
    if (e.key === 'ArrowLeft') n = (i - 1 + TABS.length) % TABS.length
    if (e.key === 'Home') n = 0
    if (e.key === 'End') n = TABS.length - 1
    if (n === null) return
    e.preventDefault()
    setTab(TABS[n].id)
    document.getElementById(`tab-${TABS[n].id}`)?.focus()
  }
  return (
    <>
      <header className="topbar">
        <div>
          <h1>复盘与报告</h1>
          <p className="subtitle">与 CLI week / month / ai-context 同源，数字现算，只读</p>
        </div>
      </header>
      <div className="tabs" role="tablist" aria-label="报告类型" onKeyDown={onKey}>
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id}
            tabIndex={tab === t.id ? 0 : -1} aria-controls={`panel-${t.id}`}
            className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'week' && <WeekView toast={toast} />}
        {tab === 'month' && <MonthView toast={toast} />}
        {tab === 'ctx' && <CtxView toast={toast} />}
      </div>
    </>
  )
}
