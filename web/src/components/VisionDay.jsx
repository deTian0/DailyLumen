// W11 / FR-I2：读图日流程 —— 选图（上传 / 收件箱）→ ① 预览字段（vision，不写盘）→ ② 写 md 数据块
// → 串到下方 ingest 预览（先 md 后库）→ 可选：归档本次用到的收件箱图片。
// 非 deepseek mode：整卡按钮禁用并提前说明原因（门禁在服务端同样生效）。
import { useState } from 'react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { GateLine, WriteFlow, gateReason } from './WriteFlow'

const MAX_IMAGES = 6
const MAX_MB = 8
const ACCEPT = 'image/png,image/jpeg,image/webp'
const KINDS = [
  { id: 'auto', label: '自动识别' },
  { id: 'diet', label: '饮食（薄荷）' },
  { id: 'sleep', label: '睡眠' },
  { id: 'screen', label: '屏幕时间' },
]

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result)
    r.onerror = () => reject(r.error)
    r.readAsDataURL(file)
  })
}

function VisionPreview(p) {
  const fields = Object.entries(p.fields || {}).filter(([k]) => k !== '_unknown')
  return (
    <>
      <p className="muted">
        {p.date} · kind={p.kind} · 成功 {p.ok_images?.length ?? 0} 张
        {p.merge_strategy === 'later_wins' && ' · 多图合并：后图覆盖前图'}
      </p>
      {p.failed_images?.length > 0 && (
        <p className="hint hint-warn" role="alert">
          {p.failed_images.length} 张读图失败（已跳过）：{p.failed_images.map((x) => x.image).join('、')}
        </p>
      )}
      {p.conflicts?.length > 0 && (
        <div className="hint hint-warn">
          <strong>字段冲突 {p.conflicts.length} 处（按后图覆盖）：</strong>
          <ul>
            {p.conflicts.map((c, i) => (
              <li key={i}><code>{c.key}</code>：{String(c.was)} → <strong>{String(c.now)}</strong></li>
            ))}
          </ul>
        </div>
      )}
      {fields.length ? (
        <dl className="kv">
          {fields.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{String(v)}</dd></div>)}
        </dl>
      ) : <p className="muted">没有读出任何字段。</p>}
      {p.diff_lines?.length > 0 ? (
        <details open>
          <summary>md 数据块将变化 {p.diff_lines.length} 行</summary>
          <pre className="diff">{p.diff_lines.join('\n')}</pre>
        </details>
      ) : <p className="muted">数据块无变化，无需写入。</p>}
      <p className="hint">确认后只写复盘 md 的 data 块并打「待人审」标记，不写库；入库在下方单独确认。</p>
    </>
  )
}

