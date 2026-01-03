import { useRef } from 'react'

function CandleChart({ candles, levels, onSelect, selectedPoint }) {
  if (!candles.length) {
    return <div className="chart-empty">暂无 K 线数据。</div>
  }

  const width = 980
  const height = 460
  const padding = 28
  const rightGutter = 72
  const max = Math.max(...candles.map((c) => c.h))
  const min = Math.min(...candles.map((c) => c.l))
  const range = max - min || 1
  const chartWidth = width - padding * 2 - rightGutter
  const chartHeight = height - padding * 2
  const candleWidth = chartWidth / candles.length
  const chartRight = padding + chartWidth
  const svgRef = useRef(null)

  const clamp = (value, minValue, maxValue) =>
    Math.min(Math.max(value, minValue), maxValue)

  const yScale = (value) =>
    padding + (max - value) * (chartHeight / range)

  const xScale = (index) => padding + index * candleWidth + candleWidth / 2

  const entryY = levels.entry ? yScale(levels.entry) : null
  const stopY = levels.stop ? yScale(levels.stop) : null
  const lastY = levels.last ? yScale(levels.last) : null

  const ticks = Array.from({ length: 5 }).map((_, idx) => {
    const value = max - (idx * range) / 4
    return { value, y: yScale(value) }
  })

  const lastLabel = levels.last ? levels.last.toFixed(2) : ''

  const handleClick = (event) => {
    if (!onSelect || !svgRef.current) {
      return
    }
    const rect = svgRef.current.getBoundingClientRect()
    const x = ((event.clientX - rect.left) * width) / rect.width
    const y = ((event.clientY - rect.top) * height) / rect.height
    if (x < padding || x > chartRight || y < padding || y > height - padding) {
      return
    }
    const index = clamp(Math.floor((x - padding) / candleWidth), 0, candles.length - 1)
    const price = max - ((y - padding) * range) / chartHeight
    onSelect({ index, price: Number(price.toFixed(2)) })
  }

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${width} ${height}`}
      style={{ width: '100%', height: 'auto', display: 'block' }}
      aria-label="K 线图"
      onClick={handleClick}
    >
      <defs>
        <linearGradient id="chartGlow" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(108, 221, 255, 0.25)" />
          <stop offset="100%" stopColor="rgba(255, 202, 120, 0.15)" />
        </linearGradient>
      </defs>
      <rect
        x="0"
        y="0"
        width={width}
        height={height}
        fill="url(#chartGlow)"
        opacity="0.6"
      />
      {ticks.map((tick, idx) => (
        <g key={`grid-${idx}`}>
          <line
            x1={padding}
            y1={tick.y}
            x2={chartRight}
            y2={tick.y}
            stroke="rgba(255,255,255,0.08)"
            strokeDasharray="4 6"
          />
          <text
            x={chartRight + 12}
            y={tick.y + 4}
            fill="rgba(200, 214, 244, 0.6)"
            fontSize="10"
            fontFamily="var(--font-mono)"
          >
            {tick.value.toFixed(2)}
          </text>
        </g>
      ))}
      {candles.map((_, idx) => {
        if (idx % 4 !== 0) return null
        const x = xScale(idx)
        return (
          <line
            key={`v-grid-${idx}`}
            x1={x}
            y1={padding}
            x2={x}
            y2={height - padding}
            stroke="rgba(255,255,255,0.05)"
          />
        )
      })}
      {candles.map((candle, index) => {
        const x = xScale(index)
        const openY = yScale(candle.o)
        const closeY = yScale(candle.c)
        const highY = yScale(candle.h)
        const lowY = yScale(candle.l)
        const isUp = candle.c >= candle.o
        // Traditional TradingView-style colors
        // Up (Green/Teal): #26a69a
        // Down (Red): #ef5350
        const color = isUp ? '#26a69a' : '#ef5350'

        // Ensure minimum height for doji candles
        const bodyHeight = Math.max(1, Math.abs(openY - closeY))
        const bodyY = isUp ? closeY : openY

        return (
          <g key={`candle-${index}`}>
            <line
              x1={x}
              y1={highY}
              x2={x}
              y2={lowY}
              stroke={color}
              strokeWidth="2"
            />
            <rect
              x={x - candleWidth * 0.25}
              y={bodyY}
              width={candleWidth * 0.5}
              height={bodyHeight}
              fill={color}
              rx="0" // Sharp edges for clearer reading
            />
          </g>
        )
      })}
      {entryY !== null ? (
        <line
          x1={padding}
          y1={entryY}
          x2={chartRight}
          y2={entryY}
          stroke="var(--accent-blue)"
          strokeWidth="2"
        />
      ) : null}
      {stopY !== null ? (
        <line
          x1={padding}
          y1={stopY}
          x2={chartRight}
          y2={stopY}
          stroke="var(--accent-red)"
          strokeWidth="2"
          strokeDasharray="6 6"
        />
      ) : null}
      {lastY !== null ? (
        <>
          <line
            x1={padding}
            y1={lastY}
            x2={chartRight}
            y2={lastY}
            stroke="rgba(255, 205, 117, 0.6)"
            strokeWidth="1.5"
            strokeDasharray="6 6"
          />
          <rect
            x={chartRight + 6}
            y={lastY - 10}
            width={rightGutter - 12}
            height={20}
            rx={6}
            fill="rgba(255, 205, 117, 0.18)"
            stroke="rgba(255, 205, 117, 0.6)"
          />
          <text
            x={chartRight + 14}
            y={lastY + 4}
            fill="var(--accent-gold)"
            fontSize="11"
            fontWeight="600"
            fontFamily="var(--font-mono)"
          >
            {lastLabel}
          </text>
        </>
      ) : null}
      {levels.targets.map((target) => (
        <line
          key={`target-${target}`}
          x1={padding}
          y1={yScale(target)}
          x2={chartRight}
          y2={yScale(target)}
          stroke="rgba(123, 199, 255, 0.5)"
          strokeDasharray="3 8"
        />
      ))}
      {levels.markers.map((marker, idx) => {
        const markerY = marker.price ? yScale(marker.price) : yScale(marker.last)
        const markerX = xScale(marker.index)
        return (
          <g key={`marker-${idx}`}>
            <circle
              cx={markerX}
              cy={markerY}
              r="6"
              fill={marker.color}
              stroke="rgba(10,16,32,0.8)"
              strokeWidth="2"
            />
          </g>
        )
      })}
      {selectedPoint ? (
        <g>
          <line
            x1={padding}
            y1={yScale(selectedPoint.price)}
            x2={chartRight}
            y2={yScale(selectedPoint.price)}
            stroke="rgba(115, 231, 255, 0.7)"
            strokeDasharray="4 6"
          />
          <circle
            cx={xScale(selectedPoint.index)}
            cy={yScale(selectedPoint.price)}
            r="6"
            fill="var(--accent-sky)"
            stroke="rgba(10,16,32,0.8)"
            strokeWidth="2"
          />
        </g>
      ) : null}
    </svg>
  )
}

export default CandleChart
