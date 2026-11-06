// W14 登录页：输入 local/.env 里的 DAILYLUMEN_WEB_KEY。先用 /api/health 校验，通过才保存。
// 默认存 sessionStorage（关标签页即失效）；勾选「记住」才进 localStorage。
import { useState } from 'react'
import { authKey, errText, verifyKey } from '../lib/api'

export default function Login({ onSuccess, expired }) {
  const [key, setKey] = useState('')
  const [remember, setRemember] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e) {
    e.preventDefault()
    const k = key.trim()
    if (!k) {
      setErr('请输入访问密钥')
      return
    }
    setBusy(true)
    setErr('')
    try {
      if (await verifyKey(k)) {
        authKey.set(k, remember)
        setKey('')
        onSuccess?.()
      } else {
        setErr('密钥不正确：请核对 local/.env 中 DAILYLUMEN_WEB_KEY 的值')
      }
    } catch (ex) {
      setErr(errText(ex))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-wrap" id="main">
      <form className="card login-card" onSubmit={submit} aria-labelledby="login-title">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">DL</div>
          DailyLumen
        </div>
        <h1 id="login-title">输入访问密钥</h1>
        {expired && (
          <p className="banner banner-warn" role="alert">密钥已失效或服务已更换密钥，请重新输入。</p>
        )}
        <p className="muted">
          密钥是 <code>local/.env</code> 里 <code>DAILYLUMEN_WEB_KEY</code> 的值，只保存在本浏览器。
        </p>
        <label className="field">
          <span>访问密钥</span>
          <input type="password" autoComplete="current-password" value={key} autoFocus
            onChange={(e) => setKey(e.target.value)} aria-invalid={!!err} aria-describedby="login-err" />
        </label>
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          在此浏览器记住（存 localStorage；不勾则关闭标签页后需重新输入）
        </label>
        <div id="login-err" className="login-err" role="alert">{err}</div>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? '校验中…' : '进入看板'}
        </button>
      </form>
    </main>
  )
}
