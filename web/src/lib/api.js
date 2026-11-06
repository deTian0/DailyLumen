// API 封装：统一错误体 {error:{code,message}}；不在前端存任何凭据。
export class ApiError extends Error {
  constructor(status, code, message) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request(path, { method = 'GET', signal } = {}) {
  let res
  try {
    res = await fetch(path, { method, signal, headers: { Accept: 'application/json' } })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError(0, 'network', '无法连接本机服务，请确认 serve 正在运行')
  }
  if (!res.ok) {
    let code = `http_${res.status}`
    let message = `请求失败（${res.status}）`
    try {
      const body = await res.json()
      if (body && body.error) {
        code = body.error.code || code
        message = body.error.message || message
      }
    } catch {
      /* 非 JSON 错误体：保留默认文案 */
    }
    throw new ApiError(res.status, code, message)
  }
  return res
}

const json = async (path, opts) => (await request(path, opts)).json()

const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  health: (o) => json('/api/health', o),
  today: (date, o) => json(`/api/today${qs({ date })}`, o),
  refreshToday: (date, o) => json(`/api/today/refresh${qs({ date })}`, { ...o, method: 'POST' }),
  done: (date, end, o) => json(`/api/clickup/done${qs({ date, end })}`, o),
  weeks: (o) => json('/api/reports/weeks', o),
  week: (year, week, o) => json(`/api/reports/week${qs({ year, week })}`, o),
  months: (o) => json('/api/reports/months', o),
  month: (month, o) => json(`/api/reports/month${qs({ month })}`, o),
  aiContext: (date, o) => json(`/api/reports/ai-context${qs({ date })}`, o),
  stats: (o) => json('/api/stats', o),
  doctor: (o) => json('/api/doctor', o),
  fuse: (month, o) => json(`/api/fuse${qs({ month })}`, o),
  integrationErrors: (o) => json('/api/integrations/errors', o),
  life: (domain, params, o) => json(`/api/${domain}${qs(params)}`, o),
  steward: (slot, params, o) => json(`/api/steward/${slot}${qs(params)}`, o),
  chartUrl: (kind) => `/api/charts/${kind}`,
  weekMdUrl: (year, week) => `/api/reports/week.md${qs({ year, week })}`,
  monthMdUrl: (month) => `/api/reports/month.md${qs({ month })}`,
  chartSvg: async (kind, o) => (await request(`/api/charts/${kind}`, o)).text(),
}

export function todayStr(d = new Date()) {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

export function errText(e) {
  if (!e) return ''
  const map = {
    db_missing: '数据库尚未建立，请先在命令行执行 ingest',
    network: '无法连接本机服务，请确认 serve 正在运行',
    integration_disabled: 'ClickUp 集成未启用（local/.env 中关闭），今日数据不可用',
    credentials_missing: 'ClickUp 未配置凭据，今日数据不可用（在 local/.env 配置后重启 serve）',
    upstream_auth: 'ClickUp 拒绝访问：token 失效或权限不足',
    upstream_unreachable: 'ClickUp 网络不可达或超时，稍后再试',
  }
  return map[e.code] || e.message || '未知错误'
}
