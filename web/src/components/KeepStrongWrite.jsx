// B4 / W17：练练写回卡 —— 6 动作全部上面板；写回不落库、不可撤销；只用 WriteFlow 预览→确认。
import { useState } from 'react'
import { Card } from './Common'
import { WriteFlow } from './WriteFlow'
import { ActionsJsonEditor, parseActionsJson, parseExtraJson } from './ActionsJsonEditor'

export const PLAN_COMMANDS = ['delay', 'cancel_rest', 'add_alternative', 'add_temporary_workout']

const KS_WARN = '写回练练（不落库、不可撤销）；请到 App 核对生效。'

function KsPreview(p) {
  const rows = Object.entries(p).filter(([, v]) => v !== null && v !== undefined && v !== '')
  return (
    <>
      <p className="muted">将向练练健身发起写回（<strong>不落库、不可撤销、不作系统状态</strong>）；请到 App 核对生效。</p>
      <ul className="task-list" aria-label="练练写回内容">
        {rows.map(([k, v]) => (
          <li key={k} className="task">
            <div className="task-body"><div className="title">{k}</div></div>
            <code className="sub">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</code>
          </li>
        ))}
      </ul>
      {p.note && <p className="hint">{p.note}</p>}
    </>
  )
}

export function KeepStrongWrite({ health, toast }) {
  const [metric, setMetric] = useState('weight')
  const [val, setVal] = useState('')
  const [day, setDay] = useState('')
  const [unit, setUnit] = useState('kg')
  const [aid, setAid] = useState('')
  const [w, setW] = useState('')

  const [schedDay, setSchedDay] = useState('')
  const [schedName, setSchedName] = useState('')
  const [schedActions, setSchedActions] = useState('')

  const [tplName, setTplName] = useState('')
  const [tplId, setTplId] = useState('')
  const [tplActions, setTplActions] = useState('')

  const [repId, setRepId] = useState('')
  const [repActions, setRepActions] = useState('')

  const [planId, setPlanId] = useState('')
  const [command, setCommand] = useState('delay')
  const [extraText, setExtraText] = useState('')

  const schedParsed = parseActionsJson(schedActions)
  const tplParsed = parseActionsJson(tplActions)
  const repParsed = parseActionsJson(repActions)
  const extraParsed = parseExtraJson(extraText)

  return (
    <Card title="练练写回" meta="W17/B4 · 写回练练，不落库、不可撤销">
      <p className="muted">
        六种写回均走预览→确认；<strong>写回不落库、不可撤销</strong>。中文参数由后端 URL 编码，前端勿自行 encode。
      </p>

      <div className="write-flow" aria-label="记体征表单">
        <div className="write-head">
          <div><strong>记体征</strong><p className="muted">POST /body/logs · {KS_WARN}</p></div>
        </div>
        <div className="inline-form">
          <label>指标<select value={metric} onChange={(e) => {
            setMetric(e.target.value)
            setUnit(e.target.value === 'weight' ? 'kg' : e.target.value === 'fat' ? '%' : unit)
          }}>
            <option value="weight">weight（体重）</option>
            <option value="fat">fat（体脂）</option>
            <option value="bodyRound">bodyRound（围度）</option>
          </select></label>
          <label>值<input value={val} onChange={(e) => setVal(e.target.value)} placeholder="如 62.5" /></label>
          <label>日期<input value={day} onChange={(e) => setDay(e.target.value)} placeholder="YYYY-MM-DD（空=今日）" /></label>
          <label>单位<input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="kg / % / cm" /></label>
        </div>
        <WriteFlow action="ks-log-body" body={{ metric, value: val, day: day || undefined, unit }}
          health={health} toast={toast} title="记体征" desc="预览后确认写回练练（不落库、不可撤销）。"
          renderPreview={KsPreview} confirmLabel="确认写回" name="记体征"
          canConfirm={() => !!val && !!unit} />
      </div>

      <div className="write-flow" aria-label="设下次重量表单">
        <div className="write-head">
          <div><strong>设下次重量</strong><p className="muted">POST /training/actions/{`{id}`}/weight · 空串=沿用历史 · {KS_WARN}</p></div>
        </div>
        <div className="inline-form">
          <label>actionId<input value={aid} onChange={(e) => setAid(e.target.value)} placeholder="act_xxx" /></label>
          <label>重量(kg)<input value={w} onChange={(e) => setW(e.target.value)} placeholder="留空=沿用历史（⛔ 不用 0）" /></label>
        </div>
        <WriteFlow action="ks-set-weight" body={{ action_id: aid, weight: w === '' ? undefined : w }}
          health={health} toast={toast} title="设下次重量" desc="预览后确认写回练练（不落库、不可撤销）。"
          renderPreview={KsPreview} confirmLabel="确认写回" name="设下次重量"
          canConfirm={() => !!aid} />
      </div>

      <div className="write-flow" aria-label="排课表单">
        <div className="write-head">
          <div><strong>排课</strong><p className="muted">POST /scheduled-workouts · {KS_WARN}</p></div>
        </div>
        <div className="inline-form">
          <label>日期<input value={schedDay} onChange={(e) => setSchedDay(e.target.value)} placeholder="YYYY-MM-DD" /></label>
          <label>课名<input value={schedName} onChange={(e) => setSchedName(e.target.value)} placeholder="如 全身A" /></label>
        </div>
        <ActionsJsonEditor id="ks-sched-actions" value={schedActions} onChange={setSchedActions} />
        <WriteFlow action="ks-schedule"
          body={{ day: schedDay, name: schedName, actions: schedParsed.ok ? schedParsed.actions : [] }}
          health={health} toast={toast} title="排课" desc="预览后确认写回练练（不落库、不可撤销）。"
          renderPreview={KsPreview} confirmLabel="确认写回" name="排课"
          canPreview={!!schedDay && !!schedName && schedParsed.ok}
          canConfirm={() => !!schedDay && !!schedName && schedParsed.ok} />
      </div>

      <div className="write-flow" aria-label="创建模板表单">
        <div className="write-head">
          <div><strong>创建 / 更新模板</strong><p className="muted">POST /templates · {KS_WARN}</p></div>
        </div>
        <div className="inline-form">
          <label>模板名<input value={tplName} onChange={(e) => setTplName(e.target.value)} placeholder="如 下肢日" /></label>
          <label>templateId<input value={tplId} onChange={(e) => setTplId(e.target.value)} placeholder="可选，更新时填" /></label>
        </div>
        <ActionsJsonEditor id="ks-tpl-actions" value={tplActions} onChange={setTplActions} />
        <WriteFlow action="ks-create-template"
          body={{
            name: tplName,
            actions: tplParsed.ok ? tplParsed.actions : [],
            template_id: tplId || undefined,
          }}
          health={health} toast={toast} title="创建模板" desc="预览后确认写回练练（不落库、不可撤销）。"
          renderPreview={KsPreview} confirmLabel="确认写回" name="创建模板"
          canPreview={!!tplName && tplParsed.ok}
          canConfirm={() => !!tplName && tplParsed.ok} />
      </div>

      <div className="write-flow" aria-label="替换模板动作表单">
        <div className="write-head">
          <div><strong>替换模板动作</strong><p className="muted">POST /templates/{`{id}`}/actions · 完整替换 · {KS_WARN}</p></div>
        </div>
        <div className="inline-form">
          <label>templateId<input value={repId} onChange={(e) => setRepId(e.target.value)} placeholder="tpl_xxx" /></label>
        </div>
        <ActionsJsonEditor id="ks-rep-actions" value={repActions} onChange={setRepActions} />
        <WriteFlow action="ks-replace-template-actions"
          body={{ template_id: repId, actions: repParsed.ok ? repParsed.actions : [] }}
          health={health} toast={toast} title="替换模板动作" desc="完整替换（非增量）；预览后确认（不落库、不可撤销）。"
          renderPreview={KsPreview} confirmLabel="确认写回" name="替换模板动作"
          canPreview={!!repId && repParsed.ok}
          canConfirm={() => !!repId && repParsed.ok} />
      </div>

      <div className="write-flow" aria-label="计划命令表单">
        <div className="write-head">
          <div><strong>计划命令</strong><p className="muted">POST /running-plans/{`{id}`}/commands · command 仅 4 值 · {KS_WARN}</p></div>
        </div>
        <div className="inline-form">
          <label>runningPlanId<input value={planId} onChange={(e) => setPlanId(e.target.value)} placeholder="pln_xxx" /></label>
          <label>command<select value={command} onChange={(e) => setCommand(e.target.value)}>
            {PLAN_COMMANDS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select></label>
        </div>
        <label className="json-editor" htmlFor="ks-plan-extra">
          <span>extra JSON（可选）</span>
          <textarea id="ks-plan-extra" value={extraText} onChange={(e) => setExtraText(e.target.value)}
            rows={3} spellCheck={false} placeholder="{}"
            aria-invalid={extraText.trim() !== '' && !extraParsed.ok} />
          <span className={extraParsed.ok || !extraText.trim() ? 'muted' : 'hint-warn'} role={extraParsed.ok || !extraText.trim() ? undefined : 'alert'}>
            {!extraText.trim() ? '可空；非空须为对象' : extraParsed.ok ? 'extra 已解析' : extraParsed.error}
          </span>
        </label>
        <WriteFlow action="ks-plan-command"
          body={{
            running_plan_id: planId,
            command,
            extra: extraParsed.ok ? extraParsed.extra : undefined,
          }}
          health={health} toast={toast} title="计划命令" desc="command 仅 delay / cancel_rest / add_alternative / add_temporary_workout；写回不落库、不可撤销。"
          renderPreview={KsPreview} confirmLabel="确认写回" name="计划命令"
          canPreview={!!planId && PLAN_COMMANDS.includes(command) && extraParsed.ok}
          canConfirm={() => !!planId && PLAN_COMMANDS.includes(command) && extraParsed.ok} />
      </div>
    </Card>
  )
}
