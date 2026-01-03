function TraceHistoryPanel({
  records,
  selectedId,
  onSelect,
  page,
  pageSize,
  total,
  onPageChange,
  title = '历史记录',
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const canPrev = page > 1
  const canNext = page < totalPages

  return (
    <section className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '100%' }}>
      <div className="panel-header" style={{ marginBottom: '12px' }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <h2 style={{ fontSize: '16px' }}>{title}</h2>
          <span className="muted" style={{ fontSize: '11px' }}>
            {page} / {totalPages} 页 (共 {total})
          </span>
        </div>
        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '4px 8px', fontSize: '12px' }}
            onClick={() => onPageChange(page - 1)}
            disabled={!canPrev}
          >
            ←
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '4px 8px', fontSize: '12px' }}
            onClick={() => onPageChange(page + 1)}
            disabled={!canNext}
          >
            →
          </button>
        </div>
      </div>
      <div className="history-list">
        {records.length ? (
          records.map((record) => {
            const plan = record.trace?.plan || {}
            const decision = plan.decision || 'WAIT'
            const asset = plan.asset || '--'
            return (
              <div
                key={record.id}
                className={`history-item ${record.id === selectedId ? 'active' : ''}`}
                onClick={() => onSelect(record.id)}
              >
                <div className="history-item-header">
                  <span className="history-id">Test #{record.id}</span>
                  <span className="history-time">{new Date(record.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                  {decision} {asset}
                </div>
                <span className="history-time" style={{ marginTop: '4px' }}>Events: {record.trace?.trace_events?.length || 0}</span>
              </div>
            )
          })
        ) : (
          <p className="muted">暂无历史记录。</p>
        )}
      </div>
    </section>
  )
}

export default TraceHistoryPanel
