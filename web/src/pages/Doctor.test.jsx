import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DoctorCards } from './Doctor'

const sample = {
  healthy: false,
  conclusion: '存在待处理项，见上方标记',
  items: [
    {
      id: 'rows', title: '复盘记录', status: 'crit', count: 0,
      summary: '0 条', advice: '库为空：先 ingest 标准复盘 md', affects_health: true,
    },
    {
      id: 'freshness', title: '新鲜度', status: 'warn', count: 5,
      summary: '最新 2026-09-01（距今 5 天）', advice: '建议补录最近复盘', affects_health: false,
    },
    {
      id: 'schema', title: 'schema 版本', status: 'ok', count: 11,
      summary: 'v11', advice: null, affects_health: true,
    },
  ],
}

describe('DoctorCards', () => {
  it('渲染分项卡片与状态 icon', () => {
    render(<DoctorCards summary={sample} />)
    expect(screen.getByRole('list', { name: '体检分项' })).toBeTruthy()
    expect(screen.getByText('复盘记录')).toBeTruthy()
    expect(screen.getByText('新鲜度')).toBeTruthy()
    expect(screen.getByText('schema 版本')).toBeTruthy()
    const crit = document.querySelector('[data-id="rows"]')
    expect(crit?.getAttribute('data-status')).toBe('crit')
    expect(crit?.textContent).toContain('❌')
    expect(crit?.textContent).toContain('库为空')
  })

  it('原文折叠由页面 details 承担（卡片不含全文）', () => {
    const { container } = render(
      <>
        <DoctorCards summary={sample} />
        <details className="doctor-raw">
          <summary>查看原文</summary>
          <pre>假原文</pre>
        </details>
      </>,
    )
    expect(container.querySelector('details.doctor-raw')).toBeTruthy()
    expect(screen.getByText('查看原文')).toBeTruthy()
  })
})
