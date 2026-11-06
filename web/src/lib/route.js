// 轻量 hash 路由工具：#/reports?tab=ctx → 页面 id 与查询参数。
export const hashPage = () => window.location.hash.replace(/^#\/?/, '').split('?')[0]

export const hashQuery = (key) =>
  new URLSearchParams(window.location.hash.split('?')[1] || '').get(key)
