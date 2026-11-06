// W13 从 Today.jsx 拆出
import { WD } from '../../lib/todos'

// W12：快照预览 —— 明确列出将被整天替换的日期（库内现值 → 新值），以及本周节奏替换后的样子。
// 投影数字由后端 plan_clickup_pull 给出（before/after），前端不另算归日。
export function PullPreview(p) {
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
