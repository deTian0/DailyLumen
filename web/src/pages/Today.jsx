import { useMemo, useState } from 'react'
import { api, errText, todayStr } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Card, CopyButton, Empty, ErrorBox, Loading, Stat } from '../components/Common'
import { WriteFlow } from '../components/WriteFlow'
import { ReviewSteps } from '../components/ReviewSteps'

const LIGHT = {
  green: { text: '绿灯', tone: 'green', hint: '可以收工' },
  yellow: { text: '黄灯', tone: 'amber', hint: '还差一点' },
  red: { text: '红灯', tone: 'red', hint: '未完成' },
}
const WD = ['一', '二', '三', '四', '五', '六', '日']

function weekDays(day) {
  const d = new Date(`${day}T00:00:00`)
  const idx = (d.getDay() + 6) % 7
  const mon = new Date(d)
  mon.setDate(d.getDate() - idx)
  return Array.from({ length: 7 }, (_, i) => {
    const x = new Date(mon)
    x.setDate(mon.getDate() + i)
    return todayStr(x)
  })
}

// W10 / FR-J1：任务内联「完成」——预览（一次性 token + 等价 CLI）→ 确认 → 以回读结果为准
function TaskDone({ t, writable, toast, onChanged }) {
  const [plan, setPlan] = useState(null)
  const [state, setState] = useState('idle') // idle | planning | writing | done | error
  const [err, setErr] = useState(null)
  if (!writable) return null
  async function preview() {
    setState('planning')
    setErr(null)
    try {
      setPlan(await api.writePlanBody('task-status', { task_id: t.id, status: 'complete', name: t.name }))
      setState('idle')
    } catch (e) {
      setErr(e)
      setState('error')
    }
  }
  async function confirm() {
    setState('writing') // 乐观：先置灰「写入中」，最终以回读为准
    try {
      await api.writeConfirm(plan.token)
      setState('done')
      setPlan(null)
      toast?.(`已完成「${t.name}」（ClickUp 回读通过）`)
      onChanged?.()
    } catch (e) {
      setErr(e)
      setPlan(null)
      setState('error')
    }
  }
  if (state === 'done') return <span className="pill pill-green">✓ 已完成</span>
  if (plan) {
    return (
      <span className="task-confirm" role="group" aria-label={`确认完成 ${t.name}`}>
        <code title={plan.cli}>{plan.cli.replace('python -m review_tool ', '')}</code>
        <button type="button" className="btn-primary btn-sm" onClick={confirm} disabled={state === 'writing'}>
          {state === 'writing' ? '写入中…' : '确认完成'}
        </button>
        <button type="button" className="btn-ghost btn-sm" onClick={() => setPlan(null)} disabled={state === 'writing'}>取消</button>
      </span>
    )
  }
  return (
    <>
      {state === 'error' && <span className="pill pill-red" role="alert" title={errText(err)}>失败</span>}
      <button type="button" className="btn-ghost btn-sm" onClick={preview} disabled={state === 'planning'}
        aria-label={`${state === 'error' ? '重试' : '标记完成'}：${t.name}`}>
        {state === 'planning' ? '…' : state === 'error' ? '重试' : '✓ 完成'}
      </button>
    </>
  )
}

