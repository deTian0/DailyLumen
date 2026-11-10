import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Card, ErrorBox, Loading, Prose, Stat, StatusMark } from '../components/Common'

const STATUS_LABEL = { ok: '正常', warn: '注意', crit: '异常' }

export function DoctorCards({ summary }) {
  if (!summary?.items?.length) return null
  return (
    <div className="doctor-grid" role="list" aria-label="体检分项">
      {summary.items.map((it) => (
        <article
          key={it.id}
          className={`doctor-card doctor-card-${it.status}`}
          role="listitem"
          data-status={it.status}
          data-id={it.id}
        >
          <header className="doctor-card-head">
            <span className="doctor-card-icon">
              <StatusMark tone={it.status} label={STATUS_LABEL[it.status] || it.status} />
            </span>
            <h3 className="doctor-card-title">{it.title}</h3>
            {it.count != null && (
              <span className="doctor-card-count">{it.count}</span>
            )}
          </header>
          <p className="doctor-card-summary">{it.summary}</p>
          {it.advice ? <p className="doctor-card-advice">{it.advice}</p> : null}
        </article>
      ))}
    </div>
  )
}

export default function Doctor() {
  const doc = useAsync((signal) => api.doctor({ signal }), [])
  const fuse = useAsync((signal) => api.fuse(undefined, { signal }), [])
  const errs = useAsync((signal) => api.integrationErrors({ signal }), [])
  const last = errs.data?.last
  const summary = doc.data?.summary
  const healthy = doc.data?.healthy
  return (
    <>
      <header className="topbar">
        <div>
          <h1>体检</h1>
          <p className="subtitle">与 CLI `doctor` / `fuse` 同源，只读</p>
        </div>
        <div className="top-actions">
          <button type="button" className="btn-ghost" onClick={() => { doc.reload(); fuse.reload(); errs.reload() }}>
            重新体检
          </button>
        </div>
      </header>

      <section className="stats" aria-label="体检摘要">
        <Stat label="数据健康" value={doc.data ? (healthy ? '健康' : '有问题') : '…'}
          tone={doc.data ? (healthy ? 'green' : 'red') : undefined} />
        <Stat label="熔断" value={fuse.data ? (fuse.data.active ? '已触发' : '未触发') : '…'}
          tone={fuse.data ? (fuse.data.active ? 'red' : 'green') : undefined} />
        <Stat label="最近集成失败" value={last ? last.integration : errs.data ? '无' : '…'}
          sub={last ? `${last.error_kind} · ${last.ts?.slice(0, 16).replace('T', ' ')}` : undefined}
          tone={last ? 'amber' : 'green'} />
      </section>

      {last && (
        <div className="banner banner-warn" role="status">
          {last.error_summary}
        </div>
      )}

      <Card title="体检报告">
        {doc.error ? <ErrorBox error={doc.error} onRetry={doc.reload} />
          : !doc.data ? <Loading label="正在体检…" />
          : (
            <>
              <div
                className={`doctor-banner doctor-banner-${healthy ? 'ok' : 'warn'}`}
                role="status"
              >
                {summary?.conclusion
                  || (healthy ? '数据健康' : '存在待处理项，见上方标记')}
              </div>
              <DoctorCards summary={summary} />
              <details className="doctor-raw">
                <summary>查看原文</summary>
                <Prose source={doc.data.text} />
              </details>
            </>
          )}
      </Card>
      <Card title="熔断判定">
        {fuse.error ? <ErrorBox error={fuse.error} onRetry={fuse.reload} />
          : !fuse.data ? <Loading />
          : <Prose source={fuse.data.text} />}
      </Card>
    </>
  )
}

export { STATUS_LABEL }
