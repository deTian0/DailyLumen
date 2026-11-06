// W13：今日页纯逻辑（无 React），便于单测。
import { todayStr } from './api'

export const WD = ['一', '二', '三', '四', '五', '六', '日']

export function weekDays(day) {
  const d = new Date(`${day}T00:00:00`)
  const idx = (d.getDay() + 6) % 7
  const mon = new Date(d)
  mon.setDate(d.getDate() - idx)
  return Array.from({ length: 7 }, (_, i) => {
    const x = new Date(mon)
    x.setDate(mon.getDate() + i)
    return todayStr(x)
  })
}

// W12：今日待办分组（逾期 / 今日到期·进行中 / 无截止）；分组只按 ClickUp 已给的 kind + due 字段，
// 不在前端另做归日（归日口径单源在后端 clickup_queries）。逾期默认折叠并显示条数。
export function groupTodos(lists) {
  return [
    { id: 'overdue', label: '逾期', items: lists.overdue.map((t) => [t, 'overdue']), open: false },
    {
      id: 'due', label: '今日到期 · 进行中',
      items: [...lists.in_progress.map((t) => [t, 'in_progress']),
        ...lists.open.filter((t) => t.due).map((t) => [t, 'open'])],
      open: true,
    },
    { id: 'nodue', label: '无截止', items: lists.open.filter((t) => !t.due).map((t) => [t, 'open']), open: true },
  ].filter((g) => g.items.length)
}
