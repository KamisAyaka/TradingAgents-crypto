import { useMemo, useState } from 'react';
import { Play, Pause, BarChart2, DollarSign, Layers, Clock, Settings, RefreshCw } from 'lucide-react';
import CandleChart from '../components/CandleChart.jsx';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';

function HomePage({
  assets,
  capital,
  interval,
  klines,
  klineMeta,
  levels,
  maxLev,
  minLev,
  scheduler,
  setAssets,
  setCapital,
  setKlineInterval,
  setMaxLev,
  setMinLev,
  setSymbol,
  status,
  error,
  symbol,
  handleRun,
  handleScheduler,
  candles,
  monitoringTargets,
}) {
  const [selectedPoint, setSelectedPoint] = useState(null);

  const selectedKline = useMemo(() => {
    if (!selectedPoint || !klines.length) {
      return null;
    }
    return klines[selectedPoint.index] || null;
  }, [klines, selectedPoint]);

  const selectedTime = selectedKline
    ? new Date(selectedKline.close_time || selectedKline.open_time).toLocaleString()
    : '';

  const chartTabs = [
    { label: '15m', value: '15m' },
    { label: '1h', value: '1h' },
    { label: '4h', value: '4h' },
    { label: '1d', value: '1d' },
  ];

  const parseMonitoringPrices = (raw) => {
    if (!raw) {
      return [];
    }
    if (Array.isArray(raw)) {
      return raw;
    }
    if (typeof raw === 'string') {
      try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        return [];
      }
    }
    return [];
  };

  return (
    <div className="min-h-screen bg-background pt-20 pb-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Status & Error Messages */}
        {(status || error) && (
          <div className="flex flex-col gap-2">
            {status && <div className="bg-primary/10 border border-primary/20 text-primary px-4 py-2 rounded text-sm">{status}</div>}
            {error && <div className="bg-danger/10 border border-danger/20 text-danger px-4 py-2 rounded text-sm">{error}</div>}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

          {/* Main Chart Section */}
          <div className="lg:col-span-9 space-y-4">
            <Card className="h-[600px] flex flex-col p-4 relative group">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xl font-bold font-heading text-slate-100">{symbol}</span>
                    <Badge variant="primary">Running</Badge>
                  </div>
                  <div className="text-xs text-slate-500 font-mono hidden sm:block">
                    {klineMeta?.db_path && `DB: ${klineMeta.db_path.split('/').pop()}`}
                  </div>
                </div>

                <div className="flex bg-slate-800/50 p-1 rounded-lg border border-slate-700/50">
                  {chartTabs.map((tab) => (
                    <button
                      key={tab.value}
                      onClick={() => setKlineInterval(tab.value)}
                      className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${interval === tab.value
                          ? 'bg-slate-700 text-white shadow-sm'
                          : 'text-slate-400 hover:text-slate-200'
                        }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex-1 w-full bg-slate-900/50 rounded border border-slate-800 relative overflow-hidden">
                {/* Chart Component Wrapper */}
                <div className="absolute inset-0">
                  <CandleChart
                    candles={candles}
                    levels={levels}
                    onSelect={setSelectedPoint}
                    selectedPoint={selectedPoint}
                  />
                </div>
              </div>

              {/* Chart Overlay Info */}
              <div className="absolute bottom-6 left-6 pointer-events-none">
                {selectedPoint ? (
                  <div className="bg-slate-900/90 backdrop-blur border border-slate-700 p-3 rounded shadow-xl text-xs space-y-1 text-slate-300">
                    <div className="flex justify-between gap-4"><span className="text-slate-500">Price</span> <span className="font-mono text-white">{selectedPoint.price}</span></div>
                    <div className="flex justify-between gap-4"><span className="text-slate-500">Index</span> <span className="font-mono">{selectedPoint.index}</span></div>
                    {selectedTime && <div className="flex justify-between gap-4"><span className="text-slate-500">Time</span> <span className="font-mono">{selectedTime}</span></div>}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 bg-slate-900/50 px-2 py-1 rounded">点击 K 线查看详情</div>
                )}
              </div>
            </Card>

            <Card className="p-5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-700/50">
                <div className="flex items-center gap-2">
                  <BarChart2 size={18} className="text-primary" />
                  <h2 className="text-sm font-bold font-heading text-slate-200">监控价位</h2>
                </div>
                <Badge variant="outline">实时</Badge>
              </div>

              {monitoringTargets.length ? (
                <div className="space-y-4 text-xs">
                  {monitoringTargets.map((target) => {
                    const nodes = parseMonitoringPrices(target.monitoring_prices);
                    const decision = (target.decision || '').toUpperCase();
                    const hasAbove = nodes.some(
                      (node) => (node.condition || '').toLowerCase() === 'above'
                    );
                    const hasBelow = nodes.some(
                      (node) => (node.condition || '').toLowerCase() === 'below'
                    );
                    const nodeHint =
                      decision === 'WAIT' && !(hasAbove && hasBelow)
                        ? '缺少上下对照节点'
                        : '';
                    return (
                      <div
                        key={target.symbol}
                        className="space-y-2 rounded-lg border border-slate-800/80 bg-slate-900/60 p-3"
                      >
                        <div className="flex items-center justify-between">
                          <div className="font-semibold text-slate-100">{target.symbol}</div>
                          <Badge variant={decision === 'WAIT' ? 'default' : 'primary'}>
                            {decision || 'N/A'}
                          </Badge>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                          <div>
                            止损:{' '}
                            <span className="font-mono text-slate-200">
                              {target.stop_loss ?? '—'}
                            </span>
                          </div>
                          <div>
                            止盈:{' '}
                            <span className="font-mono text-slate-200">
                              {target.take_profit ?? '—'}
                            </span>
                          </div>
                        </div>
                        <div className="space-y-1 text-[11px]">
                          {nodes.length ? (
                            nodes.map((node, idx) => (
                              <div
                                key={`${target.symbol}-${idx}`}
                                className="flex items-center justify-between text-slate-400"
                              >
                                <span className="font-mono text-slate-200">
                                  {node.price ?? '—'}
                                </span>
                                <span className="uppercase">{node.condition || 'touch'}</span>
                                <span className="text-slate-500">
                                  {node.note || '监控价位'}
                                </span>
                              </div>
                            ))
                          ) : (
                            <div className="text-slate-500">暂无监控节点</div>
                          )}
                        </div>
                        {nodeHint && <div className="text-[11px] text-amber-300">{nodeHint}</div>}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-xs text-slate-500">暂无监控数据</div>
              )}
            </Card>
          </div>

          {/* Sidebar Controls */}
          <div className="lg:col-span-3 space-y-4">
            <Card className="p-5 space-y-5">
              <div className="flex items-center gap-2 pb-3 border-b border-slate-700/50">
                <Settings size={18} className="text-primary" />
                <h2 className="text-sm font-bold font-heading text-slate-200">运行参数</h2>
              </div>

              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400 flex items-center gap-1">
                    <Layers size={12} /> 资产列表
                  </label>
                  <input
                    type="text"
                    value={assets}
                    onChange={(e) => setAssets(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/50 transition-colors placeholder:text-slate-600"
                    placeholder="BTCUSDT, ETHUSDT"
                  />
                  <div className="flex flex-wrap gap-2 pt-1">
                    {assets.split(/[,，]/).map(s => s.trim()).filter(Boolean).map(s => (
                      <button
                        key={s}
                        onClick={() => setSymbol(s.toUpperCase())}
                        className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${symbol === s.toUpperCase()
                            ? 'bg-primary/20 border-primary text-primary'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'
                          }`}
                      >
                        {s.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400 flex items-center gap-1">
                    <DollarSign size={12} /> 可用资金 (USDT)
                  </label>
                  <input
                    type="number"
                    value={capital}
                    onChange={(e) => setCapital(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-primary transition-colors font-mono"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-400">最小杠杆</label>
                    <input
                      type="number"
                      value={minLev}
                      onChange={(e) => setMinLev(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-primary transition-colors font-mono"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-400">最大杠杆</label>
                    <input
                      type="number"
                      value={maxLev}
                      onChange={(e) => setMaxLev(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-primary transition-colors font-mono"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400 flex items-center gap-1">
                    <Clock size={12} /> 自定义周期
                  </label>
                  <input
                    type="text"
                    value={interval}
                    onChange={(e) => setKlineInterval(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-primary transition-colors font-mono"
                  />
                </div>
              </div>

              <div className="pt-2">
                <Button variant="primary" className="w-full" onClick={handleRun}>
                  <RefreshCw size={16} className="mr-2" />
                  立即运行分析
                </Button>
              </div>

              <div className="pt-4 border-t border-slate-700/50 space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-400">自动调度</label>
                  <Badge variant={scheduler.running ? 'success' : 'default'} className="animate-pulse">
                    {scheduler.running ? 'Running' : 'Stopped'}
                  </Badge>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleScheduler('start')}
                    disabled={scheduler.running}
                    className="w-full"
                  >
                    <Play size={14} className="mr-1.5" /> 启动
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleScheduler('stop')}
                    disabled={!scheduler.running}
                    className="w-full"
                  >
                    <Pause size={14} className="mr-1.5" /> 停止
                  </Button>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

export default HomePage;
