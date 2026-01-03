import { Target, TrendingUp, ShieldAlert, CheckCircle, Terminal, FileWarning } from 'lucide-react';
import TraceHistoryPanel from '../components/TraceHistoryPanel.jsx'
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';

function FocusPage({
  execution,
  plan,
  risk,
  toolCalls,
  riskLogs,
  history,
  selectedTraceId,
  onSelectTrace,
  historyPage,
  historyPageSize,
  historyTotal,
  onPageChange,
}) {
  return (
    <div className="min-h-screen bg-background pt-20 pb-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Sidebar */}
        <div className="lg:col-span-3">
          <Card className="h-full min-h-[500px]">
            <TraceHistoryPanel
              records={history}
              selectedId={selectedTraceId}
              onSelect={onSelectTrace}
              page={historyPage}
              pageSize={historyPageSize}
              total={historyTotal}
              onPageChange={onPageChange}
              title="执行历史"
            />
          </Card>
        </div>

        <div className="lg:col-span-9 space-y-6">
          {/* Top Grid: Key Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="p-4 flex flex-col gap-2 relative overflow-hidden group hover:border-primary/50 transition-colors">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-bold uppercase tracking-wider">
                <Target size={14} /> Signal
              </div>
              <div className={`text-2xl font-bold font-heading ${plan.decision === 'LONG' ? 'text-success' :
                plan.decision === 'SHORT' ? 'text-danger' : 'text-slate-200'
                }`}>
                {plan.asset ? `${plan.decision || 'WAIT'} ${plan.asset}` : 'WAIT'}
              </div>
              <div className="text-xs text-slate-500 truncate">{plan.thesis || '暂无交易观点'}</div>
              <div className={`absolute top-0 right-0 w-16 h-16 bg-gradient-to-br from-transparent to-white/5 rounded-bl-full pointer-events-none transition-opacity opacity-0 group-hover:opacity-100`} />
            </Card>

            <Card className="p-4 flex flex-col gap-2 group hover:border-primary/50 transition-colors">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-bold uppercase tracking-wider">
                <TrendingUp size={14} /> Entry
              </div>
              <div className="text-2xl font-bold font-heading font-mono-numbers text-slate-200">
                {execution.entry_price || '—'}
              </div>
              <div className="text-xs text-slate-500 font-mono font-mono-numbers">{execution.entry_range || '未设置区间'}</div>
            </Card>

            <Card className="p-4 flex flex-col gap-2 group hover:border-danger/50 transition-colors">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-bold uppercase tracking-wider">
                <ShieldAlert size={14} /> Stop Loss
              </div>
              <div className="text-2xl font-bold font-heading text-danger font-mono-numbers">
                {risk.stop_loss_price || '—'}
              </div>
              <div className="text-xs text-slate-500">Risk Cap Enabled</div>
            </Card>

            <Card className="p-4 flex flex-col gap-2 group hover:border-success/50 transition-colors">
              <div className="flex items-center gap-2 text-slate-400 text-xs font-bold uppercase tracking-wider">
                <CheckCircle size={14} /> Target
              </div>
              <div className="text-2xl font-bold font-heading text-success truncate font-mono-numbers">
                {(Array.isArray(risk.take_profit_targets)
                  ? risk.take_profit_targets.join(' / ')
                  : risk.take_profit_targets) || '—'}
              </div>
              <div className="text-xs text-slate-500">Take Profit</div>
            </Card>
          </div>

          {/* Tool Calls */}
          <Card className="p-0" variant="terminal">
            <div className="flex items-center gap-2 p-4 border-b border-slate-800 bg-slate-900/50">
              <Terminal className="text-primary" size={16} />
              <h2 className="text-sm font-bold font-mono text-slate-300 uppercase tracking-wider">System Logs</h2>
            </div>
            {toolCalls.length ? (
              <div className="p-4 font-mono text-xs text-slate-300 space-y-1.5 overflow-x-auto max-h-[300px] overflow-y-auto custom-scrollbar">
                {toolCalls.map((call, idx) => (
                  <div key={idx} className="flex gap-2 min-w-max hover:bg-white/5 p-0.5 rounded transition-colors group">
                    <span className="text-slate-600 select-none w-6 text-right opacity-50">{idx + 1}</span>
                    <span className="text-primary font-bold">{call.tool}</span>
                    <span className="text-accent">{call.asset}</span>
                    <span className="text-slate-400 group-hover:text-slate-200 transition-colors">→ {call.result}</span>
                  </div>
                ))}
                <div className="animate-pulse text-primary mt-2">_</div>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-600 font-mono text-xs">
                &gt; No execution logs available...
                <div className="animate-pulse mt-2">_</div>
              </div>
            )}
          </Card>

          {/* Risk Logs */}
          <Card className="p-0" variant="terminal">
            <div className="flex items-center gap-2 p-4 border-b border-slate-800 bg-slate-900/50">
              <FileWarning className="text-accent" size={16} />
              <h2 className="text-sm font-bold font-mono text-slate-300 uppercase tracking-wider">Risk Control Diagnostics</h2>
            </div>
            <div className="p-4 font-mono text-xs min-h-[100px] bg-red-950/5">
              {riskLogs.adjustments?.length || riskLogs.warnings?.length ? (
                <div className="space-y-1">
                  {[...(riskLogs.adjustments || []), ...(riskLogs.warnings || [])].map((log, i) => (
                    <div key={i} className="flex gap-2 text-accent/90 hover:bg-white/5 p-0.5 rounded">
                      <span className="text-slate-600 select-none w-6 text-right">[W]</span>
                      <span>{log}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-slate-600 italic">
                  &gt; System operational. No risk events detected.
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default FocusPage
