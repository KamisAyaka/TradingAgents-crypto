export function toNumber(value) {
  if (value === null || value === undefined) {
    return null
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  const parsed = Number.parseFloat(String(value).replace(/[^0-9.\-]/g, ''))
  return Number.isFinite(parsed) ? parsed : null
}
