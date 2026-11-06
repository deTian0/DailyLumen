// 极简 Markdown 渲染：标题 / 段落 / 引用 / 列表 / 表格 / 代码块 / 分隔线 + 行内 `code` **粗体**。
// 直接产出 React 元素，不使用 dangerouslySetInnerHTML（报告内容来自本地文件，仍按不可信处理）。
import { Fragment } from 'react'

const INLINE = /(`[^`]+`|\*\*[^*]+\*\*)/g

function inline(text, keyPrefix) {
  return text.split(INLINE).map((part, i) => {
    const key = `${keyPrefix}-${i}`
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={key}>{part.slice(1, -1)}</code>
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }
    return <Fragment key={key}>{part}</Fragment>
  })
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
                    {inline(c, `th${id}-${ci}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, ci) => (
                    <td key={ci}>{inline(c, `td${id}-${ri}-${ci}`)}</td>
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