// 新建任务：输入即预览（Enter）→ 确认；默认落「日常事务」list
function NewTask({ writable, toast, onChanged }) {
  const [name, setName] = useState('')
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  if (!writable) {
    return <p className="hint">看板以只读启动：新建 / 完成任务需 <code>serve --enable-write</code>。</p>
  }
  async function preview(e) {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setErr(null)
    try {
      setPlan(await api.writePlanBody('task-create', { name: name.trim() }))
    } catch (x) {
      setErr(x)
    } finally {
      setBusy(false)
    }
  }
  async function confirm() {
    setBusy(true)
    try {
      await api.writeConfirm(plan.token)
      toast?.(`已新建「${plan.preview.name}」（ClickUp 回读通过）`)
      setPlan(null)
      setName('')
      onChanged?.()
    } catch (x) {
      setErr(x)
      setPlan(null)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="new-task">
      <form onSubmit={preview} className="new-task-row">
        <label className="visually-hidden" htmlFor="new-task-name">新建任务名</label>
        <input id="new-task-name" value={name} maxLength={200} disabled={busy || !!plan}
          onChange={(e) => setName(e.target.value)} placeholder="＋ 新建任务，回车预览" />
        {!plan && <button type="submit" className="btn-ghost btn-sm" disabled={busy || !name.trim()}>预览</button>}
      </form>
      {plan && (
        <div className="task-confirm" role="group" aria-label="确认新建任务">
          <span>{plan.preview.list} ←「{plan.preview.name}」</span>
          <code>{plan.cli.replace('python -m review_tool ', '')}</code>
          <button type="button" className="btn-primary btn-sm" onClick={confirm} disabled={busy}>
            {busy ? '写入中…' : '确认新建'}
          </button>
          <button type="button" className="btn-ghost btn-sm" onClick={() => setPlan(null)} disabled={busy}>取消</button>
        </div>
      )}
      {err && <ErrorBox error={err} />}
    </div>
  )
}

function Task({ t, kind, writable, toast, onChanged, selectable, selected, onSelect }) {
  const pill =
    kind === 'overdue'
      ? { text: `逾期 ${t.due?.slice(5) || ''}`, cls: 'pill-red' }
      : kind === 'in_progress'
        ? { text: '进行中', cls: 'pill-blue' }
        : kind === 'done'
          ? { text: t.rebated_to ? `回拨→${t.rebated_to.slice(5)}` : t.closed_clock || '完成', cls: 'pill-green' }
          : { text: t.due ? `due ${t.due.slice(5)}` : '无截止', cls: '' }
  return (
    <li className={`task task-${kind}`}>
      {selectable ? (
        <input type="checkbox" className="task-sel" checked={selected} onChange={onSelect}
          aria-label={`加入批量完成：${t.name}`} />
      ) : <span className="dot" aria-hidden="true" />}
      <div className="task-body">
        <div className="title">{t.name}</div>
        <div className="sub">{t.list}</div>
      </div>
      <span className={`pill ${pill.cls}`}>{pill.text}</span>
      {kind !== 'done' && <TaskDone t={t} writable={writable} toast={toast} onChanged={onChanged} />}
    </li>
  )
}

// W12：今日待办分组（逾期 / 今日到期·进行中 / 无截止）；分组只按 ClickUp 已给的 kind + due 字段，
// 不在前端另做归日（归日口径单源在后端 clickup_queries）。逾期默认折叠并显示条数。
function groupTodos(lists) {
  return [
    { id: 'overdue', label: '逾期', items: lists.overdue.map((t) => [t, 'overdue']), open: false },
    {
      id: 'due', label: '今日到期 · 进行中',
      items: [...lists.in_progress.map((t) => [t, 'in_progress']),
        ...lists.open.filter((t) => t.due).map((t) => [t, 'open'])],
      open: true,
    },
    { id: 'nodue', label: '无截止', items: lists.open.filter((t) => !t.due).map((t) => [t, 'open']), open: true },
  ].filter((g) => g.items.length)
}

// 批量完成：一次预览 + 一次性 token 对应一批（≤20 条），回显逐条等价 CLI；结果逐条以回读为准
function BatchBar({ selected, clear, toast, onChanged }) {
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [res, setRes] = useState(null)
  if (!selected.length && !plan && !res) return null
  async function preview() {
    setBusy(true)
    setErr(null)
    setRes(null)
    try {
      setPlan(await api.writePlanBody('task-batch', {
        items: selected.map((t) => ({ task_id: t.id, name: t.name })), status: 'complete',
      }))
    } catch (e) {
      setErr(e)
    } finally {
      setBusy(false)
    }
  }
  async function confirm() {
    setBusy(true)
    try {
      const r = await api.writeConfirm(plan.token)
      setPlan(null)
      setRes(r.result)
      toast?.(`批量完成 ${r.result.written} 条${r.result.failed.length ? `，${r.result.failed.length} 条失败` : ''}（以回读为准）`)
      clear()
      onChanged?.()
    } catch (e) {
      setErr(e)
      setPlan(null)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="batch-bar" role="region" aria-label="批量完成">
      {!plan ? (
        <div className="batch-row">
          <span>已选 {selected.length} 条</span>
          <button type="button" className="btn-ghost btn-sm" onClick={preview} disabled={busy || !selected.length}
            aria-label={`预览：批量完成 ${selected.length} 条任务`}>
            {busy ? '预览中…' : '① 预览批量完成'}
          </button>
          <button type="button" className="btn-ghost btn-sm" onClick={clear} disabled={busy}
            aria-label="清空批量选择">清空</button>
        </div>
      ) : (
        <>
          <p className="muted">将把 {plan.preview.count} 条任务改为 <code>{plan.preview.status}</code>（逐条写后回读）：</p>
          <ul className="batch-list">
            {plan.preview.items.map((x, i) => (
              <li key={x.task_id}><span>{x.name || x.task_id}</span> <code className="cli">{plan.preview.clis[i]}</code></li>
            ))}
          </ul>
          <div className="batch-row">
            <button type="button" className="btn-primary btn-sm" onClick={confirm} disabled={busy}
              aria-label={`确认：批量完成 ${plan.preview.count} 条任务`}>
              {busy ? '写入中…' : `② 确认完成 ${plan.preview.count} 条`}
            </button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => setPlan(null)} disabled={busy}
              aria-label="取消：批量完成">取消</button>
            <CopyButton text={plan.cli} toast={toast} label="复制 CLI" aria="复制 CLI：批量完成" />
          </div>
        </>
      )}
      {res?.failed?.length > 0 && (
        <div className="hint hint-warn" role="alert">
          {res.failed.length} 条未完成（可重新勾选重试）：
          <ul>{res.failed.map((f) => <li key={f.task_id}>{f.name || f.task_id}：{f.error}</li>)}</ul>
        </div>
      )}
      {err && <ErrorBox error={err} onRetry={selected.length ? preview : undefined} />}
    </div>
  )
}

function TodoGroups({ lists, writable, toast, onChanged, query }) {
  const [sel, setSel] = useState({}) // id -> task
  const groups = groupTodos(lists)
  const toggle = (t) => setSel((s) => {
    const n = { ...s }
    if (n[t.id]) delete n[t.id]
    else if (Object.keys(n).length < 20) n[t.id] = t
    return n
  })
  const selected = Object.values(sel)
  return (
    <>
      {groups.map((g) => (
        // 搜索时全部展开，避免命中项藏在折叠组里
        <details key={g.id} className={`task-group tg-${g.id}`} open={g.open || !!query}>
          <summary>
            <span className="tg-name">{g.label}</span>
            <span className={`pill ${g.id === 'overdue' ? 'pill-red' : ''}`}>{g.items.length}</span>
          </summary>
          <ul className="task-list" aria-label={`${g.label}任务`}>
            {g.items.map(([t, k]) => (
              <Task key={t.id} t={t} kind={k} writable={writable} toast={toast} onChanged={onChanged}
                selectable={writable} selected={!!sel[t.id]} onSelect={() => toggle(t)} />
            ))}
          </ul>
        </details>
      ))}
      {writable && <BatchBar selected={selected} clear={() => setSel({})} toast={toast} onChanged={onChanged} />}
    </>
  )
}

// W12：快照预览 —— 明确列出将被整天替换的日期（库内现值 → 新值），以及本周节奏替换后的样子。
// 投影数字由后端 plan_clickup_pull 给出（before/after），前端不另算归日。
function PullPreview(p) {
  return (
    <>
      <p className="muted">
        拉取 {p.fetched} 条 · 已完成 {p.closed} 条 → 写入 <code>{p.target_table}</code>（{p.strategy}）
      </p>
      {p.per_day.length ? (
        <>
          <p className="muted"><strong>将被替换的 {p.per_day.length} 天</strong>（现有 → 替换后）：</p>
          <ul className="chips" aria-label="将被替换的日期">
            {p.per_day.map((x) => (
              <li key={x.date}>{x.date.slice(5)} · {x.before} → <strong>{x.count}</strong></li>
            ))}
          </ul>
        </>
      ) : <p className="muted">窗口内没有已完成任务，无需写入。</p>}
      {p.week?.length > 0 && (
        <>
          <p className="muted"><strong>本周节奏将变为</strong>（未出现在预览中的日期保持不变）：</p>
          <ol className="week week-sm" aria-label="替换后的本周每日完成数">
            {p.week.map((d, i) => (
              <li key={d.date} className={`day ${d.replaced ? 'sel' : ''}`}
                aria-label={`星期${WD[i]} ${d.date}：${d.before} → ${d.after}${d.replaced ? '（替换）' : '（不变）'}`}>
                <span className="wd">{WD[i]}</span>
                <span className="num">{d.after}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </>
  )
}

const INTEG = [
  { id: 'clickup', label: 'ClickUp' },
  { id: 'keepstrong', label: '练练健身' },
  { id: 'deepseek', label: 'DeepSeek' },
]
const MODE = { workbuddy: 'WorkBuddy 宿主', deepseek: 'DeepSeek 直连' }

// 系统状态：只展示 /api/health 的白名单字段（mode / 三集成开关），不推导任何业务结论
function SystemCard({ health }) {
  return (
    <Card title="系统状态" meta="来自 /api/health">
      {!health ? (
        <Loading />
      ) : (
        <dl className="kv">
          <div>
            <dt>复盘模式</dt>
            <dd>{MODE[health.llm_mode] || health.llm_mode}</dd>
          </div>
          {INTEG.map((i) => (
            <div key={i.id}>
              <dt>{i.label}</dt>
              <dd>
                <span className={`pill ${health.integrations?.[i.id] ? 'pill-green' : ''}`}>
                  {health.integrations?.[i.id] ? '已启用' : '未启用'}
                </span>
              </dd>
            </div>
          ))}
          <div>
            <dt>AI 一键功能</dt>
            <dd>{health.ai_enabled ? '可用' : '不可用（需 deepseek 模式且集成开启）'}</dd>
          </div>
        </dl>
      )}
    </Card>
  )
}

export default function Today({ toast, health }) {
  const day = todayStr()
  const [refreshing, setRefreshing] = useState(false)
  const [override, setOverride] = useState(null)
  const [query, setQuery] = useState('')
  const today = useAsync((signal) => api.today(undefined, { signal }), [])
  const doctor = useAsync((signal) => api.doctor({ signal }), [])
  const days = useMemo(() => weekDays(day), [day])
  const weekDone = useAsync((signal) => api.done(days[0], days[6], { signal }), [days])

  const data = override || today.data
  const writable = health && health.readonly === false

  // 写后以 ClickUp 实时回读为准：静默刷新今日列表（失败不打断，已有 toast）
  async function afterWrite() {
    try {
      setOverride(await api.refreshToday())
    } catch {
      /* 刷新失败保留当前列表；用户可点「刷新今日」 */
    }
  }

  async function refresh() {
    setRefreshing(true)
    try {
      const d = await api.refreshToday()
      setOverride(d)
      toast(d.stale ? `刷新失败，显示上次结果：${d.stale_reason}` : `已刷新 · ${d.fetched_at.slice(11, 16)}`)
    } catch (e) {
      toast(`刷新失败：${errText(e)}`)
    } finally {
      setRefreshing(false)
    }
  }

  const lists = useMemo(() => {
    if (!data) return null
    const q = query.trim().toLowerCase()
    const pick = (k) =>
      data.groups.flatMap((g) => g[k]).filter((t) => !q || t.name.toLowerCase().includes(q))
    return { overdue: pick('overdue'), in_progress: pick('in_progress'), open: pick('open'), done: pick('done') }
  }, [data, query])

  const ready = doctor.data?.result?.day_ready
  const light = ready ? LIGHT[ready.light] : null
  const todoCount = lists ? lists.overdue.length + lists.in_progress.length + lists.open.length : null

  return (
    <>
      <header className="topbar">
        <div>
          <h1>今日看板</h1>
          <p className="subtitle">
            {day} · 星期{WD[(new Date().getDay() + 6) % 7]}
            {data && <> · ClickUp 拉取于 {data.fetched_at.slice(11, 16)}</>}
          </p>
        </div>
        <div className="top-actions">
          <label className="search">
            <span aria-hidden="true">⌕</span>
            <span className="visually-hidden">搜索今日任务</span>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索今日任务" />
          </label>
          <button type="button" className="btn-primary" onClick={refresh} disabled={refreshing} aria-busy={refreshing}>
            {refreshing ? '刷新中…' : '↻ 刷新今日'}
          </button>
        </div>
      </header>

      {data?.stale && (
        <div className="banner banner-warn" role="status">
          ClickUp 刷新失败（{data.stale_reason}），当前显示上次成功的结果。
        </div>
      )}

      <section className="stats" aria-label="今日摘要">
        <Stat
          label="今天要做"
          value={lists ? lists.in_progress.length + lists.open.length : '—'}
          sub={lists ? `进行中 ${lists.in_progress.length} · 另有逾期 ${lists.overdue.length}` : '加载中'}
          tone={undefined}
        />
        <Stat
          label="今日已办"
          value={lists ? lists.done.length : '—'}
          sub={data ? `含回拨 ${data.totals.rebated}` : '加载中'}
          tone="green"
        />
        <Stat
          label={`昨日收工灯${ready ? ` · ${ready.day.slice(5)}` : ''}`}
          value={light ? light.text : doctor.error ? '—' : '…'}
          sub={ready ? (ready.reasons.length ? ready.reasons[0] : light.hint) : doctor.error ? errText(doctor.error) : ''}
          tone={light?.tone}
        />
        <Stat
          label="跨日未完成"
          value={data ? data.totals.cross_day : '—'}
          sub="非今日到期的开放任务"
        />
      </section>

      {ready && ready.light !== 'green' && (
        <section className="card review-strip" aria-label="昨日复盘进度">
          <div className="card-h">
            <h2>昨日复盘还差几步</h2>
            <a className="btn-ghost btn-sm" href="#/reports?tab=ctx">去复盘 →</a>
          </div>
          <ReviewSteps ready={ready} />
        </section>
      )}

      <div className="row">
        <Card title="今日待办" meta="逾期（默认折叠）· 今日到期 · 无截止">
          <div className="well">
            {today.loading && !data ? (
              <Loading label="正在拉取 ClickUp…" />
            ) : today.error && !data ? (
              <ErrorBox error={today.error} onRetry={today.reload} />
            ) : todoCount === 0 ? (
              <Empty>{query ? '没有匹配的任务' : '今天没有待办，轻松一点'}</Empty>
            ) : (
              <TodoGroups lists={lists} writable={writable} toast={toast} onChanged={afterWrite}
                query={query} />
            )}
          </div>
          <NewTask writable={writable} toast={toast} onChanged={afterWrite} />
        </Card>

        <Card title="今日已办" meta="date_closed 归日 · 含次日早上回拨">
          <div className="well">
            {today.loading && !data ? (
              <Loading />
            ) : today.error && !data ? (
              <ErrorBox error={today.error} onRetry={today.reload} />
            ) : lists.done.length === 0 ? (
              <Empty>{query ? '没有匹配的任务' : '还没有完成的任务'}</Empty>
            ) : (
              <ul className="task-list" aria-label="已办任务">
                {lists.done.map((t) => <Task key={t.id} t={t} kind="done" />)}
              </ul>
            )}
          </div>
        </Card>
      </div>

      <div className="row">
        <Card title="本周节奏" meta="每日完成数（本地快照）">
          {weekDone.error ? (
            <ErrorBox error={weekDone.error} onRetry={weekDone.reload} />
          ) : (
            <ol className="week" aria-label="本周每日完成数">
              {days.map((d, i) => {
                const rec = weekDone.data?.days.find((x) => x.date === d)
                const n = rec?.count ?? 0
                const isToday = d === day
                return (
                  <li key={d} className={`day ${isToday ? 'sel' : ''} ${d > day ? 'future' : ''}`}
                    aria-label={`星期${WD[i]} ${d}，完成 ${n} 项${isToday ? '（今天）' : ''}`}>
                    <span className="wd">{WD[i]}</span>
                    <span className="num">{d > day ? '·' : n}</span>
                  </li>
                )
              })}
            </ol>
          )}
          {weekDone.data && weekDone.data.total === 0 ? (
            <>
              <p className="hint hint-warn">
                本周还没有已入库的 ClickUp 完成快照，所以每天都显示 0（不代表没做事）。
                拉取一次快照后这里才有数字；今日待办 / 已办以上方实时数据为准。
              </p>
              <WriteFlow action="clickup-pull" body={{ days: 14 }} health={health} toast={toast}
                title="拉取完成快照（clickup-pull）"
                name="拉取完成快照"
                desc="拉近 14 天已完成任务，按天预览条数；确认后整天替换 clickup_done（写库前自动备份，写后回读）。"
                confirmLabel="确认写入快照"
                canConfirm={(p) => p.closed > 0}
                onDone={() => weekDone.reload()}
                renderPreview={PullPreview} />
            </>
          ) : (
            <p className="hint">本周合计完成 {weekDone.data?.total ?? '—'} 项（来自已入库的 ClickUp 完成快照，今日数据以上方实时为准）。</p>
          )}
        </Card>

        <Card title="今日负荷" meta="按清单：已办 / 待办">
          {data ? (
            <div className="bars">
              {data.groups.map((g) => {
                const done = g.done.length
                const todo = g.open.length + g.in_progress.length + g.overdue.length
                const total = done + todo
                const pct = total ? Math.round((done / total) * 100) : 0
                return (
                  <div className="bar-row" key={g.id}>
                    <span className="name">{g.name}</span>
                    <div className="track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
                      aria-label={`${g.name} 完成 ${done}/${total}`}>
                      <div className="fill" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="bar-n">{done}/{total}</span>
                  </div>
                )
              })}
            </div>
          ) : today.error ? (
            <Empty>ClickUp 数据不可用，暂无负荷统计</Empty>
          ) : (
            <Loading />
          )}
          {data?.bulk_hint && <p className="hint">{data.bulk_hint}</p>}
        </Card>
      </div>

      <div className="row row-full">
        <SystemCard health={health} />
      </div>
    </>
  )
}
