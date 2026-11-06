// W13 从 Today.jsx 拆出：单条完成 / 新建任务 / 分组列表 / 批量完成栏
import { useState } from 'react'
import { api, errText } from '../../lib/api'
import { groupTodos } from '../../lib/todos'
import { CopyButton, ErrorBox } from '../Common'

// W10 / FR-J1：任务内联「完成」——预览（一次性 token + 等价 CLI）→ 确认 → 以回读结果为准
function TaskDone({ t, writable, toast, onChanged }) {
  const [plan, setPlan] = useState(null)
  const [state, setState] = useState('idle') // idle | planning | writing | done | error
  const [err, setErr] = useState(null)
  if (!writable) return null
  async function preview() {
    setState('planning')
    setErr(null)
    try {
      setPlan(await api.writePlanBody('task-status', { task_id: t.id, status: 'complete', name: t.name }))
      setState('idle')
    } catch (e) {
      setErr(e)
      setState('error')
    }
  }
  async function confirm() {
    setState('writing') // 乐观：先置灰「写入中」，最终以回读为准
    try {
      await api.writeConfirm(plan.token)
      setState('done')
      setPlan(null)
      toast?.(`已完成「${t.name}」（ClickUp 回读通过）`)
      onChanged?.()
    } catch (e) {
      setErr(e)
      setPlan(null)
      setState('error')
    }
  }
  if (state === 'done') return <span className="pill pill-green">✓ 已完成</span>
  if (plan) {
    return (
      <span className="task-confirm" role="group" aria-label={`确认完成 ${t.name}`}>
        <code title={plan.cli}>{plan.cli.replace('python -m review_tool ', '')}</code>
        <button type="button" className="btn-primary btn-sm" onClick={confirm} disabled={state === 'writing'}>
          {state === 'writing' ? '写入中…' : '确认完成'}
        </button>
        <button type="button" className="btn-ghost btn-sm" onClick={() => setPlan(null)} disabled={state === 'writing'}>取消</button>
      </span>
    )
  }
  return (
    <>
      {state === 'error' && <span className="pill pill-red" role="alert" title={errText(err)}>失败</span>}
      <button type="button" className="btn-ghost btn-sm" onClick={preview} disabled={state === 'planning'}
        aria-label={`${state === 'error' ? '重试' : '标记完成'}：${t.name}`}>
        {state === 'planning' ? '…' : state === 'error' ? '重试' : '✓ 完成'}
      </button>
    </>
  )
}

