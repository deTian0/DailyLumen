import { describe, expect, it } from 'vitest'
import { toProseSource } from './prose'

describe('toProseSource', () => {
  it('把 ==== 横幅 + 标题行转成 # 标题', () => {
    const src = toProseSource('====================================================\nDailyLumen 晨间 brief\n====================================================\n')
    expect(src).toContain('# DailyLumen 晨间 brief')
    expect(src).not.toContain('====')
  })

  it('把 ---- 分段转成 ##', () => {
    const src = toProseSource('---- 1. 昨日四维 + 熔断 ----\n  熔断: 无')
    expect(src).toContain('## 昨日四维 + 熔断')
    expect(src).toContain('- 熔断: 无')
  })

  it('source= 行变成引用代码', () => {
    const src = toProseSource('  source=reports.steward')
    expect(src).toContain('> `source=reports.steward`')
  })

  it('已是 Markdown 时透传', () => {
    const md = '# 周报\n\n**系统分** 6'
    expect(toProseSource(md)).toBe(md)
  })

  it('[方括号] 段标题 → ##', () => {
    expect(toProseSource('[第三方集成]\n  OK')).toContain('## 第三方集成')
  })
})
