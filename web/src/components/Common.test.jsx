import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Empty, StatusMark } from './Common'

describe('StatusMark', () => {
  it('渲染点 + 短标签并映射 tone', () => {
    const { container } = render(<StatusMark tone="crit" label="异常" />)
    expect(container.querySelector('.status-crit')).toBeTruthy()
    expect(container.querySelector('.dot-crit')).toBeTruthy()
    expect(screen.getByText('异常')).toBeTruthy()
  })

  it('green 别名落到 ok', () => {
    const { container } = render(<StatusMark tone="green" label="完成" />)
    expect(container.querySelector('.status-ok')).toBeTruthy()
  })
})

describe('Empty', () => {
  it('一句说明 + 可选 CTA', () => {
    const onClear = vi.fn()
    render(
      <Empty action={<button type="button" onClick={onClear}>清除搜索</button>}>
        没有匹配的任务
      </Empty>,
    )
    expect(screen.getByText('没有匹配的任务')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '清除搜索' }))
    expect(onClear).toHaveBeenCalledTimes(1)
  })
})
