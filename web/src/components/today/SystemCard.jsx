// W13 从 Today.jsx 拆出
import { Card, Loading, StatusMark } from '../Common'

const INTEG = [
  { id: 'clickup', label: 'ClickUp' },
  { id: 'keepstrong', label: '练练健身' },
  { id: 'deepseek', label: 'DeepSeek' },
]
const MODE = { workbuddy: 'WorkBuddy 宿主', deepseek: 'DeepSeek 直连' }

// 系统状态：只展示 /api/health 的白名单字段（mode / 三集成开关），不推导任何业务结论
export function SystemCard({ health }) {
  return (
    <Card title="系统状态" meta="来自 /api/health">
      {!health ? (
        <Loading />
      ) : (
        <dl className="kv">
          <div>
            <dt>复盘模式</dt>
            <dd>{MODE[health.llm_mode] || health.llm_mode}</dd>
          </div>
          {INTEG.map((i) => (
            <div key={i.id}>
              <dt>{i.label}</dt>
              <dd>
                <StatusMark
                  tone={health.integrations?.[i.id] ? 'ok' : 'muted'}
                  label={health.integrations?.[i.id] ? '已启用' : '未启用'}
                />
              </dd>
            </div>
          ))}
          <div>
            <dt>AI 一键功能</dt>
            <dd>
              <StatusMark
                tone={health.ai_enabled ? 'ok' : 'muted'}
                label={health.ai_enabled ? '可用' : '不可用（需 deepseek 模式且集成开启）'}
              />
            </dd>
          </div>
        </dl>
      )}
    </Card>
  )
}
