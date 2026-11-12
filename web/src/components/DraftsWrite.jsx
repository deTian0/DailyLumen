// E1 / FR-K3：候选草稿落收件箱（promise / three-things / improve）。
// 红线：草稿不入库（ingest 跳过收件箱）；不做 Web 端勾选回填 —— 回填复盘 md 仍在 md / 会话完成。
import { useState } from 'react'
import { Card, StatusMark } from './Common'
import { WriteFlow } from './WriteFlow'

function DraftPreview(p) {
  const blocked = p.blocked_reason === 'draft_exists'
  return (
    <>
      <p className="muted">{p.disclaimer}</p>
      <ul className="task-list" aria-label="草稿候选">
        {(p.candidates || []).slice(0, 12).map((c, i) => (
          <li key={`${c.name}-${i}`} className="task">
            <div className="task-body">
              <div className="title">{c.name}</div>
              <div className="sub">{c.list}</div>
            </div>
          </li>
        ))}
        {!p.candidates && <li className="task muted">取数上下文骨架（排序查书仍须走 life-decision-guide 会话）</li>}
      </ul>
      <p className="hint">
        将写入 <code>收件箱/{p.file}</code>（{p.bytes} 字节）。
        {blocked && <strong className="ink-amber"> 收件箱已有同名草稿：将拒绝写入，请先归档或用 CLI --out 换目录。</strong>}
      </p>
    </>
  )
}

export function DraftWrite({ kind, health, toast, title, desc, date: fixedDate }) {
  const [day, setDay] = useState(fixedDate || '')
  return (
    <Card title={title} meta="落收件箱 · 不入库">
      <p className="muted">{desc}</p>
      <div className="inline-form">
        <label>日期<input value={day} onChange={(e) => setDay(e.target.value)} placeholder="YYYY-MM-DD（空=今日）" /></label>
      </div>
      <WriteFlow
        action={kind}
        body={{ date: day || undefined }}
        health={health}
        toast={toast}
        title={title}
        name={title}
        desc={desc}
        renderPreview={DraftPreview}
        confirmLabel="确认落收件箱"
        canConfirm={(p) => !p.blocked_reason}
        onDone={(r) => toast?.(`已落收件箱：${r.result?.file || ''}（去复盘 md 勾选回填）`)}
      />
    </Card>
  )
}
