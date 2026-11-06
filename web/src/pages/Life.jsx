import { useState } from 'react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Card, ErrorBox, Loading, Stat } from '../components/Common'

// 健康 / 学习 / 督导（W6）：数字全部来自后端 collect（与 CLI 同源），前端只挑字段展示
const TABS = [
  { id: 'morning', label: '晨间简报', load: (s) => api.steward('morning', {}, { signal: s }) },
  { id: 'evening', label: '夜间复盘指引', load: (s) => api.steward('evening', {}, { signal: s }) },
  { id: 'day-help', label: '一日三步', cli: 'day-help', load: (s) => api.life('day-help', {}, { signal: s }) },
  { id: 'week-done', label: '本周做成', cli: 'week-done', load: (s) => api.life('week-done', {}, { signal: s }) },
  { id: 'streaks', label: '连续天数', cli: 'week（streak 段）', load: (s) => api.life('streaks', {}, { signal: s }) },
  { id: 'steward-week', label: '周管家', cli: 'steward --slot week', load: (s) => api.steward('week', {}, { signal: s }) },
  { id: 'body', label: '体征', load: (s) => api.life('body', {}, { signal: s }) },
  { id: 'coach', label: '训练', load: (s) => api.life('coach', {}, { signal: s }) },
  { id: 'nutrition', label: '营养', load: (s) => api.life('nutrition', {}, { signal: s }) },
  { id: 'habits', label: '习惯', load: (s) => api.life('habits', {}, { signal: s }) },
  { id: 'tutor', label: '学习', load: (s) => api.life('tutor', {}, { signal: s }) },
  { id: 'promises', label: '承诺兑现', load: (s) => api.life('promises', {}, { signal: s }) },
  { id: 'correlate', label: '跨维关联', load: (s) => api.life('correlate', {}, { signal: s }) },
]

const n = (v, unit = '') => (v === null || v === undefined ? '—' : `${v}${unit}`)
const pct = (r) => (r === null || r === undefined ? '—' : `${Math.round(r * 100)}%`)

