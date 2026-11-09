import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ActionsJsonEditor, parseActionsJson, parseExtraJson } from './ActionsJsonEditor'

describe('parseActionsJson', () => {
  it('接受含 actionId 的非空数组', () => {
    const r = parseActionsJson('[{"actionId":"act_1","groups":[{"sets":3}]}]')
    expect(r.ok).toBe(true)
    expect(r.actions).toHaveLength(1)
    expect(r.actions[0].actionId).toBe('act_1')
  })

  it('语法错误 / 非数组 / 空数组 / 缺 actionId 均失败', () => {
    expect(parseActionsJson('{').error).toMatch(/语法/)
    expect(parseActionsJson('{}').error).toMatch(/数组/)
    expect(parseActionsJson('[]').error).toMatch(/空/)
    expect(parseActionsJson('[{"name":"x"}]').error).toMatch(/actionId/)
    expect(parseActionsJson('').error).toMatch(/空/)
  })
})

describe('parseExtraJson', () => {
  it('空串省略；对象通过；数组/语法失败', () => {
    expect(parseExtraJson('').ok).toBe(true)
    expect(parseExtraJson('{"dayStr":"20261106"}').extra).toEqual({ dayStr: '20261106' })
    expect(parseExtraJson('[]').ok).toBe(false)
    expect(parseExtraJson('{').ok).toBe(false)
  })
})

describe('ActionsJsonEditor', () => {
  it('输入非法 JSON 时 aria-invalid 并显示错误', () => {
    const onChange = vi.fn()
    render(<ActionsJsonEditor value="{" onChange={onChange} id="t1" />)
    expect(screen.getByRole('alert').textContent).toMatch(/语法/)
    expect(screen.getByRole('textbox').getAttribute('aria-invalid')).toBe('true')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '[{"actionId":"a"}]' } })
    expect(onChange).toHaveBeenCalledWith('[{"actionId":"a"}]')
  })

  it('合法 JSON 显示已解析条数', () => {
    render(<ActionsJsonEditor value='[{"actionId":"a"},{"actionId":"b"}]' onChange={() => {}} id="t2" />)
    expect(screen.getByText('已解析 2 个动作')).toBeTruthy()
    expect(screen.getByRole('textbox').getAttribute('aria-invalid')).toBe('false')
  })
})
