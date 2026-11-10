import { useMemo, useState } from 'react'
import { api, errText, todayStr } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { WD, weekDays } from '../lib/todos'
import { Card, Empty, ErrorBox, Loading, Stat } from '../components/Common'
import { WriteFlow } from '../components/WriteFlow'
import { ReviewSteps } from '../components/ReviewSteps'
import { NewTask, Task, TodoGroups } from '../components/today/Todos'
import { PullPreview } from '../components/today/PullPreview'
import { SystemCard } from '../components/today/SystemCard'

const LIGHT = {
  green: { text: '绿灯', tone: 'green', hint: '可以收工' },
  yellow: { text: '黄灯', tone: 'amber', hint: '还差一点' },
  red: { text: '红灯', tone: 'red', hint: '未完成' },
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

      <div className="list-toolbar" role="search">
        <label className="search">
          <span aria-hidden="true">⌕</span>
          <span className="visually-hidden">搜索今日任务</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索今日任务" />
        </label>
        <button type="button" className="btn-ghost" onClick={refresh} disabled={refreshing} aria-busy={refreshing}>
          {refreshing ? '刷新中…' : '↻ 刷新今日'}
        </button>
      </div>

      <div className="row">
        <Card title="今日待办" meta="逾期（默认折叠）· 今日到期 · 无截止">
          <div className="well">
            {today.loading && !data ? (
              <Loading label="正在拉取 ClickUp…" />
            ) : today.error && !data ? (
              <ErrorBox error={today.error} onRetry={today.reload} />
            ) : todoCount === 0 ? (
              <Empty
                action={query ? (
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setQuery('')}>
                    清除搜索
                  </button>
                ) : null}
              >
                {query ? '没有匹配的任务' : '今天没有待办，轻松一点'}
              </Empty>
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
              <Empty
                action={query ? (
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setQuery('')}>
                    清除搜索
                  </button>
                ) : (
                  <button type="button" className="btn-ghost btn-sm" onClick={refresh} disabled={refreshing}>
                    刷新今日
                  </button>
                )}
              >
                {query ? '没有匹配的任务' : '还没有完成的任务'}
              </Empty>
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
            <Empty
              action={
                <button type="button" className="btn-ghost btn-sm" onClick={today.reload}>
                  重试拉取
                </button>
              }
            >
              ClickUp 数据不可用，暂无负荷统计
            </Empty>
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
