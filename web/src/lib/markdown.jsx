// 极简 Markdown 渲染：标题 / 段落 / 引用 / 列表 / 表格 / 代码块 / 分隔线 + 行内 `code` **粗体**。
// B7：表细胞 / 行内识别 `_md_bar`（█░）与可选 CLI（[█·]）→ CSS progressbar。
// 直接产出 React 元素，不使用 dangerouslySetInnerHTML（报告内容来自本地文件，仍按不可信处理）。
import { Fragment } from 'react'
import { barPercent, parseWholeBar, splitAsciiBars } from './asciiBar'

const INLINE = /(`[^`]+`|\*\*[^*]+\*\*)/g

function AsciiProgress({ bar }) {
  const pct = barPercent(bar)
  return (
    <span
      className="md-bar"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={bar.max}
      aria-valuenow={bar.now}
      aria-label={bar.label}
    >
      <span className="md-bar-track" aria-hidden="true">
        <span className="md-bar-fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="md-bar-label">{bar.label}</span>
    </span>
  )
}

function inline(text, keyPrefix) {
  // 先按 code/粗体切，再在纯文本段里替换 ASCII 条
  return text.split(INLINE).flatMap((part, i) => {
    const key = `${keyPrefix}-${i}`
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return [<code key={key}>{part.slice(1, -1)}</code>]
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return [<strong key={key}>{part.slice(2, -2)}</strong>]
    }
    const chunks = splitAsciiBars(part)
    if (chunks.length === 1 && chunks[0].type === 'text') {
      return [<Fragment key={key}>{part}</Fragment>]
    }
    return chunks.map((c, j) => {
      const ck = `${key}-b${j}`
      if (c.type === 'bar') return <AsciiProgress key={ck} bar={c} />
      return <Fragment key={ck}>{c.text}</Fragment>
    })
  })
}

function cellNodes(text, keyPrefix) {
  const whole = parseWholeBar(text)
  if (whole) return <AsciiProgress key={keyPrefix} bar={whole} />
  return inline(text, keyPrefix)
}

const splitRow = (line) =>
  line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim())

const isSep = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line)

export function Markdown({ source }) {
  const lines = (source || '').replace(/\r\n/g, '\n').split('\n')
  const out = []
  let i = 0
  let k = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i++
      continue
    }
    if (line.startsWith('```')) {
      const buf = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++])
      i++
      out.push(<pre key={k++}>{buf.join('\n')}</pre>)
      continue
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) {
      const Tag = `h${Math.min(h[1].length + 1, 6)}`
      out.push(<Tag key={k++}>{inline(h[2], `h${k}`)}</Tag>)
      i++
      continue
    }
    if (/^\s*-{3,}\s*$/.test(line)) {
      out.push(<hr key={k++} />)
      i++
      continue
    }
    if (line.trim().startsWith('|') && i + 1 < lines.length && isSep(lines[i + 1])) {
      const head = splitRow(line)
      i += 2
      const rows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(splitRow(lines[i++]))
      const id = k++
      out.push(
        <div className="md-table" key={id} tabIndex={0} role="region" aria-label="表格（可横向滚动）">
          <table>
            <thead>
              <tr>
                {head.map((c, ci) => (
                  <th key={ci} scope="col">
                    {cellNodes(c, `th${id}-${ci}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, ci) => (
                    <td key={ci}>{cellNodes(c, `td${id}-${ri}-${ci}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }
    if (line.startsWith('>')) {
      const buf = []
      while (i < lines.length && lines[i].startsWith('>')) buf.push(lines[i++].replace(/^>\s?/, ''))
      const id = k++
      out.push(
        <blockquote key={id}>
          {buf.map((b, bi) => (
            <p key={bi}>{inline(b, `q${id}-${bi}`)}</p>
          ))}
        </blockquote>,
      )
      continue
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line)
      const items = []
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        items.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ''))
      }
      const id = k++
      const Tag = ordered ? 'ol' : 'ul'
      out.push(
        <Tag key={id}>
          {items.map((it, ii) => (
            <li key={ii}>{inline(it, `li${id}-${ii}`)}</li>
          ))}
        </Tag>,
      )
      continue
    }
    const buf = [line]
    i++
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,6}\s|>|```|\s*([-*]|\d+\.)\s+|\s*\|)/.test(lines[i])
    ) {
      buf.push(lines[i++])
    }
    const id = k++
    out.push(<p key={id}>{inline(buf.join(' '), `p${id}`)}</p>)
  }
  return <div className="md">{out}</div>
}