function Highlights({ id, d }) {
  if (!d) return null
  if (id === 'morning') {
    const s = d.scores
    return (
      <section className="stats" aria-label="晨间摘要">
        <Stat label={`昨日系统分${s ? ` · ${s.date.slice(5)}` : ''}`} value={n(s?.system_score)}
          sub={s ? `健康 ${n(s.health_score)} · 工作 ${n(s.work_score)} · 学习 ${n(s.learn_score)} · 生活 ${n(s.life_score)}` : '昨日未入库'} />
        <Stat label="绝对熔断" value={d.fuse?.absolute_count ?? '—'}
          tone={d.fuse?.absolute_count ? 'red' : 'green'}
          sub={d.fuse?.absolute_count ? d.fuse.absolute.map((f) => f.label).join('、') : '无'} />
        <Stat label="今日宏量目标" value={`${n(d.diet_targets?.protein_g, 'g')}`}
          sub={`蛋白 · 碳水 ${n(d.diet_targets?.carbs_g, 'g')} · 脂肪 ${n(d.diet_targets?.fat_g, 'g')}`} />
        <Stat label="训练" value={d.training?.plan_name || '未判断'} sub={d.training?.hint || d.training?.weekday_cn} />
      </section>
    )
  }
  if (id === 'evening') {
    return (
      <Card title={`今晚复盘 ${d.as_of}`} meta={d.day_in_db ? '当日已入库' : '当日尚未入库'}>
        <ol className="steps">
          {(d.steps || []).map((st) => (
            <li key={st.id}>
              <div className="title">{st.title}</div>
              {st.cmd && <code>{st.cmd}</code>}
              {st.note && <div className="sub">{st.note}</div>}
            </li>
          ))}
        </ol>
      </Card>
    )
  }
  if (id === 'body') {
    return (
      <section className="stats" aria-label="体征摘要">
        <Stat label={`最新体重${d.latest ? ` · ${d.latest.date.slice(5)}` : ''}`} value={n(d.latest?.weight_kg, ' kg')}
          sub={`7 日均 ${n(d.ma7, ' kg')}`} />
        <Stat label="BMI" value={n(d.bmi)} sub={d.bmi_band} tone={d.bmi_band === '正常' ? 'green' : 'amber'} />
        <Stat label="目标区间" value={d.targets ? `${d.targets.weight_kg_low}–${d.targets.weight_kg_high}` : '—'}
          sub={d.distance_to_target != null ? `距目标 ${d.distance_to_target} kg` : undefined} />
        <Stat label="周变化" value={n(d.weekly_delta, ' kg')} sub={`共 ${d.count} 条记录`} />
      </section>
    )
  }
  if (id === 'nutrition') {
    const below = d.day_gap?.below || []
    return (
      <section className="stats" aria-label="营养摘要">
        <Stat label={`当日热量 · ${d.as_of?.slice(5)}`} value={n(d.day_gap?.diet_kcal, ' kcal')}
          sub={`近 ${d.recent_days} 日均 ${n(d.window_avg?.diet_kcal, ' kcal')}`} />
        <Stat label="当日缺口" value={below.length ? below.map((b) => b.label).join('、') : '无'}
          tone={below.length ? 'amber' : 'green'}
          sub={below.map((b) => `${b.label} ${b.actual}/${b.target}g`).join(' · ') || '宏量达标'} />
        <Stat label="建议补充" value={d.suggestions?.[0] ? d.suggestions[0].name : '—'}
          sub={d.suggestions?.[0] ? `${d.suggestions[0].amount}${d.suggestions[0].unit} · 补${d.suggestions[0].for_label}` : undefined} />
        <Stat label="极低热量连续" value={`${d.extreme?.streak ?? 0} 天`} tone={d.extreme?.triggered ? 'red' : undefined}
          sub={`阈值 ${d.extreme?.threshold} kcal × ${d.extreme?.need_days} 天`} />
      </section>
    )
  }
  if (id === 'coach') {
    const c = d.completion || {}
    return (
      <section className="stats" aria-label="训练摘要">
        <Stat label="本窗口完成" value={`${n(c.completed)}${c.planned ? `/${c.planned}` : ''}`} sub={`完成率 ${pct(c.ratio)}`} />
        <Stat label="训练次数" value={d.sessions_in_window ?? '—'} sub={`动作 ${d.items_in_window ?? '—'} 条`} />
        <Stat label="建议" value={(d.suggestions || []).length} sub="条（详见下方全文）" />
      </section>
    )
  }
  if (id === 'tutor') {
    return (
      <section className="stats" aria-label="学习摘要">
        <Stat label="今日待复习" value={(d.due_today || []).length} />
        <Stat label="逾期复习" value={(d.overdue || []).length} tone={(d.overdue || []).length ? 'red' : 'green'} />
        <Stat label="队列总量" value={d.queue_total ?? '—'} sub="以最近一次 CLI tutor 重建为准" />
      </section>
    )
  }
  if (id === 'promises') {
    const c = d.counts || {}
    return (
      <section className="stats" aria-label="承诺摘要">
        <Stat label="兑现率" value={pct(d.rate)} tone={d.rate >= 0.6 ? 'green' : 'amber'} />
        <Stat label="已兑现" value={n(c.fulfilled)} tone="green" />
        <Stat label="未兑现" value={n(c.missed)} tone={c.missed ? 'red' : undefined} />
        <Stat label="无法判定" value={n(c.unmapped)} sub={`无数据 ${n(c.no_data)}`} />
      </section>
    )
  }
  if (id === 'week-done') {
    return (
      <section className="stats" aria-label="本周做成摘要">
        <Stat label="ClickUp 完成" value={n(d.clickup_total)} sub={`${d.start} ~ ${d.end}`}
          tone={d.clickup_total ? 'green' : undefined} />
        <Stat label="复盘三件事" value={n(d.three_total)} sub={`${(d.three_things || []).length} 天有记录`} />
      </section>
    )
  }
  if (id === 'streaks') {
    return (
      <section className="stats" aria-label="连续天数摘要">
        <Stat label="复盘入库" value={n(d.review?.current, ' 天')} sub={d.review?.as_of ? `截至 ${d.review.as_of}` : undefined} tone="green" />
        <Stat label="训练达标" value={n(d.training?.current, ' 个训练日')} />
      </section>
    )
  }
  return null
}

export default function Life() {
  const [tab, setTab] = useState('morning')
  const cur = TABS.find((t) => t.id === tab)
  const res = useAsync((signal) => cur.load(signal), [tab])
  return (
    <>
      <header className="topbar">
        <div>
          <h1>生活管家</h1>
          <p className="subtitle">健康 / 训练 / 营养 / 习惯 / 学习 / 承诺（与 CLI 同名命令同源，只读；不计入四维评分）</p>
        </div>
      </header>
      <div className="tabs" role="tablist" aria-label="管家领域">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`ltab-${t.id}`} aria-selected={tab === t.id}
            aria-controls="lpanel" className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="lpanel" aria-labelledby={`ltab-${tab}`} aria-busy={res.loading}>
        {res.error ? <ErrorBox error={res.error} onRetry={res.reload} />
          : !res.data || res.loading ? <Loading />
          : (
            <>
              {tab === 'tutor' && res.data.queue_rebuilt === false && (
                <div className="banner" role="note">
                  看板只读，不重建复习队列；如需刷新队列请在命令行执行 <code>python -m review_tool tutor</code>。
                </div>
              )}
              {res.data.data && <Highlights id={tab} d={res.data.data} />}
              <Card title="全文" meta={`= CLI ${cur.cli || (tab === 'morning' || tab === 'evening' ? `steward --slot ${tab}` : tab)}`}>
                <pre className="plain">{res.data.text}</pre>
              </Card>
            </>
          )}
      </div>
    </>
  )
}
