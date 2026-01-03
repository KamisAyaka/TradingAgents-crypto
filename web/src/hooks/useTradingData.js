import { useEffect, useMemo, useState } from 'react'
import { toNumber } from '../utils/number.js'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const fallbackTrace = [
  {
    title: '市场分析师',
    status: 'pending',
    detail: '等待首次运行。',
  },
]

function useTradingData() {
  const [traceHistory, setTraceHistory] = useState([])
  const [traceTotal, setTraceTotal] = useState(0)
  const [tracePage, setTracePage] = useState(1)
  const [tracePageSize] = useState(16)
  const [selectedTraceId, setSelectedTraceId] = useState(null)
  const [klines, setKlines] = useState([])
  const [trades, setTrades] = useState([])
  const [scheduler, setScheduler] = useState({ running: false, jobs: [] })
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [klineMeta, setKlineMeta] = useState(null)
  const [assets, setAssets] = useState('BTCUSDT,ETHUSDT')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [interval, setKlineInterval] = useState('15m')
  const [capital, setCapital] = useState('100')
  const [minLev, setMinLev] = useState('5')
  const [maxLev, setMaxLev] = useState('10')

  const candles = useMemo(
    () =>
      klines.map((kline) => ({
        o: kline.open,
        h: kline.high,
        l: kline.low,
        c: kline.close,
      })),
    [klines]
  )

  const latestTrace = traceHistory.length ? traceHistory[0].trace : null
  const selectedTrace = useMemo(() => {
    if (!traceHistory.length) {
      return null
    }
    if (!selectedTraceId) {
      return traceHistory[0].trace
    }
    const match = traceHistory.find((record) => record.id === selectedTraceId)
    return match ? match.trace : traceHistory[0].trace
  }, [selectedTraceId, traceHistory])

  const latestPlan = latestTrace?.plan || {}
  const latestExecution = latestPlan.execution || {}
  const latestRisk = latestPlan.risk_management || {}

  const selectedPlan = selectedTrace?.plan || {}
  const selectedExecution = selectedPlan.execution || {}
  const selectedRisk = selectedPlan.risk_management || {}

  useEffect(() => {
    let active = true
    const fetchTraceHistory = async () => {
      try {
        const offset = (tracePage - 1) * tracePageSize
        const res = await fetch(
          `${API_BASE}/api/trace/history?limit=${tracePageSize}&offset=${offset}`
        )
        const payload = await res.json()
        if (active) {
          const records = payload.traces || []
          setTraceHistory(records)
          setTraceTotal(payload.total || 0)
          setSelectedTraceId((prev) => {
            if (!records.length) {
              return null
            }
            if (!prev || !records.some((item) => item.id === prev)) {
              return records[0].id
            }
            return prev
          })
        }
      } catch (err) {
        if (active) {
          setError(String(err))
        }
      }
    }
    const fetchKlines = async () => {
      try {
        const res = await fetch(
          `${API_BASE}/api/klines?symbol=${symbol}&interval=${interval}&limit=80`
        )
        const payload = await res.json()
        if (active) {
          setKlines(payload.klines || [])
          setKlineMeta(payload)
          if (payload.interval_used && payload.interval_used !== interval) {
            setStatus(`未找到 ${interval} 数据，已自动切换到 ${payload.interval_used}`)
          }
        }
      } catch (err) {
        if (active) {
          setError(String(err))
        }
      }
    }
    const fetchScheduler = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/scheduler/status`)
        const payload = await res.json()
        if (active) {
          setScheduler(payload)
        }
      } catch (err) {
        if (active) {
          setError(String(err))
        }
      }
    }
    const fetchTrades = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/trades?symbol=${symbol}&limit=50`)
        const payload = await res.json()
        if (active) {
          setTrades(payload.trades || [])
        }
      } catch (err) {
        if (active) {
          setError(String(err))
        }
      }
    }

    fetchTraceHistory()
    fetchKlines()
    fetchScheduler()
    fetchTrades()

    const timer = window.setInterval(() => {
      fetchTraceHistory()
      fetchKlines()
      fetchScheduler()
      fetchTrades()
    }, 15000)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [interval, symbol, tracePage, tracePageSize])

  const handleRun = async () => {
    setStatus('正在运行分析...')
    setError('')
    try {
      const payload = {
        assets: assets
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        available_capital: Number.parseFloat(capital) || 100,
        min_leverage: Number.parseInt(minLev, 10) || 5,
        max_leverage: Number.parseInt(maxLev, 10) || 10,
      }
      const res = await fetch(`${API_BASE}/api/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      await res.json()
      setStatus('分析完成。')
    } catch (err) {
      setStatus('')
      setError(String(err))
    }
  }

  const handleScheduler = async (action) => {
    setStatus(`${action === 'start' ? '正在启动' : '正在停止'}调度器...`)
    setError('')
    try {
      let options = {}
      if (action === 'start') {
        const payload = {
          assets: assets
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
          available_capital: Number.parseFloat(capital) || 100,
          min_leverage: Number.parseInt(minLev, 10) || 5,
          max_leverage: Number.parseInt(maxLev, 10) || 10,
        }
        options = {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      } else {
        options = { method: 'POST' }
      }

      const res = await fetch(`${API_BASE}/api/scheduler/${action}`, options)
      const payload = await res.json()
      setScheduler(payload)
      setStatus('调度器已更新。')
    } catch (err) {
      setStatus('')
      setError(String(err))
    }
  }

  const traceEvents = selectedTrace?.trace_events || fallbackTrace
  const thread = selectedTrace?.thread || []
  const toolCalls = selectedTrace?.tool_calls || []
  const riskLogs = selectedTrace?.risk_logs || {}

  const markers = useMemo(() => {
    if (!candles.length || !trades.length) {
      return []
    }
    const timeSeries = klines.map((item) => item.close_time || item.open_time)
    return trades
      .map((trade) => {
        const decision = (trade.decision || '').toUpperCase()
        const entryPrice = toNumber(trade.entry_price) || toNumber(trade.stop_loss)
        const created = trade.created_at ? Date.parse(trade.created_at) : null
        if (!decision || created === null) {
          return null
        }
        let index = timeSeries.findIndex((time) => time >= created)
        if (index < 0) {
          index = timeSeries.length - 1
        }
        const color =
          decision === 'LONG'
            ? 'var(--accent-green)'
            : decision === 'SHORT'
              ? 'var(--accent-red)'
              : decision === 'CLOSE_LONG' || decision === 'CLOSE_SHORT'
                ? 'var(--accent-gold)'
                : 'rgba(160, 186, 230, 0.7)'
        const kind =
          decision === 'LONG' || decision === 'SHORT'
            ? 'open'
            : decision === 'CLOSE_LONG' || decision === 'CLOSE_SHORT'
              ? 'close'
              : 'other'
        return {
          index,
          price: entryPrice,
          last: candles[index].c,
          color,
          kind,
        }
      })
      .filter(Boolean)
  }, [candles, klines, trades])

  const levels = useMemo(
    () => ({
      entry: toNumber(latestExecution.entry_price),
      stop: toNumber(latestRisk.stop_loss_price),
      targets: (latestRisk.take_profit_targets || [])
        .map((value) => toNumber(value))
        .filter((value) => value !== null),
      last: candles.length ? candles[candles.length - 1].c : null,
      markers,
    }),
    [
      candles,
      latestExecution.entry_price,
      markers,
      latestRisk.stop_loss_price,
      latestRisk.take_profit_targets,
    ]
  )

  return {
    assets,
    candles,
    capital,
    error,
    execution: latestExecution,
    handleRun,
    handleScheduler,
    interval,
    klines,
    klineMeta,
    levels,
    maxLev,
    minLev,
    plan: latestPlan,
    risk: latestRisk,
    riskLogs,
    scheduler,
    setAssets,
    setCapital,
    setKlineInterval,
    setMaxLev,
    setMinLev,
    setSymbol,
    setTracePage,
    setSelectedTraceId,
    status,
    symbol,
    thread,
    toolCalls,
    traceEvents,
    traceHistory,
    tracePage,
    tracePageSize,
    traceTotal,
    selectedPlan,
    selectedExecution,
    selectedRisk,
    selectedRiskLogs: riskLogs,
    selectedToolCalls: toolCalls,
    selectedTraceId,
  }
}

export default useTradingData
