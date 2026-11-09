// B4：练练写回 actions JSON 编辑 / 前端校验（语法 + 必填 actionId）；中文参数由后端 URL 编码，此处不重复编码。

export const ACTIONS_PLACEHOLDER = `[
  { "actionId": "act_xxx", "groups": [{ "sets": 3, "reps": 10 }] }
]`

/** 解析并校验 actions JSON：须为非空对象数组，每项含非空 actionId。 */
export function parseActionsJson(text) {
  const raw = (text || '').trim()
  if (!raw) return { ok: false, error: 'actions 不能为空' }
  let parsed
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, error: 'JSON 语法错误' }
  }
  if (!Array.isArray(parsed)) return { ok: false, error: 'actions 须为 JSON 数组' }
  if (parsed.length === 0) return { ok: false, error: 'actions 不能为空数组' }
  for (let i = 0; i < parsed.length; i += 1) {
    const item = parsed[i]
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      return { ok: false, error: `第 ${i + 1} 项须为对象` }
    }
    const aid = item.actionId
    if (aid === undefined || aid === null || String(aid).trim() === '') {
      return { ok: false, error: `第 ${i + 1} 项缺少必填字段 actionId` }
    }
  }
  return { ok: true, actions: parsed }
}

/** 可选 extra JSON：空=省略；非空须为对象（非数组）。 */
export function parseExtraJson(text) {
  const raw = (text || '').trim()
  if (!raw) return { ok: true, extra: undefined }
  let parsed
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, error: 'extra JSON 语法错误' }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, error: 'extra 须为 JSON 对象' }
  }
  return { ok: true, extra: parsed }
}

export function ActionsJsonEditor({
  value, onChange, id = 'actions-json', label = 'actions JSON', rows = 6, hint,
}) {
  const parsed = parseActionsJson(value)
  return (
    <label className="json-editor" htmlFor={id}>
      <span>{label}</span>
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        spellCheck={false}
        placeholder={ACTIONS_PLACEHOLDER}
        aria-invalid={value.trim() !== '' && !parsed.ok}
        aria-describedby={`${id}-hint`}
      />
      <span id={`${id}-hint`} className={parsed.ok || !value.trim() ? 'muted' : 'hint-warn'} role={parsed.ok || !value.trim() ? undefined : 'alert'}>
        {!value.trim()
          ? (hint || '须为非空数组，每项含 actionId（中文参数由后端编码，勿自行 encode）')
          : parsed.ok
            ? `已解析 ${parsed.actions.length} 个动作`
            : parsed.error}
      </span>
    </label>
  )
}
