// 把 CLI 风格全文（==== / ---- 分段 / 缩进行）转成可读 Markdown，供 Markdown 组件渲染。
// 不改后端文案；仅前端呈现层。已是 Markdown（含 # 标题）时尽量透传。

const BANNER = /^=+$/
const SEC_DASH = /^-{2,}\s+(.+?)\s+-{2,}$/
const BRACKET = /^\[(.+)\]\s*$/
const LOOKS_MD = /^#{1,6}\s+|^\*\*|^\|.+\|/m

export function toProseSource(text) {
  if (!text) return ''
  const raw = String(text).replace(/\r\n/g, '\n')
  if (LOOKS_MD.test(raw) && !BANNER.test(raw.trim().split('\n')[0] || '')) {
    return raw
  }
  const lines = raw.split('\n')
  const out = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const t = line.trim()
    if (BANNER.test(t)) {
      i += 1
      if (i < lines.length && lines[i].trim() && !BANNER.test(lines[i].trim())) {
        out.push(`# ${lines[i].trim()}`)
        i += 1
        if (i < lines.length && BANNER.test(lines[i].trim())) i += 1
      } else {
        out.push('---')
      }
      continue
    }
    const sec = SEC_DASH.exec(t)
    if (sec) {
      const title = sec[1].replace(/^\d+\.\s*/, '').trim()
      out.push(`## ${title}`)
      i += 1
      continue
    }
    const br = BRACKET.exec(t)
    if (br) {
      out.push(`## ${br[1]}`)
      i += 1
      continue
    }
    if (/^\s{2,}(.*)$/.test(line)) {
      const body = line.replace(/^\s+/, '')
      if (!body) {
        out.push('')
      } else if (/^\d+\.\s+/.test(body)) {
        out.push(body)
      } else if (/^source=/.test(body) || /^python -m /.test(body)) {
        out.push(`> \`${body}\``)
      } else if (/^[✓✔✕×⚠·•]/.test(body) || /^(OK|WARN|FAIL|PASS)\b/i.test(body)) {
        out.push(`- ${body}`)
      } else {
        out.push(`- ${body}`)
      }
      i += 1
      continue
    }
    out.push(line)
    i += 1
  }
  return out.join('\n')
}
