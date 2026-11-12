// API 封装：统一错误体 {error:{code,message}}。
// W14：访问密钥由用户在登录页输入，只存浏览器存储（默认 sessionStorage，勾选「记住」才进
// localStorage），每次请求放 Authorization 头；绝不进 bundle、URL 查询串或日志。
export class ApiError extends Error {
  constructor(status, code, message) {
    super(message)
    this.status = status
    this.code = code
  }
}

const KEY_NAME = 'dailylumen.webKey'
export const UNAUTHORIZED_EVENT = 'dailylumen:unauthorized'

const store = (kind) => {
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

export const authKey = {
  get() {
    return store('session')?.getItem(KEY_NAME) || store('local')?.getItem(KEY_NAME) || ''
  },
  set(key, remember = false) {
    authKey.clear()
    store(remember ? 'local' : 'session')?.setItem(KEY_NAME, key)
  },
  clear() {
    store('session')?.removeItem(KEY_NAME)
    store('local')?.removeItem(KEY_NAME)
  },
  remembered() {
    return !!store('local')?.getItem(KEY_NAME)
  },
}

const authHeaders = (key) => (key ? { Authorization: `Bearer ${key}` } : {})

async function request(path, { method = 'GET', signal, body } = {}) {
  let res
  const headers = { Accept: 'application/json', ...authHeaders(authKey.get()) }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  try {
    res = await fetch(path, {
      method, signal, headers, body: body === undefined ? undefined : JSON.stringify(body),
    })
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
    // 仅看板访问密钥失败才清 key / 回登录；练练 upstream_auth 等同为 401，勿误伤
    if (res.status === 401 && code === 'unauthorized') {
      authKey.clear()
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
      throw new ApiError(401, 'unauthorized', '访问密钥无效，请重新输入')
    }
    throw new ApiError(res.status, code, message)
  }
  return res
}

const json = async (path, opts) => (await request(path, opts)).json()

// 带鉴权取二进制 → object URL（<img> / 下载链接无法带请求头）；调用方负责 revoke
const blobUrl = async (path, opts) => URL.createObjectURL(await (await request(path, opts)).blob())

// 登录页校验：用待验证的 key 直接请求 health，不写存储、不触发 401 事件
export async function verifyKey(key) {
  let res
  try {
    res = await fetch('/api/health', { headers: { Accept: 'application/json', ...authHeaders(key) } })
  } catch {
    throw new ApiError(0, 'network', '无法连接本机服务，请确认 serve 正在运行')
  }
  if (res.status === 401) return false
  if (!res.ok) throw new ApiError(res.status, `http_${res.status}`, `请求失败（${res.status}）`)
  return true
}

// 下载：先带 key 取 blob，再用临时 <a download> 触发保存
export async function downloadFile(path, filename) {
  const url = await blobUrl(path)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || ''
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

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
  // D2：今日训练日只读状态（练练旁证 + md 是否已同步）
  trainingDay: (date, o) => json(`/api/training-day${qs({ date })}`, o),
  steward: (slot, params, o) => json(`/api/steward/${slot}${qs(params)}`, o),
  aiStatus: (o) => json('/api/ai/status', o),
  aiReviewPreview: (date, o) =>
    json(`/api/ai/review-preview${qs({ date })}`, { ...o, method: 'POST' }),
  // W9 写操作两段式：plan（预览 + 一次性 token）→ confirm（执行预览过的内容）
  writePlan: (action, params, o) =>
    json(`/api/write/${action}/plan${qs(params)}`, { ...o, method: 'POST' }),
  // W10：带 JSON 体的 plan（建任务 / 改状态 / ingest）
  writePlanBody: (action, body, o) =>
    json(`/api/write/${action}/plan`, { ...o, method: 'POST', body }),
  writeConfirm: (token, o) => json('/api/write/confirm', { ...o, method: 'POST', body: { token } }),
  // W11：收件箱待处理截图清单（只读；写接口未挂载时 404）
  inbox: (o) => json('/api/write/inbox', o),
  // W12：收件箱缩略图（服务端只认收件箱顶层文件名，防穿越）；W14 起经 blob URL 带 key
  inboxImagePath: (name) => `/api/write/inbox/image${qs({ name })}`,
  chartPath: (kind) => `/api/charts/${kind}`,
  chartJsonPath: (kind) => `/api/charts/${kind}.json`,
  chartJson: (kind, o) => json(`/api/charts/${kind}.json`, o),
  weekMdPath: (year, week) => `/api/reports/week.md${qs({ year, week })}`,
  monthMdPath: (month) => `/api/reports/month.md${qs({ month })}`,
  blobUrl,
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
    upstream_auth: '上游拒绝访问：凭据失效或权限不足（ClickUp / 练练）',
    upstream_unreachable: '上游网络不可达或超时，稍后再试',
    rate_limited: '上游限流（每分钟请求数超限），请稍后再刷新',
    writeback_failed: '练练写回失败，请核对参数后重新预览',
    skill_update_required: '练练要求更新 skill / 客户端后再写回',
    mode_gated: '当前 mode 不调 DeepSeek：读图 / AI 评价请改 local/.env 的 DAILYLUMEN_LLM_MODE=deepseek',
    image_too_large: '图片太大（单张上限 8 MB），请裁剪或压缩后重试',
    invalid_image: '只支持 PNG / JPEG / WebP 截图',
    too_many_images: '一次最多 6 张截图',
    md_missing: '找不到该日复盘 md，请先从模板建当日复盘文件',
    stale_plan: '复盘 md 在预览后被改动，请重新预览再确认',
    token_invalid: '确认已失效或已使用，请重新预览',
    token_expired: '确认已过期（5 分钟），请重新预览',
    unauthorized: '访问密钥无效，请重新输入',
  }
  return map[e.code] || e.message || '未知错误'
}
