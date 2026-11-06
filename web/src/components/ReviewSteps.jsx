// W12 复盘闭环进度条：读图 → 草稿 → 定稿 → 入库，标明当前所处步骤。
// 状态全部取自 doctor 的 day_ready（后端 reports.day_close.assess_day_ready 单源），前端只做映射展示。
// 类名用 rstep-* 前缀，避开 Life 页管家清单已占用的 .steps。
const STEPS = [
  {
    id: 'vision', label: '读图',
    done: (r) => r.md_exists && !(r.missing_focus || []).length,
    todo: (r) => (r.md_exists ? `缺关注字段：${(r.missing_focus || []).join('、')}` : '还没有复盘 md'),
  },
  { id: 'draft', label: '草稿', done: (r) => r.md_exists, todo: () => '还没有复盘 md / 草稿' },
  { id: 'final', label: '定稿', done: (r) => r.md_exists && !r.pending_draft, todo: () => '仍有待人审标记' },
  { id: 'ingest', label: '入库', done: (r) => !!r.ingested, todo: () => '尚未入库' },
]

export function ReviewSteps({ ready }) {
  if (!ready) return null
  const states = STEPS.map((s) => ({ ...s, ok: !!s.done(ready) }))
  const cur = states.findIndex((s) => !s.ok)
  return (
    <div className="rsteps">
      <ol className="rstep-list" aria-label={`复盘闭环进度 · ${ready.day}`}>
        {states.map((s, i) => {
          const st = s.ok ? 'done' : i === cur ? 'current' : 'todo'
          return (
            <li key={s.id} className={`rstep rstep-${st}`} aria-current={st === 'current' ? 'step' : undefined}>
              <span className="rstep-dot" aria-hidden="true">{s.ok ? '✓' : i + 1}</span>
              <span className="rstep-label">{s.label}</span>
              <span className="visually-hidden">
                {s.ok ? '（已完成）' : st === 'current' ? '（当前步骤）' : '（未开始）'}
              </span>
            </li>
          )
        })}
      </ol>
      <p className="hint">
        {cur === -1
          ? `${ready.day} 四步已齐${ready.inbox_pending ? '；收件箱还有该日截图未归档' : ''}`
          : `${ready.day} 当前在「${states[cur].label}」：${states[cur].todo(ready)}`}
      </p>
    </div>
  )
}
