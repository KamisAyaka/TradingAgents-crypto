import { useState } from 'react'

function CollapsibleText({ text, limit = 360 }) {
  const [expanded, setExpanded] = useState(false)
  if (!text) {
    return <p className="muted">暂无内容。</p>
  }
  let prettyText = text
  const trimmed = text.trim()
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      prettyText = JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch {
      prettyText = text
    }
  }
  const shouldTruncate = prettyText.length > limit
  const displayText =
    shouldTruncate && !expanded ? `${prettyText.slice(0, limit)}...` : prettyText
  return (
    <div className="collapsible">
      <pre className="whitespace-pre-wrap break-words p-2 bg-slate-950/30 rounded text-xs font-mono border border-slate-800/50">{displayText}</pre>
      {shouldTruncate ? (
        <button
          className="link-button"
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? '收起' : '展开'}
        </button>
      ) : null}
    </div>
  )
}

export default CollapsibleText
