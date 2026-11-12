import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Bell, Bot, ClipboardCheck, Database, FileText, LayoutDashboard, LogOut, Map as MapIcon, Microscope, PanelLeftClose, PanelLeftOpen, Settings } from 'lucide-react'
import { useApp, useAsync } from '../lib/context.jsx'
import { api } from '../lib/api.js'
import { fmtDate } from '../lib/format.js'
import { Modal, SampleTag } from './ui.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, title: 'Tổng quan hệ thống' },
  { to: '/map', label: 'Bản đồ nguy cơ', icon: MapIcon, title: 'Bản đồ nguy cơ môi trường' },
  { to: '/analysis', label: 'Phân tích môi trường', icon: Microscope, title: 'Phân tích điều kiện môi trường' },
  { to: '/alerts', label: 'Cảnh báo & phê duyệt', icon: ClipboardCheck, title: 'Cảnh báo và phê duyệt' },
  { to: '/agent', label: 'AI Agent Center', icon: Bot, title: 'AI Agent Center' },
  { to: '/data', label: 'Quản lý dữ liệu', icon: Database, title: 'Quản lý dữ liệu' },
  { to: '/reports', label: 'Báo cáo & đánh giá', icon: FileText, title: 'Báo cáo và đánh giá' },
  { to: '/settings', label: 'Cài đặt', icon: Settings, title: 'Cài đặt và cấu hình (chỉ đọc)' },
]

