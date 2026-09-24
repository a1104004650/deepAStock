export function fmtPrice(v) {
  if (v == null || isNaN(v)) return '--'
  return Number(v).toFixed(2)
}

export function fmtAmt(v) {
  if (v == null || isNaN(v)) return '--'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function fmtMoney(v) {
  if (v == null || isNaN(v)) return '0'
  if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(0) + '万'
  return v.toLocaleString()
}

export function fmtPct(v) {
  if (v == null || isNaN(v)) return '--'
  const n = Number(v)
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%'
}

export function fmtVol(v) {
  if (v == null || isNaN(v)) return '--'
  if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(0) + '万'
  return v.toString()
}

export function fmtLarge(v) {
  if (v == null || isNaN(v)) return '--'
  if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(1) + '亿'
  if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(0) + '万'
  return v.toLocaleString()
}
