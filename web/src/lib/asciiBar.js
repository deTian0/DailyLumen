// B7：识别周报 md `_md_bar`（█/░，宽约 10）与可选 CLI `_bar`（[█·]）。
// 解析失败原样返回；不改 CLI / md 生成文本。

const MD_WHOLE = /^(█*)(░*)$/
const CLI_WHOLE = /^\[(█*)(·*)\]$/
/** 行内条：CLI 括号条，或连续 █/░（≥2）；后可跟可选分数 */
const INLINE_BAR = /(\[[█·]{2,}\]|[█░]{2,})(?:\s+(\d+)\s*\/\s*(\d+))?/g

/**
 * 解析整段是否为单一进度条（周报表细胞常见）。
 * @returns {{ filled: number, total: number, now: number, max: number, label: string, kind: string } | null}
 */
export function parseWholeBar(text) {
  if (text == null) return null
  const s = String(text).trim()
  if (!s) return null

  let m = MD_WHOLE.exec(s)
  if (m && s.length >= 2 && /^[█░]+$/.test(s)) {
    const filled = m[1].length
    const total = filled + m[2].length
    if (total < 2) return null
    return {
      filled,
      total,
      now: filled,
      max: total,
      label: `${filled}/${total}`,
      kind: 'md',
    }
  }

  m = CLI_WHOLE.exec(s)
  if (m) {
    const filled = m[1].length
    const total = filled + m[2].length
    if (total < 2) return null
    return {
      filled,
      total,
      now: filled,
      max: total,
      label: `${filled}/${total}`,
      kind: 'cli',
    }
  }
  return null
}

/**
 * 切成「普通字串 / 进度条」片段。含分数 `5/7` 时 now=5 max=7。
 */
export function splitAsciiBars(text) {
  const s = String(text ?? '')
  if (!s || !/[█░\[]/.test(s)) return [{ type: 'text', text: s }]

  const parts = []
  let last = 0
  INLINE_BAR.lastIndex = 0
  let m
  while ((m = INLINE_BAR.exec(s)) !== null) {
    const whole = parseWholeBar(m[1])
    if (!whole) continue
    if (m.index > last) {
      parts.push({ type: 'text', text: s.slice(last, m.index) })
    }
    const fracNum = m[2] != null ? Number(m[2]) : null
    const fracDen = m[3] != null ? Number(m[3]) : null
    if (
      fracNum != null &&
      fracDen != null &&
      Number.isFinite(fracNum) &&
      Number.isFinite(fracDen) &&
      fracDen > 0
    ) {
      parts.push({
        type: 'bar',
        filled: whole.filled,
        total: whole.total,
        now: fracNum,
        max: fracDen,
        label: `${fracNum}/${fracDen}`,
        kind: whole.kind,
      })
    } else {
      parts.push({ type: 'bar', ...whole })
    }
    last = m.index + m[0].length
  }
  if (last === 0) return [{ type: 'text', text: s }]
  if (last < s.length) parts.push({ type: 'text', text: s.slice(last) })
  return parts
}

/** 填充比例 0–100（视觉条用 filled/total；与 aria now/max 可不同） */
export function barPercent(bar) {
  if (!bar || !bar.total) return 0
  return Math.max(0, Math.min(100, Math.round((bar.filled / bar.total) * 100)))
}
