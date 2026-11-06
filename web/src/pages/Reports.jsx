import { useState } from 'react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Markdown } from '../lib/markdown'
import { Card, CopyButton, Empty, ErrorBox, Loading, Stat } from '../components/Common'
import { WriteFlow } from '../components/WriteFlow'
import { VisionDay } from '../components/VisionDay'

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

// AI 评价预览（W8）：只预览不落盘；mode≠deepseek 时按钮禁用并说明原因
function AiPreview({ date, toast }) {
  const st = useAsync((signal) => api.aiStatus({ signal }), [])
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  async function run() {
    setBusy(true)
    setErr(null)
    try {
      setRes(await api.aiReviewPreview(date))
    } catch (e) {
      setErr(e)
    } finally {
      setBusy(false)
    }
  }
  const allowed = st.data?.allowed
  return (
    <Card title="AI 评价预览" meta={st.data ? `mode=${st.data.mode}` : ''}
      actions={
        <button type="button" className="btn-primary" onClick={run} disabled={!allowed || busy}
          aria-describedby="ai-gate-note">
          {busy ? '生成中…' : '生成预览'}
        </button>
      }>
      <p id="ai-gate-note" className="hint">
        {st.data && !allowed
          ? st.data.reason
          : '调用 DeepSeek 生成「七、AI 评价与建议」草稿，仅预览，不写 md、不写库；确认后用下方 CLI 落盘。'}
      </p>
      {err && <ErrorBox error={err} onRetry={allowed ? run : undefined} />}
      {res && (
        <div aria-live="polite">
          <Markdown source={res.section} />
          <div className="card-actions">
            <CopyButton text={res.section} toast={toast} />
            <CopyButton text={res.cli} toast={toast} label="复制落盘命令" />
          </div>
          {res.diff_text && (
            <details>
              <summary>与 md 现有「七、AI」的差异</summary>
              <pre className="plain">{res.diff_text}</pre>
            </details>
          )}
        </div>
      )}
    </Card>
  )
}

const FIELD_NAME = {
  health_score: '健康', work_score: '工作', learn_score: '学习', life_score: '生活',
  diet_kcal: '热量 kcal', sleep_h: '睡眠 h', exercise_min: '运动 min',
}

function IngestPreview(p) {
  return (
    <>
      <p className="muted">
        {p.rel} · 日期 {p.date}
        {p.pending && (p.allow_ai_draft ? ' · 含待人审标记（已勾选强制入库）' : ' · 含待人审标记，ingest 会跳过：请先定稿')}
      </p>
      <dl className="kv">
        {Object.entries(p.fields || {}).map(([k, v]) => (
          <div key={k}><dt>{FIELD_NAME[k] || k}</dt><dd>{v ?? '—'}</dd></div>
        ))}
      </dl>
    </>
  )
}

function CtxView({ toast, health }) {
  const ctx = useAsync((signal) => api.aiContext(undefined, { signal }), [])
  const ai = useAsync((signal) => api.aiStatus({ signal }), [])
  const [ingestKick, setIngestKick] = useState(0)
  const [allowDraft, setAllowDraft] = useState(false)
  if (ctx.error) return <ErrorBox error={ctx.error} onRetry={ctx.reload} />
  if (!ctx.data) return <Loading />
  return (
    <>
      <Card title={`复盘上下文 · ${ctx.data.date}`} meta="当日事实 / 近 7 日 / 规则关注点"
        actions={<CopyButton text={ctx.data.markdown} toast={toast} />}>
        <Markdown source={ctx.data.markdown} />
      </Card>
      <AiPreview date={ctx.data.date} toast={toast} />
      <Card title="读图写入数据块" meta="截图 → 预览字段 → 写 md（不写库）→ 定稿 → 入库">
        <VisionDay date={ctx.data.date} health={health} toast={toast} ai={ai.data}
          onWritten={() => { ctx.reload(); setIngestKick((k) => k + 1) }} />
      </Card>
      <Card title="写入与定稿" meta="只写复盘 md，不写库；入库另跑 ingest">
        <WriteFlow action="ai-draft" params={{ date: ctx.data.date }} health={health} toast={toast}
          title="写入「七-A AI 草稿」"
          desc="重新生成一次草稿并预览差异；确认后写入 md，带「草稿 / 待人审」标记（ingest 默认跳过）。"
          confirmLabel="确认写入草稿"
          blockedReason={ai.data && !ai.data.allowed ? ai.data.reason : undefined}
          renderPreview={(p) => (
            <>
              <Markdown source={p.section} />
              {p.diff_text && (
                <details>
                  <summary>与 md 现有「七、AI」的差异</summary>
                  <pre className="diff">{p.diff_text}</pre>
                </details>
              )}
            </>
          )} />
        <WriteFlow action="finalize" params={{ date: ctx.data.date }} health={health} toast={toast}
          title="定稿（llm-finalize）"
          desc="把七-A 草稿提升为七-B 定稿并清除待人审标记；写前展示数据块 + 七、AI 并排对比。"
          confirmLabel="确认定稿"
          canConfirm={(p) => p.changed}
          onDone={() => setIngestKick((k) => k + 1)}
          renderPreview={(p) => (
            p.changed
              ? <pre className="diff">{p.side_by_side}</pre>
              : <p className="muted">md 无需改动（可能已定稿或尚无草稿），无需确认；可直接在下方入库。</p>
          )} />
        <WriteFlow action="ingest" body={{ date: ctx.data.date, allow_ai_draft: allowDraft }}
          health={health} toast={toast} autoPreview={ingestKick}
          title="入库（ingest）"
          desc="把该日复盘 md 解析入库（仅限 local/每日复盘/ 内，一次一个文件）；写库前自动备份，写后回读。"
          confirmLabel="确认入库"
          canConfirm={(p) => !p.will_skip}
          renderPreview={IngestPreview} />
        <label className="check">
          <input type="checkbox" checked={allowDraft} onChange={(e) => setAllowDraft(e.target.checked)} />
          允许入库仍含待人审标记的 md（= <code>--allow-ai-draft</code>，一般不建议）
        </label>
      </Card>
    </>
  )
}

export default function Reports({ toast, health }) {
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
        {tab === 'ctx' && <CtxView toast={toast} health={health} />}
      </div>
    </>
  )
}
