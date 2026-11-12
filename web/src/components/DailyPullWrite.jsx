// D6：夜间 daily-pull 薄封装（= CLI daily-pull --apply）。挂在 Life evening tab。
import { useState } from 'react'
import { Card, StatusMark } from './Common'
import { WriteFlow } from './WriteFlow'

function PullPreview(p) {
  return (
    <>
      <p className="muted">{p.disclaimer}</p>
      <ul className="task-list" aria-label="daily-pull 步骤预览">
        <li className="task">
          <div className="task-body"><div className="title">归属日</div></div>
          <code className="sub">{p.date}</code>
        </li>
        {(p.steps || []).map((st) => (
          <li key={st.cli} className="task">
            <div className="task-body">
              <div className="title">{st.name}</div>
              <div className="sub"><code>{st.cli}</code></div>
            </div>
            <StatusMark tone="progress" label="将执行" />
          </li>
        ))}
      </ul>
      <p className="hint">不含代勾练练健身、不含 finalize；失败步骤不阻断其余。</p>
    </>
  )
}

function ResultView({ result }) {
  if (!result) return null
  const r = result.result || result
  return (
    <ul className="task-list" aria-label="daily-pull 执行结果">
      {(r.steps || []).map((st) => (
        <li key={st.cli || st.name} className="task">
          <div className="task-body">
            <div className="title">{st.name}</div>
            <div className="sub">rc={st.rc}</div>
          </div>
          <StatusMark tone={st.ok ? 'ok' : 'crit'} label={st.ok ? '完成' : '失败'} />
        </li>
      ))}
    </ul>
  )
}

export function DailyPullWrite({ health, toast }) {
  const [day, setDay] = useState('')
  const [last, setLast] = useState(null)

  return (
    <Card title="夜间采集拉齐" meta="D6 · daily-pull --apply · 会打网">
      <p className="muted">
        一条确认跑完：练练落 md+ingest → 习惯快照 → 全量 ingest（G1）。
        仅建议<strong>夜间</strong>使用；预览零副作用，确认才打网写盘。
      </p>
      <div className="inline-form">
        <label>日期<input value={day} onChange={(e) => setDay(e.target.value)} placeholder="YYYY-MM-DD（空=今日）" /></label>
      </div>
      <WriteFlow
        action="daily-pull"
        body={{ date: day || undefined }}
        health={health}
        toast={toast}
        title="夜间拉齐"
        name="夜间拉齐"
        desc="预览三步与副作用；确认后按序执行（失败继续）。"
        renderPreview={PullPreview}
        confirmLabel="确认拉齐"
        canConfirm={(p) => (p.step_count || 0) > 0}
        onDone={(r) => setLast(r)}
      />
      {last && (
        <>
          <p className="hint">{last.result?.next || (last.result?.ok === false ? '部分失败，见下表' : '已完成')}</p>
          <ResultView result={last} />
        </>
      )}
    </Card>
  )
}
