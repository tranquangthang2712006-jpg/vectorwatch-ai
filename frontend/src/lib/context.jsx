import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api.js'

// ---------------------------------------------------------------- Toast
const ToastContext = createContext(null)
export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)
  const dismiss = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), [])
  const push = useCallback((type, message, sticky = false) => {
    const id = ++idRef.current
    setToasts((list) => [...list.slice(-3), { id, type, message }])
    if (!sticky) setTimeout(() => dismiss(id), type === 'error' ? 8000 : 4500)
  }, [dismiss])
  const value = useMemo(() => ({
    success: (m) => push('success', m),
    info: (m) => push('info', m),
    warning: (m) => push('warning', m),
    error: (m) => push('error', m),
  }), [push])
  const styles = {
    success: 'border-emerald-300 bg-emerald-50 text-emerald-900',
    info: 'border-sky-300 bg-sky-50 text-sky-900',
    warning: 'border-amber-300 bg-amber-50 text-amber-900',
    error: 'border-red-300 bg-red-50 text-red-900',
  }
  const titles = { success: 'Thành công', info: 'Thông tin', warning: 'Lưu ý', error: 'Lỗi' }
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="no-print fixed bottom-4 right-4 z-[2000] flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} role={t.type === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-4 py-3 shadow-lg ${styles[t.type]}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide">{titles[t.type]}</div>
                <div className="mt-0.5 text-sm">{t.message}</div>
              </div>
              <button onClick={() => dismiss(t.id)} className="text-lg leading-none opacity-60 hover:opacity-100" aria-label="Đóng thông báo">×</button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// ---------------------------------------------------------------- Auth + meta + bộ lọc dùng chung
const AppContext = createContext(null)
export const useApp = () => useContext(AppContext)

export function AppProvider({ children }) {
  const [user, setUser] = useState(null)
  const [meta, setMeta] = useState(null)
  const [booting, setBooting] = useState(true)
  const [bootError, setBootError] = useState(null)
  const [areaId, setAreaId] = useState('')   // '' = tất cả khu vực
  const [days, setDays] = useState(7)

  const logout = useCallback(() => { setToken(null); setUser(null); setMeta(null) }, [])
  useEffect(() => { setUnauthorizedHandler(logout) }, [logout])

  const loadSession = useCallback(async () => {
    setBootError(null)
    if (!getToken()) { setBooting(false); return }
    try {
      const [me, m] = await Promise.all([api.get('/api/auth/me'), api.get('/api/meta')])
      setUser(me); setMeta(m)
    } catch (err) {
      if (err.status !== 401) setBootError(err.message)
    } finally { setBooting(false) }
  }, [])
  useEffect(() => { loadSession() }, [loadSession])

  const login = useCallback(async (email, password) => {
    const res = await api.post('/api/auth/login', { email, password })
    setToken(res.token)
    setUser(res.user)
    setMeta(await api.get('/api/meta'))
  }, [])

  const refreshMeta = useCallback(async () => { try { setMeta(await api.get('/api/meta')) } catch { /* giữ meta cũ */ } }, [])
  const can = useCallback((perm) => !!user && user.permissions.includes(perm), [user])

  const value = useMemo(() => ({ user, meta, booting, bootError, login, logout, can, refreshMeta, reloadSession: loadSession,
    areaId, setAreaId, days, setDays }),
  [user, meta, booting, bootError, login, logout, can, refreshMeta, loadSession, areaId, days])
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

// ---------------------------------------------------------------- Hook tải dữ liệu
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const counter = useRef(0)
  const run = useCallback(async (silent = false) => {
    const id = ++counter.current
    if (!silent) setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await fn()
      if (id === counter.current) setState({ data, loading: false, error: null })
    } catch (err) {
      if (id === counter.current) setState((s) => ({ data: silent ? s.data : null, loading: false, error: silent ? s.error : err.message }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { run() }, [run])
  return { ...state, reload: run }
}
