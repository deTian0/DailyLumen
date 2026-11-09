// B15：受控代勾 ClickUp「练练健身」习惯 —— 只写 ClickUp，≠ 训练明细入库；habit_logs 另 sync。
import { useState } from 'react'
import { todayStr } from '../lib/api'
import { Card } from './Common'
import { WriteFlow } from './WriteFlow'

function HabitPreview(p) {
  const hint = p.keepstrong_hint?.message || ''
  return (
    <>
      <p className="muted">{p.disclaimer || '这是习惯勾选，≠ 训练明细入库。'}</p>
      <ul className="task-list" aria-label="代勾预览">
        <li className="task">
          <div className="task-body">
            <div className="title">{p.label || p.habit_key}</div>
            <div className="sub">{p.date} · {p.name} · {p.task_id}</div>
          </div>
          <span className={`pill ${p.action === 'skip_closed' ? 'pill-green' : ''}`}>
            {p.action === 'skip_closed' ? '已完成（幂等）' : '将勾选'}
          </span>
        </li>
      </ul>
      {hint && <p className="hint">{hint}</p>}
      <p className="hint">
        确认后只写 ClickUp；不写 <code>habit_logs</code> / <code>training_*</code>。
        入库请另跑 <code>habits --sync</code>。
      </p>
    </>
  )
}

export function ClickupHabitWrite({ health, toast }) {
  const [day, setDay] = useState(todayStr())
  return (
    <Card title="代勾「练练健身」习惯" meta="ClickUp Continuity · ≠ 训练入库">
      <p className="hint">
        练练完成后可在此受控勾选 ClickUp「习惯与打卡 · 练练健身」。
        预览→确认才写；不会静默自动勾，也不会反推训练表。
      </p>
      <label className="field">
        <span>归属日</span>
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
      </label>
      <WriteFlow
        action="clickup-habit"
        body={{ habit: 'lianlian', date: day || undefined }}
        health={health}
        toast={toast}
        title="代勾练练健身习惯"
        name="代勾练练健身"
        desc="只勾 ClickUp 习惯（Continuity），≠ 练练训练明细入库。"
        renderPreview={HabitPreview}
        confirmLabel="确认勾选"
        canConfirm={(p) => p.action !== 'skip_closed'}
      />
    </Card>
  )
}
