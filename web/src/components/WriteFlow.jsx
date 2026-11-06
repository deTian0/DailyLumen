// W9 写操作确认流：① 预览（plan，不写任何东西）→ ② 确认（confirm，执行预览过的内容）
// 只在 serve --enable-write 时可用；只读启动时按钮禁用并说明原因。
import { useState } from 'react'
import { api } from '../lib/api'
import { CopyButton, ErrorBox } from './Common'

export function WriteFlow({ action, params, health, toast, title, desc, renderPreview, confirmLabel = '确认写入' }) {
  const [plan, setPlan] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const writable = health && health.readonly === false

  async function step(fn) {
    setBusy(true)
    setErr(null)
    try {
      await fn()
    } catch (e) {
      setErr(e)
    } finally {
      setBusy(false)
    }
  }
  const preview = () => step(async () => {
    setRes(null)
    setPlan(await api.writePlan(action, params))
  })
  const confirm = () => step(async () => {
    const r = await api.writeConfirm(plan.token)
    setPlan(null)
    setRes(r)
    toast?.('已写入，回读校验通过')
  })

  return (
    <section className="write-flow" aria-label={title}>
      <div className="write-head">
        <div>
          <strong>{title}</strong>
          <p className="muted">{writable ? desc : '看板以只读启动；如需写入请用 serve --enable-write 重启。'}</p>
        </div>
        <button type="button" className="btn-ghost" onClick={preview} disabled={!writable || busy}>
          {busy && !plan ? '预览中…' : plan ? '重新预览' : '① 预览'}
        </button>
      </div>
      {err && <ErrorBox error={err} />}
      {plan && (
        <div className="write-plan" role="region" aria-label="写入预览">
          {renderPreview(plan.preview)}
          <p className="hint">
            等价 CLI：<code>{plan.cli}</code> · 确认有效期 {Math.round(plan.expires_in / 60)} 分钟，仅可使用一次
          </p>
          <div className="card-actions">
            <button type="button" className="btn-primary" onClick={confirm} disabled={busy}>
              {busy ? '写入中…' : `② ${confirmLabel}`}
            </button>
            <button type="button" className="btn-ghost" onClick={() => setPlan(null)} disabled={busy}>取消</button>
            <CopyButton text={plan.cli} toast={toast} label="复制 CLI" />
          </div>
        </div>
      )}
      {res && (
        <div className="banner" role="status">
          已完成（{res.cli}）
          {res.result?.backup && <> · 库已先备份：{res.result.backup}</>}
          {res.result?.next && <> · 下一步：{res.result.next}</>}
        </div>
      )}
    </section>
  )
}
