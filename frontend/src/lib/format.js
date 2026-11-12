export const fmtNum = (v, digits = 1) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('vi-VN', { maximumFractionDigits: digits }))
export const fmtPct = (v) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`)
export function fmtDate(iso) {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}
export function fmtDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
export function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString('vi-VN')
}
export function duration(startIso, endIso) {
  if (!startIso || !endIso) return '—'
  const ms = new Date(endIso) - new Date(startIso)
  return ms < 1000 ? '< 1 giây' : `${Math.round(ms / 1000)} giây`
}
export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

// Màu + nhãn cho nhóm ESS. Màu không bao giờ là tín hiệu duy nhất: luôn kèm nhãn chữ và số.
export const ESS_LEVELS = {
  very_low: { label: 'Rất thấp', color: '#64748b', range: '0–24' },
  low: { label: 'Thấp', color: '#16a34a', range: '25–49' },
  medium: { label: 'Trung bình', color: '#d9a406', range: '50–74' },
  high: { label: 'Cao', color: '#ea6a0c', range: '75–89' },
  very_high: { label: 'Rất cao', color: '#c81e1e', range: '90–100' },
  not_scored: { label: 'Không đủ dữ liệu', color: '#cbd5e1', range: '—' },
}
export const PIS_LEVELS = {
  none: { label: 'Không ưu tiên', color: '#64748b' },
  watch: { label: 'Theo dõi', color: '#16a34a' },
  inspect: { label: 'Cần kiểm tra', color: '#d9a406' },
  priority: { label: 'Ưu tiên kiểm tra', color: '#c81e1e' },
}
export const essKey = (cls) => (cls ? (typeof cls === 'string' ? cls : cls.key) : 'not_scored')
export const SHORT_FACTOR = { rainfall: 'mưa', temperature: 'nhiệt độ', humidity: 'độ ẩm', water: 'điểm nước đọng', survey: 'khảo sát' }
export const missingText = (missing) => (missing || []).map((m) => SHORT_FACTOR[m.key] || m.label).join(', ')
