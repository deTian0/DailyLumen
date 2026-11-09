// W9 写操作确认流：① 预览（plan，不写任何东西）→ ② 确认（confirm，执行预览过的内容）
// 只在 serve --enable-write 时可用；只读启动 / 门禁不满足时整卡折叠成一行说明（W12）。
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { CopyButton, ErrorBox } from './Common'

export const READONLY_NOTE = '看板以只读启动；如需写入请用 serve --enable-write 重启。'

// W12 门禁折叠：一行说明，可展开看原因与切换方法（不占大块禁用区）
export function GateLine({ title, reason }) {
  return (
    <details className="gate-line">
      <summary>
        <strong>{title}</strong>
        <span className="muted"> · 暂不可用（点开看原因）</span>
      </summary>
      <p className="hint">{reason}</p>
    </details>
  )
}

// 统一门禁原因：只读优先，其次前置门禁（如 mode≠deepseek）
export function gateReason(health, blockedReason) {
  if (!health || health.readonly !== false) return READONLY_NOTE
  return blockedReason || null
}

// canConfirm(preview)：预览判定为无改动时返回 false → 不给确认按钮（避免无意义写入）
// blockedReason：前置门禁原因（如 mode≠deepseek），非空时整卡折叠为 GateLine
// onDone(result)：确认成功后的回调（如定稿后串到 ingest 预览）
// name：按钮可访问名里的动作名（默认 title），如「预览：同步习惯」
// canPreview：表单未就绪（如 JSON 语法错）时禁用预览，避免无意义打后端
export function WriteFlow({ action, params, health, toast, title, desc, renderPreview, confirmLabel = '确认写入',
  canConfirm, canPreview = true, blockedReason, onDone, body, autoPreview, name, previewLabel = '预览' }) {
  const [plan, setPlan] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const gate = gateReason(health, blockedReason)
  const writable = !!health && !gate
  const confirmable = plan && (!canConfirm || canConfirm(plan.preview))
  const act = name || title

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
    let r
    try {
      r = await api.writeConfirm(plan.token)
    } catch (e) {
      // 服务端取 token 即作废：失败后不留旧预览（防止拿用过的 token 再点确认）
      setPlan(null)
      throw e
    }
    setPlan(null)
    setRes(r)
    toast?.('已写入，回读校验通过')
    onDone?.(r)
  })

  if (health && gate) return <GateLine title={title} reason={gate} />

  return (
    <section className="write-flow" aria-label={title}>
      <div className="write-head">
        <div>
          <strong>{title}</strong>
          <p className="muted">{desc}</p>
        </div>
        <button type="button" className="btn-ghost" onClick={preview}
          disabled={!writable || busy || !canPreview}
          aria-label={`${plan ? '重新' : ''}${previewLabel}：${act}`}>
          {busy && !plan ? '预览中…' : plan ? '重新预览' : `① ${previewLabel}`}
        </button>
      </div>
      {/* token 单次有效：确认失败后重试一律重新预览（拿新 token），不复用旧 token */}
      {err && <ErrorBox error={err} onRetry={writable ? preview : undefined} />}
      {plan && (
        <div className="write-plan" role="region" aria-label={`写入预览：${act}`}>
          {renderPreview(plan.preview)}
          <p className="hint">
            等价 CLI：<code className="cli">{plan.cli}</code> · 确认有效期 {Math.round(plan.expires_in / 60)} 分钟，仅可使用一次
          </p>
          <div className="card-actions">
            {confirmable && (
              <button type="button" className="btn-primary" onClick={confirm} disabled={busy}
                aria-label={`${confirmLabel}：${act}`}>
                {busy ? '写入中…' : `② ${confirmLabel}`}
              </button>
            )}
            <button type="button" className="btn-ghost" onClick={() => setPlan(null)} disabled={busy}
              aria-label={`${confirmable ? '取消' : '关闭'}：${act}`}>
              {confirmable ? '取消' : '关闭'}
            </button>
            <CopyButton text={plan.cli} toast={toast} label="复制 CLI" aria={`复制 CLI：${act}`} />
          </div>
        </div>
      )}
      {res && (
        <div className="banner" role="status">
          已完成（{res.cli.split('\n')[0]}{res.cli.includes('\n') ? ' 等' : ''}）
          {res.result?.backup && <> · 库已先备份：{res.result.backup}</>}
          {res.result?.next && <> · 下一步：{res.result.next}</>}
        </div>
      )}
    </section>
  )
}
