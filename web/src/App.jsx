import { Navigate, Route, Routes } from 'react-router-dom'
import AppHeader from './components/AppHeader.jsx'
import HomePage from './pages/HomePage.jsx'
import TracePage from './pages/TracePage.jsx'
import FocusPage from './pages/FocusPage.jsx'
import useTradingData from './hooks/useTradingData.js'
import './App.css'

function App() {
  const {
    assets,
    candles,
    capital,
    error,
    execution,
    handleRun,
    handleScheduler,
    interval,
    klines,
    klineMeta,
    levels,
    maxLev,
    minLev,
    plan,
    risk,
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
    selectedRiskLogs,
    selectedToolCalls,
    selectedTraceId,
  } = useTradingData()

  return (
    <div className="app-shell">
      <AppHeader scheduler={scheduler} symbol={symbol} />

      <main className="app">
        <Routes>
          <Route
            path="/"
            element={
              <HomePage
                assets={assets}
                capital={capital}
                interval={interval}
                klines={klines}
                klineMeta={klineMeta}
                levels={levels}
                maxLev={maxLev}
                minLev={minLev}
                scheduler={scheduler}
                setAssets={setAssets}
                setCapital={setCapital}
                setKlineInterval={setKlineInterval}
                setMaxLev={setMaxLev}
                setMinLev={setMinLev}
                setSymbol={setSymbol}
                status={status}
                error={error}
                symbol={symbol}
                handleRun={handleRun}
                handleScheduler={handleScheduler}
                candles={candles}
              />
            }
          />
          <Route
            path="/trace"
            element={
              <TracePage
                traceEvents={traceEvents}
                thread={thread}
                history={traceHistory}
                selectedTraceId={selectedTraceId}
                onSelectTrace={setSelectedTraceId}
                historyPage={tracePage}
                historyPageSize={tracePageSize}
                historyTotal={traceTotal}
                onPageChange={setTracePage}
              />
            }
          />
          <Route
            path="/focus"
            element={
              <FocusPage
                execution={selectedExecution}
                plan={selectedPlan}
                risk={selectedRisk}
                toolCalls={selectedToolCalls}
                riskLogs={selectedRiskLogs}
                history={traceHistory}
                selectedTraceId={selectedTraceId}
                onSelectTrace={setSelectedTraceId}
                historyPage={tracePage}
                historyPageSize={tracePageSize}
                historyTotal={traceTotal}
                onPageChange={setTracePage}
              />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
