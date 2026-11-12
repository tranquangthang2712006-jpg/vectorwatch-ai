// Lớp gọi API dùng chung. Token lưu trong sessionStorage (mất khi đóng tab).
const TOKEN_KEY = 'vw_token'

export function getToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(token) {
  try { token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY) } catch { /* bỏ qua */ }
}

let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) { onUnauthorized = fn }

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

async function request(method, path, { body, form, raw } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  let res
  try {
    res = await fetch(path, { method, headers, body: payload })
  } catch {
    throw new ApiError('Không kết nối được máy chủ. Kiểm tra backend đã chạy (cổng 8000) rồi nhấn “Thử lại”.', 0)
  }
  if (!res.ok) {
    let detail = `Yêu cầu thất bại (mã ${res.status}).`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') detail = data.detail
      else if (Array.isArray(data.detail)) detail = 'Dữ liệu gửi lên chưa hợp lệ: ' + data.detail.map((d) => `${(d.loc || []).slice(-1)[0]} — ${d.msg}`).join('; ')
    } catch { /* giữ thông báo mặc định */ }
    if (res.status === 401 && path !== '/api/auth/login') onUnauthorized()
    throw new ApiError(detail, res.status)
  }
  if (raw) return res
  return res.json()
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, { body: body ?? {} }),
  upload: (path, form) => request('POST', path, { form }),
  async download(path, fallbackName) {
    const res = await request('GET', path, { raw: true })
    const blob = await res.blob()
    const match = /filename="?([^"]+)"?/.exec(res.headers.get('Content-Disposition') || '')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = match ? match[1] : fallbackName
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}

export function qs(params) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') search.set(k, v) })
  const text = search.toString()
  return text ? `?${text}` : ''
}
