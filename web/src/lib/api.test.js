import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, UNAUTHORIZED_EVENT, api, authKey, errText, verifyKey } from './api'

const jsonRes = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

const sentHeaders = (call = 0) => fetchMock.mock.calls[call][1].headers

describe('authKey 存储', () => {
  it('默认存 sessionStorage，remember 才进 localStorage', () => {
    authKey.set('k1')
    expect(sessionStorage.getItem('dailylumen.webKey')).toBe('k1')
    expect(localStorage.getItem('dailylumen.webKey')).toBeNull()
    expect(authKey.remembered()).toBe(false)
    authKey.set('k2', true)
    expect(sessionStorage.getItem('dailylumen.webKey')).toBeNull()
    expect(localStorage.getItem('dailylumen.webKey')).toBe('k2')
    expect(authKey.get()).toBe('k2')
    expect(authKey.remembered()).toBe(true)
    authKey.clear()
    expect(authKey.get()).toBe('')
  })
})

describe('request 带 key', () => {
  it('有 key 时带 Authorization: Bearer，且 key 不进 URL', async () => {
    authKey.set('secret-k')
    fetchMock.mockResolvedValue(jsonRes(200, { status: 'ok' }))
    await api.health()
    expect(sentHeaders().Authorization).toBe('Bearer secret-k')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/health')
    expect(fetchMock.mock.calls[0][0]).not.toContain('secret-k')
  })

  it('无 key 时不带 Authorization', async () => {
    fetchMock.mockResolvedValue(jsonRes(200, {}))
    await api.health()
    expect(sentHeaders().Authorization).toBeUndefined()
  })

  it('POST 带 JSON 体与 Content-Type', async () => {
    authKey.set('k')
    fetchMock.mockResolvedValue(jsonRes(200, { token: 't' }))
    await api.writeConfirm('tok-1')
    const [, opts] = fetchMock.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(opts.body)).toEqual({ token: 'tok-1' })
  })
})

describe('401 处理', () => {
  it('清 key、派发 unauthorized 事件并抛 ApiError', async () => {
    authKey.set('bad', true)
    const onEvt = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, onEvt)
    fetchMock.mockResolvedValue(jsonRes(401, { error: { code: 'unauthorized', message: 'x' } }))
    const err = await api.today('2026-11-06').catch((e) => e)
    window.removeEventListener(UNAUTHORIZED_EVENT, onEvt)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(401)
    expect(err.code).toBe('unauthorized')
    expect(onEvt).toHaveBeenCalledTimes(1)
    expect(authKey.get()).toBe('')
  })

  it('非 401 错误保留服务端错误体，不清 key', async () => {
    authKey.set('k')
    fetchMock.mockResolvedValue(jsonRes(409, { error: { code: 'token_invalid', message: '已失效' } }))
    const err = await api.writeConfirm('t').catch((e) => e)
    expect(err.code).toBe('token_invalid')
    expect(errText(err)).toBe('确认已失效或已使用，请重新预览')
    expect(authKey.get()).toBe('k')
  })

  it('网络失败 → network', async () => {
    fetchMock.mockRejectedValue(new TypeError('failed'))
    const err = await api.health().catch((e) => e)
    expect(err.code).toBe('network')
  })
})

describe('verifyKey', () => {
  it('用候选 key 请求 health，不写存储、不派发事件', async () => {
    const onEvt = vi.fn()
    window.addEventListener(UNAUTHORIZED_EVENT, onEvt)
    fetchMock.mockResolvedValueOnce(jsonRes(401, {})).mockResolvedValueOnce(jsonRes(200, {}))
    expect(await verifyKey('wrong')).toBe(false)
    expect(await verifyKey('right')).toBe(true)
    window.removeEventListener(UNAUTHORIZED_EVENT, onEvt)
    expect(sentHeaders(1).Authorization).toBe('Bearer right')
    expect(authKey.get()).toBe('')
    expect(onEvt).not.toHaveBeenCalled()
  })
})

describe('blobUrl', () => {
  it('带 key 取二进制并返回 object URL', async () => {
    authKey.set('k')
    URL.createObjectURL = vi.fn(() => 'blob:x')
    fetchMock.mockResolvedValue(new Response('<svg/>', { status: 200 }))
    expect(await api.blobUrl(api.chartPath('trends'))).toBe('blob:x')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/charts/trends')
    expect(sentHeaders().Authorization).toBe('Bearer k')
  })
})
