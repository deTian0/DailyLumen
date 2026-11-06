import { useState } from 'react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Card, ErrorBox, Loading, Stat } from '../components/Common'
import { EChart } from '../components/EChart'
import { buildChartOption } from '../lib/chartOption'

const CHARTS = [
  { id: 'trends', label: '四维趋势' },
  { id: 'body', label: '体征' },
  { id: 'training', label: '训练' },
  { id: 'nutrition', label: '营养' },
]
const DIM_NAME = {
  health_score: '健康',
  work_score: '工作',
  learn_score: '学习',
  life_score: '生活',
  system_score: '系统',
}

// W16：前端自绘图（ECharts 吃 /api/charts/{kind}.json，与 SVG 同源）
function ChartView({ kind, label }) {
  const [st, setSt] = useState({ kind, status: 'loading', n: 0 })
  const cur = st.kind === kind ? st : { kind, status: 'loading', n: 0 }
  if (cur !== st) setSt(cur)
  const data = useAsync((signal) => api.chartJson(kind, { signal }), [kind, cur.n])
  const option = data.data ? buildChartOption(data.data) : null
  return (
    <div className="chart-well" aria-busy={cur.status === 'loading'}>
      {data.error ? (
        <div className="state state-error" role="alert">
          <div>{label}图生成失败（可能该类数据为空或库未就绪）</div>
          <button type="button" className="btn-ghost"
            onClick={() => setSt({ kind, status: 'loading', n: cur.n + 1 })}>重试</button>
        </div>
      ) : !option ? (
        <Loading label={`正在生成${label}图…`} />
      ) : (
        <EChart option={option} ariaLabel={`${label}图表`} />
      )}
    </div>
  )
}

export default function Analytics() {
  const [kind, setKind] = useState('trends')
  const stats = useAsync((signal) => api.stats({ signal }), [])
  const s = stats.data
  return (
    <>
      <header className="topbar">
        <div>
          <h1>分析</h1>
          <p className="subtitle">数据概览与图表（与 CLI `stats` / `chart` 同源）</p>
        </div>
      </header>
      {stats.error ? (
        <ErrorBox error={stats.error} onRetry={stats.reload} />
      ) : !s ? (
        <Loading />
      ) : (
        <>
          <section className="stats" aria-label="数据概览">
            <Stat label="入库天数" value={s.days} sub={`最新 ${s.latest_date}`} />
            <Stat label="打卡记录" value={s.tracks} sub={`习惯日志 ${s.habit_logs}`} />
            <Stat label="历史缺口" value={`${s.history_gap_days} 天`} sub={`${s.history_gaps.length} 段`}
              tone={s.history_gap_days ? 'amber' : 'green'} />
            <Stat label="库" value={`${s.db_size_kb} KB`} sub={`schema v${s.schema_version}`} />
          </section>
          <Card title="四维分布" meta="全量历史">
            <div className="md-table" tabIndex={0} role="region" aria-label="四维分布表">
              <table>
                <thead>
                  <tr>
                    <th scope="col">维度</th><th scope="col">天数</th><th scope="col">均值</th>
                    <th scope="col">中位</th><th scope="col">最低</th><th scope="col">最高</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(s.scores?.dims || {}).map(([k, d]) => (
                    <tr key={k}>
                      <th scope="row">{DIM_NAME[k] || k}</th>
                      <td>{d.n}</td><td>{d.avg}</td><td>{d.median}</td><td>{d.min}</td><td>{d.max}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <Card title="图表" className="chart-card"
        actions={
          <div className="seg" role="group" aria-label="图表类型">
            {CHARTS.map((c) => (
              <button key={c.id} type="button" className={`seg-btn ${kind === c.id ? 'active' : ''}`}
                aria-pressed={kind === c.id} onClick={() => setKind(c.id)}>
                {c.label}
              </button>
            ))}
          </div>
        }>
        <ChartView kind={kind} label={CHARTS.find((c) => c.id === kind).label} />
      </Card>
    </>
  )
}
