// D1：练练 → 复盘 md（keepstrong --write 同源）。≠ KeepStrongWrite 的 App 写回。
import { useState } from 'react'
import { Card } from './Common'
import { WriteFlow } from './WriteFlow'

function SyncPreview(p) {
  const td = p.training_day === true ? '是' : p.training_day === false ? '否' : '未写'
  return (
    <>
      <p className="muted">{p.disclaimer}</p>
      <ul className="task-list" aria-label="同步复盘 md 预览">
        <li className="task"><div className="task-body"><div className="title">日期</div></div><code className="sub">{p.date}</code></li>
        <li className="task"><div className="task-body"><div className="title">文件</div></div><code className="sub">{p.file}</code></li>
        <li className="task"><div className="task-body"><div className="title">当日 completed</div></div><code className="sub">{p.records_day} / 原始 {p.records_raw}</code></li>
        <li className="task"><div className="task-body"><div className="title">训练块</div></div><code className="sub">{p.training_written ? (p.training_replaced ? '替换' : '写入') : '不写'}</code></li>
        <li className="task"><div className="task-body"><div className="title">训练日</div></div><code className="sub">{td}</code></li>
        <li className="task"><div className="task-body"><div className="title">体重</div></div><code className="sub">{p.weight_written ? `${p.weight_kg} kg` : '不改'}</code></li>
        <li className="task"><div className="task-body"><div className="title">md 是否变化</div></div><code className="sub">{p.changed ? '是' : '否'}</code></li>
      </ul>
      {p.empty_note && <p className="hint">{p.empty_note}</p>}
      <p className="hint">入库另走 ingest：<code className="cli">{p.next_ingest_cli}</code></p>
    </>
  )
}

export function KeepstrongSyncWrite({ health, toast, onSynced }) {
  const [day, setDay] = useState('')
  const [ingestKick, setIngestKick] = useState(0)

  return (
    <Card title="练练 → 复盘 md" meta="D1 · keepstrong --write · 不写库">
      <p className="muted">
        把当日练练 <strong>completed</strong> 同步进复盘 md（训练块 / 训练日 / 体重）。
        这是<strong>写本地 md</strong>，不是上方「练练写回」那种 App 写回；入库请在下方另确认。
      </p>
      <div className="inline-form">
        <label>日期<input value={day} onChange={(e) => setDay(e.target.value)} placeholder="YYYY-MM-DD（空=今日）" /></label>
      </div>
      <WriteFlow
        action="keepstrong-sync"
        body={{ date: day || undefined }}
        health={health}
        toast={toast}
        title="同步到复盘 md"
        desc="预览将改动的训练块 / 训练日 / 体重；确认后写 md（不写库、不写练练 App）。"
        renderPreview={SyncPreview}
        confirmLabel="确认写入 md"
        name="同步复盘 md"
        canConfirm={(p) => !!p.changed}
        onDone={() => {
          setIngestKick((k) => k + 1)
          onSynced?.()
        }}
      />
      <WriteFlow
        action="ingest"
        body={{ date: day || undefined }}
        health={health}
        toast={toast}
        autoPreview={ingestKick}
        title="下一步：入库（ingest）"
        desc="可选。把刚写过的复盘 md 解析入库（写库前备份、写后回读）。未同步 md 前也可手动预览。"
        confirmLabel="确认入库"
        name="入库"
        canConfirm={(p) => !p.will_skip}
        renderPreview={(p) => (
          <p className="muted">
            {p.rel || p.file} · 日期 {p.date}
            {p.will_skip ? ' · 含待人审标记，将跳过：请先定稿' : ' · 将解析入库'}
          </p>
        )}
      />
    </Card>
  )
}
