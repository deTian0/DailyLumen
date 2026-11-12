// D5：承诺明细（只读）。消费 collect 已有 items；不改判定口径 / 兑现率。
import { StatusMark } from '../Common'

const STATUS_UI = {
  missed: { tone: 'crit', label: '未兑现' },
  no_data: { tone: 'progress', label: '待判定' },
  unmapped: { tone: 'muted', label: '无法判定' },
  fulfilled: { tone: 'ok', label: '已兑现' },
  declined: { tone: 'muted', label: '明写不设' },
}

/** 关注列表：未兑现优先，其次「对账尚未结束」的待判定；上限与 CLI show_items 同量级。 */
export function pickAttentionItems(items, limit = 12) {
  const list = Array.isArray(items) ? items : []
  const missed = list.filter((r) => r.status === 'missed')
  const pending = list.filter(
    (r) => r.status === 'no_data' && /尚未结束|未记录/.test(r.evidence || ''),
  )
  // 日期新→旧；同日 missed 压在 pending 前（两段各自排再拼接）
  const byDateDesc = (a, b) => String(b.date || '').localeCompare(String(a.date || ''))
  missed.sort(byDateDesc)
  pending.sort(byDateDesc)
  return [...missed, ...pending].slice(0, limit)
}

export function PromiseDetailList({ data }) {
  if (!data) return null
  const items = pickAttentionItems(data.items)
  const total = (data.items || []).length

  return (
    <section className="card" aria-label="承诺明细">
      <div className="card-h">
        <h2>近期关注</h2>
        <span className="meta">未兑现 + 待判定 · 只读</span>
      </div>
      {items.length === 0 ? (
        <p className="hint">
          {total === 0
            ? '还没有承诺记录。在复盘「改进点 / 明日 Top 3」写具体可核对的数字后会出现在这里。'
            : '近期没有未兑现或待判定条目（已兑现 / 无法判定 / 明写不设见下方全文）。'}
        </p>
      ) : (
        <ul className="task-list" aria-label="承诺关注列表">
          {items.map((r) => {
            const ui = STATUS_UI[r.status] || { tone: 'muted', label: r.status }
            const key = `${r.date}-${r.kind}-${r.seq}`
            return (
              <li key={key} className="task">
                <span className="dot" aria-hidden="true" />
                <div className="task-body">
                  <div className="title">{r.text || '（空承诺）'}</div>
                  <div className="sub">
                    {r.date}
                    {r.bucket_label ? ` · ${r.bucket_label}` : ''}
                    {r.kind ? ` · ${r.kind}` : ''}
                    {r.evidence ? ` · ${r.evidence}` : ''}
                  </div>
                </div>
                <StatusMark tone={ui.tone} label={ui.label} />
              </li>
            )
          })}
        </ul>
      )}
      <p className="hint">列表不改兑现率；判定口径与 CLI <code>promises</code> 同源。</p>
    </section>
  )
}
