// D2：今日训练日状态条（只读）。并列于 ReviewSteps，不并入复盘四步。
import { StatusMark } from '../Common'

function mark(ok, pendingLabel, okLabel = '已完成') {
  if (ok === true) return <StatusMark tone="ok" label={okLabel} />
  if (ok === false) return <StatusMark tone="muted" label={pendingLabel} />
  return <StatusMark tone="muted" label="未知" />
}

export function TrainingDayStrip({ status }) {
  if (!status) return null
  const ks = status.keepstrong || {}
  const completed = ks.checked ? !!ks.completed : null
  const next = status.next

  let cta = null
  if (next === 'sync_md') {
    cta = <a className="btn-ghost btn-sm" href={status.links?.sync || '#/life?tab=coach'}>去同步复盘 md →</a>
  } else if (next === 'habit_optional') {
    cta = <a className="btn-ghost btn-sm" href={status.links?.habit || '#/life?tab=coach'}>可选：代勾练练健身 →</a>
  } else if (next === 'create_md') {
    cta = <a className="btn-ghost btn-sm" href={status.links?.coach || '#/life?tab=coach'}>先建当日复盘 →</a>
  } else if (next === 'none' || next === 'unknown') {
    cta = <a className="btn-ghost btn-sm" href={status.links?.coach || '#/life?tab=coach'}>训练页 →</a>
  }

  // 无 completed 时不诱导代勾（即使链接存在也不用 habit CTA）
  if (completed === false && next === 'habit_optional') cta = null

  return (
    <section className="card review-strip" aria-label="今日训练日状态">
      <div className="card-h">
        <h2>今日训练日</h2>
        {cta}
      </div>
      <ul className="tday-list" aria-label={`训练日状态 · ${status.date}`}>
        <li className="tday-row">
          <span className="tday-label">练练 completed</span>
          {mark(completed, '无 / 未查到', '有')}
        </li>
        <li className="tday-row">
          <span className="tday-label">复盘 md 训练块</span>
          {mark(status.md_exists ? status.md_synced : false, status.md_exists ? '未同步' : '无 md', '已写入')}
        </li>
        <li className="tday-row">
          <span className="tday-label">代勾练练健身</span>
          {completed
            ? <StatusMark tone="progress" label="可选（须确认）" />
            : <StatusMark tone="muted" label="无 completed 不诱导" />}
        </li>
      </ul>
      <p className="hint">{ks.message || status.note}</p>
    </section>
  )
}
