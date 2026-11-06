import { useMemo, useState } from 'react'
import { api, errText, todayStr } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Card, Empty, ErrorBox, Loading, Stat } from '../components/Common'

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

function Task({ t, kind }) {
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
      <span className="dot" aria-hidden="true" />
      <div className="task-body">
        <div className="title">{t.name}</div>
        <div className="sub">{t.list}</div>
      </div>
      <span className={`pill ${pill.cls}`}>{pill.text}</span>
    </li>
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

      <div className="row">
        <Card title="今日待办" meta="逾期 → 进行中 → 今日到期">
          <div className="well">
            {today.loading && !data ? (
              <Loading label="正在拉取 ClickUp…" />
            ) : today.error && !data ? (
              <ErrorBox error={today.error} onRetry={today.reload} />
            ) : todoCount === 0 ? (
              <Empty>{query ? '没有匹配的任务' : '今天没有待办，轻松一点'}</Empty>
            ) : (
              <ul className="task-list" aria-label="待办任务">
                {lists.overdue.map((t) => <Task key={t.id} t={t} kind="overdue" />)}
                {lists.in_progress.map((t) => <Task key={t.id} t={t} kind="in_progress" />)}
                {lists.open.map((t) => <Task key={t.id} t={t} kind="open" />)}
              </ul>
            )}
          </div>
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
            <p className="hint hint-warn">
              本地还没有 ClickUp 完成快照，先在命令行跑一次 <code>python -m review_tool clickup-pull</code>。
            </p>
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

      <div className="row">
        <SystemCard health={health} />
      </div>
    </>
  )
}