function Logo({ collapsed }) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sky-400/15 ring-1 ring-sky-300/40">
        <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden="true"><path d="M7 8l9 16 9-16" fill="none" stroke="#7dd3fc" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" /><circle cx="16" cy="9" r="2.2" fill="#fbbf24" /></svg>
      </div>
      {!collapsed && (
        <div className="leading-tight">
          <div className="text-[15px] font-bold text-white">VectorWatch <span className="text-sky-300">AI</span></div>
          <div className="text-[11px] text-slate-300">Giám sát môi trường véc-tơ</div>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const { user, meta, logout, areaId, setAreaId, days, setDays } = useApp()
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 1180)
  const [showBuild, setShowBuild] = useState(false)
  const pending = useAsync(() => api.get('/api/alerts?status=pending'), [location.pathname])
  useEffect(() => {
    const refresh = () => pending.reload(true)
    window.addEventListener('vw-alerts-changed', refresh)
    return () => window.removeEventListener('vw-alerts-changed', refresh)
  }, [pending.reload])

  useEffect(() => {
    const onResize = () => { if (window.innerWidth < 1180) setCollapsed(true) }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const current = NAV.find((n) => (n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to))) || NAV[0]
  const pendingCount = pending.data ? pending.data.length : 0
  const showFilters = ['/', '/map', '/data', '/alerts'].includes(current.to)

  return (
    <div className="print-root flex h-full overflow-hidden">
      <aside className={`no-print flex shrink-0 flex-col bg-navy-800 text-slate-200 transition-[width] duration-200 ${collapsed ? 'w-[68px]' : 'w-60'}`}>
        <Logo collapsed={collapsed} />
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2" aria-label="Điều hướng chính">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} title={label}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium ${isActive ? 'bg-brand-600 text-white shadow' : 'text-slate-300 hover:bg-navy-700 hover:text-white'}`}>
              <Icon size={18} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
              {!collapsed && to === '/alerts' && pendingCount > 0 && <span className="ml-auto rounded-full bg-amber-400 px-1.5 text-xs font-bold text-navy-900">{pendingCount}</span>}
            </NavLink>
          ))}
        </nav>
        <button onClick={() => setCollapsed((c) => !c)} className="m-2 flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-navy-700"
          aria-label={collapsed ? 'Mở rộng thanh điều hướng' : 'Thu gọn thanh điều hướng'}>
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}{!collapsed && 'Thu gọn'}
        </button>
      </aside>

      <div className="print-root flex min-w-0 flex-1 flex-col">
        <div className="no-print flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-amber-300 bg-amber-100 px-4 py-1.5 text-xs text-amber-900">
          <SampleTag />
          <span>Công cụ hỗ trợ giám sát điều kiện môi trường. Không chẩn đoán bệnh, không dự đoán ca bệnh, không kết luận có dịch hay có véc-tơ.</span>
        </div>
        <header className="no-print flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-5 py-3">
          <h1 className="mr-auto text-lg font-semibold text-slate-900">{current.title}</h1>
          {showFilters && (
            <>
              <label className="flex items-center gap-2 text-xs font-medium text-slate-500">Khu vực
                <select className="input !w-40 !py-1.5" value={areaId} onChange={(e) => setAreaId(e.target.value)}>
                  <option value="">Tất cả khu vực</option>
                  {meta.areas.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.code})</option>)}
                </select>
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-slate-500">Thời gian
                <select className="input !w-40 !py-1.5" value={days} onChange={(e) => setDays(Number(e.target.value))}>
                  <option value={7}>7 ngày gần nhất</option>
                  <option value={14}>14 ngày gần nhất</option>
                  <option value={30}>30 ngày gần nhất</option>
                </select>
              </label>
            </>
          )}
          <div className="hidden items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800 lg:flex" title="Ngày dữ liệu thời tiết mới nhất trong CSDL">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />Dữ liệu đến {fmtDate(meta.data.latest_date)}
          </div>
          <button onClick={() => navigate('/alerts?status=pending')} className="relative rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-50" aria-label={`${pendingCount} đề xuất chờ phê duyệt`} title="Đề xuất chờ phê duyệt">
            <Bell size={17} />
            {pendingCount > 0 && <span className="absolute -right-1.5 -top-1.5 rounded-full bg-red-600 px-1.5 text-[11px] font-bold text-white">{pendingCount}</span>}
          </button>
          <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
            <div className="text-right leading-tight">
              <div className="max-w-36 truncate text-sm font-medium text-slate-800">{user.full_name}</div>
              <div className="text-xs text-slate-500">{user.role_label}</div>
            </div>
            <button onClick={logout} className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-50" aria-label="Đăng xuất" title="Đăng xuất"><LogOut size={16} /></button>
          </div>
        </header>

        <main className="print-root min-h-0 flex-1 overflow-y-auto p-5"><Outlet /></main>

        <footer className="no-print flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-200 bg-white px-5 py-2 text-xs text-slate-500">
          <button className="font-medium text-slate-600 underline-offset-2 hover:underline" onClick={() => setShowBuild(true)}>{meta.app.name} v{meta.app.version}</button>
          <span>Scoring: {meta.scoring.version}</span>
          <span>Dữ liệu: {fmtDate(meta.data.earliest_date)} → {fmtDate(meta.data.latest_date)}</span>
          <span>Agent: {meta.agent.llm_description}</span>
          <span className="ml-auto flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500" />API hoạt động</span>
        </footer>
      </div>

      {showBuild && (
        <Modal title="Thông tin bản dựng" onClose={() => setShowBuild(false)}>
          <dl className="grid grid-cols-[160px_1fr] gap-y-2 text-sm">
            <dt className="text-slate-500">Ứng dụng</dt><dd>{meta.app.name} v{meta.app.version}</dd>
            <dt className="text-slate-500">Phiên bản scoring</dt><dd>{meta.scoring.version}</dd>
            <dt className="text-slate-500">Chế độ Agent/LLM</dt><dd>{meta.agent.llm_description}</dd>
            <dt className="text-slate-500">Bản ghi dữ liệu</dt><dd>{meta.data.counts.weather} thời tiết · {meta.data.counts.water_points} điểm nước đọng · {meta.data.counts.surveys} khảo sát</dd>
            <dt className="text-slate-500">Loại dữ liệu</dt><dd>{meta.data.label}</dd>
          </dl>
          <p className="mt-3 text-xs text-slate-500">Không hiển thị khóa bí mật, token hay thông tin xác thực ở đây.</p>
        </Modal>
      )}
    </div>
  )
}
