// D4：今日「今晚三步」只读条。消费 steward evening 结构化 steps；不并入复盘四步；无新写。

/** 夜间主路径三步（从 evening 全量清单挑出）；顺序固定。 */
const TONIGHT = [
  {
    id: 'intake',
    fallbackTitle: '走 daily-review-intake 全流程',
    href: '#/life?tab=day-help',
    linkLabel: '一日三步 →',
  },
  {
    id: 'training',
    fallbackTitle: '练练同步训练日与明细',
    href: '#/life?tab=coach&focus=keepstrong-sync',
    linkLabel: '去同步 md →',
  },
  {
    id: 'doctor',
    fallbackTitle: '收尾体检',
    href: '#/doctor',
    linkLabel: '去体检 →',
  },
]

export function EveningGuideStrip({ evening }) {
  if (!evening) return null

  const data = evening.data || evening
  const byId = new Map((data.steps || []).map((s) => [s.id, s]))
  const steps = TONIGHT.map((t) => {
    const src = byId.get(t.id)
    return {
      id: t.id,
      title: src?.title || t.fallbackTitle,
      note: src?.note || '',
      href: t.href,
      linkLabel: t.linkLabel,
    }
  })

  const asOf = data.as_of
  const empty = !(data.steps && data.steps.length)

  return (
    <section className="card review-strip" aria-label="今晚三步">
      <div className="card-h">
        <h2>今晚三步{asOf ? ` · ${asOf}` : ''}</h2>
        <a className="btn-ghost btn-sm" href="#/life?tab=evening">完整夜间指引 →</a>
      </div>
      {empty ? (
        <p className="hint">夜间指引暂无结构化步骤，可打开生活管家「夜间复盘指引」查看全文。</p>
      ) : (
        <ol className="tday-list" aria-label="今晚三步">
          {steps.map((st, i) => (
            <li key={st.id} className="tday-row">
              <span className="tday-label">{i + 1}. {st.title}</span>
              <a className="btn-ghost btn-sm" href={st.href}>{st.linkLabel}</a>
            </li>
          ))}
        </ol>
      )}
      <p className="hint">
        只读导流；写 md / 代勾 / ingest 仍须在对应页预览→确认。
        {' · '}
        <a href="#/life?tab=day-help">一日三步全文</a>
      </p>
    </section>
  )
}
