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
