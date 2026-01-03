import { Share2, Clock, CheckCircle2, AlertCircle, MessageSquare } from 'lucide-react';
import TraceHistoryPanel from '../components/TraceHistoryPanel.jsx'
import CollapsibleText from '../components/CollapsibleText.jsx'
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';

function TracePage({
  traceEvents,
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

        {/* Sidebar: History List */}
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
              title="Trace 历史"
            />
          </Card>
        </div>

        {/* Main Content: Timeline & Thread */}
        <div className="lg:col-span-9 space-y-6">
          {/* Trace Timeline */}
          <Card className="p-6">
            <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-700/50">
              <div className="flex items-center gap-2">
                <Share2 className="text-primary" size={20} />
                <h2 className="text-lg font-bold font-heading text-slate-100">Trace 时间线</h2>
              </div>
              <Badge variant="primary">{traceEvents.length} Events</Badge>
            </div>

            <div className="relative pl-4 space-y-8 before:absolute before:inset-y-0 before:left-[21px] before:w-0.5 before:bg-slate-700/50">
              {traceEvents.map((event, index) => {
                const isCompleted = event.status === 'completed';
                const isAdjusted = event.status === 'adjusted';

                return (
                  <div key={`${event.title}-${index}`} className="relative pl-8">
                    {/* Timeline Dot */}
                    <div className={`absolute left-0 top-1.5 w-3 h-3 rounded-full border-2 transform -translate-x-[5px] z-10 bg-background ${isCompleted ? 'border-success bg-success/20' :
                      isAdjusted ? 'border-accent bg-accent/20' :
                        'border-slate-500 bg-slate-500/20'
                      }`} />

                    <div className="flex flex-col gap-2">
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-bold text-slate-200">
                          {{
                            'Market Analyst': '市场分析师',
                            'Newsflash Analyst': '快讯分析师',
                            'Longform Cache': '长文缓存',
                            Debate: '辩论',
                            Trader: '交易员',
                            'Risk Control': '风险控制',
                            Execution: '执行',
                          }[event.title] || event.title}
                        </span>
                        {event.time && (
                          <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
                            <span className="flex items-center gap-1"><Clock size={10} /> {event.time}</span>
                            {event.latency && <span className="opacity-70">{event.latency}</span>}
                          </div>
                        )}
                        {isCompleted && <CheckCircle2 size={12} className="text-success" />}
                        {isAdjusted && <AlertCircle size={12} className="text-accent" />}
                      </div>

                      <div className="text-sm text-slate-400 bg-slate-800/30 rounded p-3 border border-slate-700/30">
                        <CollapsibleText text={String(event.detail || '')} limit={420} />
                      </div>
                    </div>
                  </div>
                )
              })}
              {!traceEvents.length && (
                <div className="text-center py-12 text-slate-500 flex flex-col items-center gap-2">
                  <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mb-2">
                    <Share2 size={24} className="opacity-50" />
                  </div>
                  <p>暂无 Trace 数据</p>
                </div>
              )}
            </div>
          </Card>


        </div>
      </div>
    </div>
  )
}

export default TracePage
