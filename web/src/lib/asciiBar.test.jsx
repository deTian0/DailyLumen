import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { barPercent, parseWholeBar, splitAsciiBars } from './asciiBar'
import { Markdown } from './markdown'

describe('parseWholeBar', () => {
  it('识别周报 _md_bar █/░（宽 10）', () => {
    const b = parseWholeBar('███████░░░')
    expect(b).toMatchObject({ filled: 7, total: 10, now: 7, max: 10, kind: 'md' })
  })

  it('全满 / 全空', () => {
    expect(parseWholeBar('██████████')).toMatchObject({ filled: 10, total: 10 })
    expect(parseWholeBar('░░░░░░░░░░')).toMatchObject({ filled: 0, total: 10 })
  })

  it('兼容 CLI [█·]', () => {
    expect(parseWholeBar('[█████·····]')).toMatchObject({
      filled: 5, total: 10, kind: 'cli',
    })
  })

  it('不认识的格式 → null', () => {
    expect(parseWholeBar('只有文字')).toBeNull()
    expect(parseWholeBar('█')).toBeNull()
    expect(parseWholeBar('—')).toBeNull()
    expect(parseWholeBar('混排█文字░')).toBeNull()
  })
})

describe('splitAsciiBars + 分数', () => {
  it('标签 + 条 + 5/7 → aria now=5 max=7', () => {
    const parts = splitAsciiBars('依从 ██████░░░░ 5/7')
    expect(parts[0]).toEqual({ type: 'text', text: '依从 ' })
    expect(parts[1]).toMatchObject({
      type: 'bar', filled: 6, total: 10, now: 5, max: 7, label: '5/7',
    })
    expect(parts.filter((p) => p.type === 'bar')).toHaveLength(1)
  })

  it('barPercent 按 filled/total', () => {
    expect(barPercent({ filled: 5, total: 10 })).toBe(50)
  })
})

describe('Markdown 表细胞 → progressbar', () => {
  it('标准 ████░░ 产出 role=progressbar', () => {
    const md = `| 维度 | 分 | 条 |
| --- | --- | --- |
| 系统 | **6.5** | ███████░░░ |
`
    render(<Markdown source={md} />)
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('7')
    expect(bar.getAttribute('aria-valuemax')).toBe('10')
    expect(bar.getAttribute('aria-valuemin')).toBe('0')
  })

  it('含分数行 aria-valuenow=5 / max=7', () => {
    render(<Markdown source={'完成度 ██████░░░░ 5/7\n'} />)
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('5')
    expect(bar.getAttribute('aria-valuemax')).toBe('7')
  })

  it('不认识的格式按原样显示', () => {
    render(<Markdown source={'只有一个█不够\n'} />)
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.getByText(/只有一个█不够/)).toBeTruthy()
  })
})