// 新建任务：输入即预览（Enter）→ 确认；默认落「日常事务」list
export function NewTask({ writable, toast, onChanged }) {
  const [name, setName] = useState('')
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  if (!writable) {
    return <p className="hint">看板以只读启动：新建 / 完成任务需 <code>serve --enable-write</code>。</p>
  }
  async function preview(e) {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setErr(null)
    try {
      setPlan(await api.writePlanBody('task-create', { name: name.trim() }))
    } catch (x) {
      setErr(x)
    } finally {
      setBusy(false)
    }
  }
  async function confirm() {
    setBusy(true)
    try {
      await api.writeConfirm(plan.token)
      toast?.(`已新建「${plan.preview.name}」（ClickUp 回读通过）`)
      setPlan(null)
      setName('')
      onChanged?.()
    } catch (x) {
      setErr(x)
      setPlan(null)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="new-task">
      <form onSubmit={preview} className="new-task-row">
        <label className="visually-hidden" htmlFor="new-task-name">新建任务名</label>
        <input id="new-task-name" value={name} maxLength={200} disabled={busy || !!plan}
          onChange={(e) => setName(e.target.value)} placeholder="＋ 新建任务，回车预览" />
        {!plan && <button type="submit" className="btn-ghost btn-sm" disabled={busy || !name.trim()}>预览</button>}
      </form>
      {plan && (
        <div className="task-confirm" role="group" aria-label="确认新建任务">
          <span>{plan.preview.list} ←「{plan.preview.name}」</span>
          <code>{plan.cli.replace('python -m review_tool ', '')}</code>
          <button type="button" className="btn-primary btn-sm" onClick={confirm} disabled={busy}>
            {busy ? '写入中…' : '确认新建'}
          </button>
          <button type="button" className="btn-ghost btn-sm" onClick={() => setPlan(null)} disabled={busy}>取消</button>
        </div>
      )}
      {err && <ErrorBox error={err} />}
    </div>
  )
}

export function Task({ t, kind, writable, toast, onChanged, selectable, selected, onSelect }) {
  const pill =
    kind === 'overdue'
      ? { text: `逾期 ${t.due?.slice(5) || ''}`, cls: 'pill-red' }
      : kind === 'in_progress'
        ? { text: '进行中', cls: 'pill-blue' }
        : kind === 'done'
          ? { text: t.rebated_to ? `回拨→${t.rebated_to.slice(5)}` : t.closed_clock || '完成', cls: 'pill-green' }
          : { text: t.due ? `due ${t.due.slice(5)}` : '无截止', cls: '' }
  return (
    <li className={`task task-${kind}`}>
      {selectable ? (
        <input type="checkbox" className="task-sel" checked={selected} onChange={onSelect}
          aria-label={`加入批量完成：${t.name}`} />
      ) : <span className="dot" aria-hidden="true" />}
      <div className="task-body">
        <div className="title">{t.name}</div>
        <div className="sub">{t.list}</div>
      </div>
      <span className={`pill ${pill.cls}`}>{pill.text}</span>
      {kind !== 'done' && <TaskDone t={t} writable={writable} toast={toast} onChanged={onChanged} />}
    </li>
  )
}


// 批量完成：一次预览 + 一次性 token 对应一批（≤20 条），回显逐条等价 CLI；结果逐条以回读为准
function BatchBar({ selected, clear, toast, onChanged }) {
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [res, setRes] = useState(null)
  if (!selected.length && !plan && !res) return null
  async function preview() {
    setBusy(true)
    setErr(null)
    setRes(null)
    try {
      setPlan(await api.writePlanBody('task-batch', {
        items: selected.map((t) => ({ task_id: t.id, name: t.name })), status: 'complete',
      }))
    } catch (e) {
      setErr(e)
    } finally {
      setBusy(false)
    }
  }
  async function confirm() {
    setBusy(true)
    try {
      const r = await api.writeConfirm(plan.token)
      setPlan(null)
      setRes(r.result)
      toast?.(`批量完成 ${r.result.written} 条${r.result.failed.length ? `，${r.result.failed.length} 条失败` : ''}（以回读为准）`)
      clear()
      onChanged?.()
    } catch (e) {
      setErr(e)
      setPlan(null)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="batch-bar" role="region" aria-label="批量完成">
      {!plan ? (
        <div className="batch-row">
          <span>已选 {selected.length} 条</span>
          <button type="button" className="btn-ghost btn-sm" onClick={preview} disabled={busy || !selected.length}
            aria-label={`预览：批量完成 ${selected.length} 条任务`}>
            {busy ? '预览中…' : '① 预览批量完成'}
          </button>
          <button type="button" className="btn-ghost btn-sm" onClick={clear} disabled={busy}
            aria-label="清空批量选择">清空</button>
        </div>
      ) : (
        <>
          <p className="muted">将把 {plan.preview.count} 条任务改为 <code>{plan.preview.status}</code>（逐条写后回读）：</p>
          <ul className="batch-list">
            {plan.preview.items.map((x, i) => (
              <li key={x.task_id}><span>{x.name || x.task_id}</span> <code className="cli">{plan.preview.clis[i]}</code></li>
            ))}
          </ul>
          <div className="batch-row">
            <button type="button" className="btn-primary btn-sm" onClick={confirm} disabled={busy}
              aria-label={`确认：批量完成 ${plan.preview.count} 条任务`}>
              {busy ? '写入中…' : `② 确认完成 ${plan.preview.count} 条`}
            </button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => setPlan(null)} disabled={busy}
              aria-label="取消：批量完成">取消</button>
            <CopyButton text={plan.cli} toast={toast} label="复制 CLI" aria="复制 CLI：批量完成" />
          </div>
        </>
      )}
      {res?.failed?.length > 0 && (
        <div className="hint hint-warn" role="alert">
          {res.failed.length} 条未完成（可重新勾选重试）：
          <ul>{res.failed.map((f) => <li key={f.task_id}>{f.name || f.task_id}：{f.error}</li>)}</ul>
        </div>
      )}
      {err && <ErrorBox error={err} onRetry={selected.length ? preview : undefined} />}
    </div>
  )
}

export function TodoGroups({ lists, writable, toast, onChanged, query }) {
  const [sel, setSel] = useState({}) // id -> task
  const groups = groupTodos(lists)
  const toggle = (t) => setSel((s) => {
    const n = { ...s }
    if (n[t.id]) delete n[t.id]
    else if (Object.keys(n).length < 20) n[t.id] = t
    return n
  })
  const selected = Object.values(sel)
  return (
    <>
      {groups.map((g) => (
        // 搜索时全部展开，避免命中项藏在折叠组里
        <details key={g.id} className={`task-group tg-${g.id}`} open={g.open || !!query}>
          <summary>
            <span className="tg-name">{g.label}</span>
            <span className={`pill ${g.id === 'overdue' ? 'pill-red' : ''}`}>{g.items.length}</span>
          </summary>
          <ul className="task-list" aria-label={`${g.label}任务`}>
            {g.items.map(([t, k]) => (
              <Task key={t.id} t={t} kind={k} writable={writable} toast={toast} onChanged={onChanged}
                selectable={writable} selected={!!sel[t.id]} onSelect={() => toggle(t)} />
            ))}
          </ul>
        </details>
      ))}
      {writable && <BatchBar selected={selected} clear={() => setSel({})} toast={toast} onChanged={onChanged} />}
    </>
  )
}
