import { errText } from '../lib/api'

export function Loading({ label = '加载中…' }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="state state-error" role="alert">
      <div>{errText(error)}</div>
      {onRetry && (
        <button type="button" className="btn-ghost" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  )
}

// 复制全文：优先 Clipboard API，失败（非安全上下文等）回退到 textarea + execCommand
export function CopyButton({ text, toast, label = '复制全文' }) {
  async function copy() {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
      } else {
        const ta = document.createElement('textarea')
        ta.value = text
        ta.setAttribute('readonly', '')
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        const ok = document.execCommand('copy')
        document.body.removeChild(ta)
        if (!ok) throw new Error('copy failed')
      }
      toast?.('已复制到剪贴板')
    } catch {
      toast?.('复制失败，请手动选择文本复制')
    }
  }
  return (
    <button type="button" className="btn-ghost" onClick={copy} disabled={!text}>
      {label}
    </button>
  )
}

export function Empty({ children }) {
  return <div className="state state-empty">{children}</div>
}

export function Card({ title, meta, children, className = '', actions }) {
  return (
    <section className={`card ${className}`}>
      <div className="card-h">
        <h2>{title}</h2>
        <div className="card-h-right">
          {meta && <span className="meta">{meta}</span>}
          {actions}
        </div>
      </div>
      {children}
    </section>
  )
}

export function Stat({ label, value, sub, tone }) {
  return (
    <article className="stat">
      <div className="label">{label}</div>
      <div className={`value ${tone ? `tone-${tone}` : ''}`}>{value}</div>
      {sub && <div className="delta">{sub}</div>}
    </article>
  )
}
