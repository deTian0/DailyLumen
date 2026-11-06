import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { Card, ErrorBox, Loading, Stat } from '../components/Common'

export default function Doctor() {
  const doc = useAsync((signal) => api.doctor({ signal }), [])
  const fuse = useAsync((signal) => api.fuse(undefined, { signal }), [])
  const errs = useAsync((signal) => api.integrationErrors({ signal }), [])
  const last = errs.data?.last
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
        <Stat label="数据健康" value={doc.data ? (doc.data.healthy ? '健康' : '有问题') : '…'}
          tone={doc.data ? (doc.data.healthy ? 'green' : 'red') : undefined} />
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
          : <pre className="plain">{doc.data.text}</pre>}
      </Card>
      <Card title="熔断判定">
        {fuse.error ? <ErrorBox error={fuse.error} onRetry={fuse.reload} />
          : !fuse.data ? <Loading />
          : <pre className="plain">{fuse.data.text}</pre>}
      </Card>
    </>
  )
}
