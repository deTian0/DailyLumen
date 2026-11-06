import { useEffect, useState } from 'react'
import { api, downloadFile, errText } from '../lib/api'
import { Markdown } from '../lib/markdown'
import { toProseSource } from '../lib/prose'

// W14：<img> 不能带请求头 → 先带 key 取 blob 再显示；卸载 / 换图时 revoke
export function AuthImage({ path, alt = '', className, onLoad, onError, style }) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    let url = null
    let alive = true
    const ctrl = new AbortController()
    api.blobUrl(path, { signal: ctrl.signal }).then(
      (u) => {
        if (alive) {
          url = u
          setSrc(u)
        } else URL.revokeObjectURL(u)
      },
      (e) => {
        if (alive && e?.name !== 'AbortError') onError?.(e)
      },
    )
    return () => {
      alive = false
      ctrl.abort()
      if (url) URL.revokeObjectURL(url)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path])
  if (!src) return null
  return <img className={className} src={src} alt={alt} onLoad={onLoad} style={style}
    onError={() => onError?.(new Error('image decode failed'))} />
}

export function DownloadButton({ path, filename, toast, label = '下载 .md' }) {
  const [busy, setBusy] = useState(false)
  async function go() {
    setBusy(true)
    try {
      await downloadFile(path, filename)
    } catch (e) {
      toast?.(`下载失败：${errText(e)}`)
    } finally {
      setBusy(false)
    }
  }
  return (
    <button type="button" className="btn-ghost" onClick={go} disabled={busy}>
      {busy ? '下载中…' : label}
    </button>
  )
}

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
export function CopyButton({ text, toast, label = '复制全文', aria }) {
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
    <button type="button" className="btn-ghost" onClick={copy} disabled={!text} aria-label={aria}>
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
    <article className={`stat ${tone ? `stat-tone-${tone}` : ''}`}>
      <div className="label">{label}</div>
      <div className={`value ${tone ? `tone-${tone}` : ''}`}>{value}</div>
      {sub && <div className="delta">{sub}</div>}
    </article>
  )
}

/** 报告 / CLI 全文：结构化 prose，不用等宽灰墙 */
export function Prose({ source, className = '' }) {
  return (
    <div className={`prose-panel ${className}`.trim()}>
      <Markdown source={toProseSource(source)} />
    </div>
  )
}
