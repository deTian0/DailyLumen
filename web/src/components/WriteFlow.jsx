// W9 写操作确认流：① 预览（plan，不写任何东西）→ ② 确认（confirm，执行预览过的内容）
// 只在 serve --enable-write 时可用；只读启动时按钮禁用并说明原因。
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { CopyButton, ErrorBox } from './Common'

// canConfirm(preview)：预览判定为无改动时返回 false → 不给确认按钮（避免无意义写入）
// blockedReason：前置门禁原因（如 mode≠deepseek），非空时预览按钮禁用并展示原因
// onDone(result)：确认成功后的回调（如定稿后串到 ingest 预览）
export function WriteFlow({ action, params, health, toast, title, desc, renderPreview, confirmLabel = '确认写入',
  canConfirm, blockedReason, onDone, body, autoPreview }) {
  const [plan, setPlan] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const writable = health && health.readonly === false && !blockedReason
  const confirmable = plan && (!canConfirm || canConfirm(plan.preview))

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
    setPlan(await (body !== undefined ? api.writePlanBody(action, body) : api.writePlan(action, params)))
  })
  // autoPreview：外部串联（如定稿完成 → 自动出 ingest 预览）时变更 key 即触发一次预览
  useEffect(() => {
    if (autoPreview && writable) preview()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPreview])
  const confirm = () => step(async () => {
    const r = await api.writeConfirm(plan.token)
    setPlan(null)
    setRes(r)
    toast?.('已写入，回读校验通过')
    onDone?.(r)
  })
  const note = !health || health.readonly !== false
    ? '看板以只读启动；如需写入请用 serve --enable-write 重启。'
    : blockedReason || desc

  return (
    <section className="write-flow" aria-label={title}>
      <div className="write-head">
        <div>
          <strong>{title}</strong>
          <p className="muted">{note}</p>
        </div>
        <button type="button" className="btn-ghost" onClick={preview} disabled={!writable || busy}>
          {busy && !plan ? '预览中…' : plan ? '重新预览' : '① 预览'}
        </button>
      </div>
      {/* token 单次有效：确认失败后重试一律重新预览（拿新 token），不复用旧 token */}
      {err && <ErrorBox error={err} onRetry={writable ? preview : undefined} />}
      {plan && (
        <div className="write-plan" role="region" aria-label="写入预览">
          {renderPreview(plan.preview)}
          <p className="hint">
            等价 CLI：<code>{plan.cli}</code> · 确认有效期 {Math.round(plan.expires_in / 60)} 分钟，仅可使用一次
          </p>
          <div className="card-actions">
            {confirmable && (
              <button type="button" className="btn-primary" onClick={confirm} disabled={busy}>
                {busy ? '写入中…' : `② ${confirmLabel}`}
              </button>
            )}
            <button type="button" className="btn-ghost" onClick={() => setPlan(null)} disabled={busy}>
              {confirmable ? '取消' : '关闭'}
            </button>
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