export function VisionDay({ date, health, toast, ai, onWritten }) {
  const [kind, setKind] = useState('auto')
  const [uploads, setUploads] = useState([]) // [{name, data}]
  const [picked, setPicked] = useState([]) // 收件箱文件名
  const [fileErr, setFileErr] = useState(null)
  const [usedInbox, setUsedInbox] = useState([]) // 已写入 md 的收件箱图 → 可归档
  const inbox = useAsync((signal) => (health?.readonly === false ? api.inbox({ signal }) : Promise.resolve(null)),
    [health?.readonly])
  const gate = ai && !ai.allowed ? ai.reason : undefined
  const total = uploads.length + picked.length
  const noImage = total === 0 ? '先选择至少一张截图（上传或收件箱）' : undefined

  async function onFiles(e) {
    setFileErr(null)
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    const bad = files.find((f) => !ACCEPT.split(',').includes(f.type) || f.size > MAX_MB * 1024 * 1024)
    if (bad) {
      setFileErr(`「${bad.name}」不是 PNG / JPEG / WebP，或超过 ${MAX_MB} MB`)
      return
    }
    if (files.length + total > MAX_IMAGES) {
      setFileErr(`一次最多 ${MAX_IMAGES} 张`)
      return
    }
    const read = await Promise.all(files.map(async (f) => ({ name: f.name, data: await readAsDataUrl(f) })))
    setUploads((u) => [...u, ...read])
  }

  const togglePick = (n) => setPicked((s) => (s.includes(n) ? s.filter((x) => x !== n) : [...s, n]))
  const disabled = !!gate || health?.readonly !== false
  // W12 门禁折叠：只读 / 非 deepseek 时整卡收成一行（不占大块禁用区）
  const hardGate = gateReason(health, gate)
  if (health && hardGate) return <GateLine title="读图日流程" reason={hardGate} />

  return (
    <>
      <fieldset className="vision-pick" disabled={disabled}>
        <legend className="visually-hidden">选择截图</legend>
        <div className="vision-row">
          <label>
            类型{' '}
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
            </select>
          </label>
          <label className="btn-ghost btn-sm file-btn">
            ＋ 上传截图
            <input type="file" accept={ACCEPT} multiple onChange={onFiles} className="visually-hidden" />
          </label>
          <span className="muted">已选 {total}/{MAX_IMAGES} 张 · 单张 ≤ {MAX_MB} MB</span>
        </div>
        {fileErr && <p className="hint hint-warn" role="alert">{fileErr}</p>}
        {uploads.length > 0 && (
          <ul className="chips" aria-label="已上传">
            {uploads.map((u, i) => (
              <li key={i}>
                <img className="thumb" src={u.data} alt="" />
                {u.name}
                <button type="button" className="chip-x" aria-label={`移除 ${u.name}`}
                  onClick={() => setUploads((s) => s.filter((_, j) => j !== i))}>×</button>
              </li>
            ))}
          </ul>
        )}
        {inbox.data?.items?.length > 0 && (
          <div className="inbox-pick">
            <span className="muted">收件箱（local/每日复盘/收件箱/）：</span>
            {inbox.data.items.map((it) => (
              <label key={it.name} className="check">
                <input type="checkbox" checked={picked.includes(it.name)} onChange={() => togglePick(it.name)} />
                <img className="thumb" src={api.inboxImageUrl(it.name)} alt="" loading="lazy" />
                {it.name} <span className="muted">· {Math.round(it.size / 1024)} KB · {it.mtime.slice(5)}</span>
              </label>
            ))}
          </div>
        )}
      </fieldset>

      <WriteFlow action="vision" body={{ date, kind, uploads, inbox: picked }}
        health={health} toast={toast}
        title="① 读图 → ② 写入 md 数据块"
        desc="上传的截图只在预览期间存于临时目录、用完即删；确认写入的正是预览出的字段。"
        blockedReason={gate || noImage}
        confirmLabel="确认写入 md"
        canConfirm={(p) => p.changed}
        onDone={() => {
          setUsedInbox(picked)
          setUploads([])
          setPicked([])
          onWritten?.()
        }}
        renderPreview={VisionPreview} />

      {usedInbox.length > 0 && (
        <WriteFlow action="inbox-archive" body={{ date, files: usedInbox }} health={health} toast={toast}
          title="可选：归档收件箱图片"
          desc={`把本次用到的 ${usedInbox.length} 张收件箱图片移到 收件箱/已处理/${date}/（移动，不删除，可还原）。`}
          confirmLabel="确认归档"
          canConfirm={(p) => p.planned.length > 0}
          onDone={() => { setUsedInbox([]); inbox.reload() }}
          renderPreview={(p) => (
            <>
              <p className="muted">目标：{p.dest}</p>
              <ul>
                {p.planned.map((x) => <li key={x.src}>{x.src} → {x.dest}</li>)}
                {p.skipped.map((x) => <li key={x.file} className="muted">{x.file}：跳过（{x.reason}）</li>)}
              </ul>
            </>
          )} />
      )}
    </>
  )
}
