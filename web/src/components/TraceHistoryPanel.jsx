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
    <div className="flex flex-col gap-4 h-full max-h-full">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex flex-col">
          <h2 className="text-sm font-bold font-heading text-slate-200 uppercase tracking-wider">{title}</h2>
          <span className="text-xs text-slate-500 font-mono mt-0.5">
            PAGE {page} / {totalPages} • TOTAL {total}
          </span>
        </div>
        <div className="flex gap-1">
          <button
            type="button"
            className="p-1 px-2.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors font-mono text-xs"
            onClick={() => onPageChange(page - 1)}
            disabled={!canPrev}
          >
            ←
          </button>
          <button
            type="button"
            className="p-1 px-2.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors font-mono text-xs"
            onClick={() => onPageChange(page + 1)}
            disabled={!canNext}
          >
            →
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2 pr-1">
        {records.length ? (
          records.map((record) => {
            const plan = record.trace?.plan || {}
            const decision = (plan.decision || 'WAIT').toUpperCase()
            const asset = plan.asset || '--'
            const isSelected = record.id === selectedId

            // Color coding for decision
            let decisionColor = 'text-slate-400'
            let borderColor = 'border-slate-800'

            if (isSelected) {
              borderColor = 'border-primary'
            }

            if (decision === 'LONG') decisionColor = 'text-success'
            else if (decision === 'SHORT') decisionColor = 'text-danger'
            else if (decision.includes('CLOSE')) decisionColor = 'text-accent'

            return (
              <div
                key={record.id}
                className={`
                  relative p-3 rounded border transition-all cursor-pointer group
                  ${isSelected ? 'bg-primary/5 border-primary shadow-[0_0_10px_rgba(var(--primary),0.1)]' : 'bg-slate-900/50 border-slate-800 hover:border-slate-600 hover:bg-slate-800/50'}
                `}
                onClick={() => onSelect(record.id)}
              >
                {isSelected && <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary rounded-l" />}

                <div className="flex justify-between items-start mb-2">
                  <span className={`font-mono text-[10px] ${isSelected ? 'text-primary' : 'text-slate-500 group-hover:text-slate-400'}`}>
                    #{record.id}
                  </span>
                  <span className="font-mono text-[10px] text-slate-500">
                    {new Date(record.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span className={`text-sm font-bold font-heading ${decisionColor}`}>
                    {decision}
                  </span>
                  <span className="text-xs font-mono text-slate-300 bg-slate-800/50 px-1.5 py-0.5 rounded">
                    {asset}
                  </span>
                </div>

                <div className="mt-2 flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                  <span className="bg-slate-950/30 px-1 rounded border border-slate-800/50">
                    Evts: {record.trace?.trace_events?.length || 0}
                  </span>
                  {record.trace?.tool_calls?.length > 0 && (
                    <span className="bg-slate-950/30 px-1 rounded border border-slate-800/50 text-slate-400">
                      Tools: {record.trace.tool_calls.length}
                    </span>
                  )}
                </div>
              </div>
            )
          })
        ) : (
          <div className="text-center py-12 text-slate-600 font-mono text-xs border border-dashed border-slate-800 rounded">
            &gt; No history logs found.
          </div>
        )}
      </div>
    </div>
  )
}

export default TraceHistoryPanel
