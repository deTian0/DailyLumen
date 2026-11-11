import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authKey } from '../lib/api'
import { ThemeProvider } from '../lib/ThemeContext'
import Login from './Login'

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

const renderLogin = (ui) => render(<ThemeProvider>{ui}</ThemeProvider>)
const typeKey = (v) => fireEvent.change(screen.getByLabelText('访问密钥'), { target: { value: v } })
const submit = () => fireEvent.click(screen.getByRole('button', { name: '进入看板' }))

describe('Login', () => {
  it('错 key：提示并不保存', async () => {
    fetchMock.mockResolvedValue(new Response('{}', { status: 401 }))
    const onSuccess = vi.fn()
    renderLogin(<Login onSuccess={onSuccess} />)
    typeKey('wrong')
    submit()
    expect(await screen.findByText(/密钥不正确/)).toBeTruthy()
    expect(onSuccess).not.toHaveBeenCalled()
    expect(authKey.get()).toBe('')
  })

  it('对 key：默认存 sessionStorage 并回调', async () => {
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))
    const onSuccess = vi.fn()
    renderLogin(<Login onSuccess={onSuccess} />)
    typeKey('  right  ')
    submit()
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(sessionStorage.getItem('dailylumen.webKey')).toBe('right')
    expect(localStorage.getItem('dailylumen.webKey')).toBeNull()
  })

  it('勾选记住：存 localStorage', async () => {
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))
    renderLogin(<Login onSuccess={() => {}} />)
    typeKey('right')
    fireEvent.click(screen.getByRole('checkbox'))
    submit()
    await waitFor(() => expect(localStorage.getItem('dailylumen.webKey')).toBe('right'))
  })

  it('空输入不发请求；expired 显示失效提示', () => {
    renderLogin(<Login expired />)
    expect(screen.getByText(/密钥已失效/)).toBeTruthy()
    submit()
    expect(screen.getByText('请输入访问密钥')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('登录页有三套主题切换', () => {
    renderLogin(<Login />)
    expect(screen.getByRole('group', { name: '主题' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '青绿' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '暗色' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Omni' })).toBeTruthy()
  })
})
