const CN_OFFSET = 8 * 3600 * 1000

// 平台新闻 time 是 epoch 秒；RSS pub_time 是 naive 北京墙钟时间字符串。
// 统一转为 epoch ms（东八区正确显示）。
export function toEpochMs(ts) {
  if (!ts && ts !== 0) return null
  const str = String(ts)
  if (/^-?\d+(\.\d+)?$/.test(str)) {
    const n = Number(str)
    return n < 1e12 ? n * 1000 : n
  }
  const s = str.trim()
  if (!s) return null
  // 带时区（Z/±hh:mm）或带 T 的 ISO
  let d
  if (/[zZ]|[+-]\d{2}:\d{2}$/.test(s)) {
    d = new Date(s.includes('T') || /[zZ]/.test(s) ? s : s.replace(' ', 'T'))
  } else {
    // 无时区 → 按东八区解释
    d = new Date((s.includes('T') ? s : s.replace(' ', 'T')) + '+08:00')
  }
  return isNaN(d.getTime()) ? null : d.getTime()
}

// 统一输出：24 小时制，同日内显示「HH:mm」，跨日显示「MM-DD HH:mm」。时区以东八区为准。
export function formatNewsTime(ts, nowMs = Date.now()) {
  const ms = toEpochMs(ts)
  if (ms == null) return ''
  const d = new Date(ms + CN_OFFSET)
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  const now = new Date(nowMs + CN_OFFSET)
  const sameDay = d.getUTCFullYear() === now.getUTCFullYear() && mm === (String(now.getUTCMonth() + 1).padStart(2, '0')) && dd === (String(now.getUTCDate()).padStart(2, '0'))
  return sameDay ? `${hh}:${mi}` : `${mm}-${dd} ${hh}:${mi}`
}