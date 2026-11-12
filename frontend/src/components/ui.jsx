import { useEffect } from 'react'
import { AlertTriangle, Inbox, Loader2, X } from 'lucide-react'
import { ESS_LEVELS, PIS_LEVELS, essKey } from '../lib/format.js'

export function Card({ title, subtitle, actions, children, className = '', bodyClass = 'p-4' }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

const BUTTON_STYLES = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-slate-300',
  secondary: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-slate-300',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-slate-300',
  ghost: 'text-brand-700 hover:bg-brand-50 disabled:text-slate-400',
}
export function Button({ variant = 'primary', size = 'md', loading = false, icon: Icon, children, className = '', ...props }) {
  const sizes = { sm: 'px-2.5 py-1.5 text-xs', md: 'px-3.5 py-2 text-sm' }
  return (
    <button {...props} disabled={props.disabled || loading}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors ${sizes[size]} ${BUTTON_STYLES[variant]} ${className}`}>
      {loading ? <Loader2 size={15} className="spin" /> : Icon ? <Icon size={15} /> : null}
      {children}
    </button>
  )
}

export function Badge({ color = '#64748b', children, solid = false, title }) {
  const style = solid ? { backgroundColor: color, color: '#fff', borderColor: color } : { color, borderColor: `${color}66`, backgroundColor: `${color}14` }
  return <span title={title} style={style} className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold">{children}</span>
}

export function EssBadge({ cls, value }) {
  const level = ESS_LEVELS[essKey(cls)]
  return <Badge color={level.color} solid>{value !== undefined && value !== null ? `${value} · ` : ''}{level.label}</Badge>
}
export function PisBadge({ cls, value }) {
  if (!cls) return <Badge color="#94a3b8">Chưa tính</Badge>
  const level = PIS_LEVELS[typeof cls === 'string' ? cls : cls.key]
  return <Badge color={level.color}>{value !== undefined && value !== null ? `${value} · ` : ''}{level.label}</Badge>
}

const TASK_COLORS = { queued: '#64748b', running: '#1d5fd1', waiting_approval: '#b45309', completed: '#15803d', failed: '#b91c1c', cancelled: '#475569' }
export const TaskStatusBadge = ({ status, label }) => <Badge color={TASK_COLORS[status] || '#64748b'}>{label}</Badge>

const ALERT_STATUS_COLORS = { pending: '#b45309', approved: '#15803d', rejected: '#b91c1c', needs_revision: '#7c3aed' }
export const AlertStatusBadge = ({ status, label }) => <Badge color={ALERT_STATUS_COLORS[status] || '#64748b'}>{label}</Badge>
const SEVERITY_COLORS = { high: '#c81e1e', medium: '#d97706', low: '#16a34a', info: '#0369a1' }
export const SeverityBadge = ({ severity, label }) => <Badge color={SEVERITY_COLORS[severity] || '#64748b'} solid>{label}</Badge>

export function Loading({ label = 'Đang tải dữ liệu…', className = 'py-10' }) {
  return (
    <div role="status" className={`flex flex-col items-center justify-center gap-2 text-slate-500 ${className}`}>
      <Loader2 className="spin" size={22} />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function EmptyState({ title, hint, action, icon: Icon = Inbox }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <div className="rounded-full bg-slate-100 p-3 text-slate-400"><Icon size={22} /></div>
      <div className="text-sm font-semibold text-slate-700">{title}</div>
      {hint && <div className="max-w-md text-sm text-slate-500">{hint}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-4 py-8 text-center">
      <div className="rounded-full bg-red-50 p-3 text-red-500"><AlertTriangle size={22} /></div>
      <div className="text-sm font-semibold text-slate-800">Không tải được dữ liệu</div>
      <div className="max-w-md text-sm text-slate-600">{message}</div>
      {onRetry && <Button variant="secondary" size="sm" onClick={() => onRetry()}>Thử lại</Button>}
    </div>
  )
}

export function Modal({ title, onClose, children, footer, wide = false }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[1500] flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 sm:p-8" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div role="dialog" aria-modal="true" aria-label={title} className={`w-full ${wide ? 'max-w-5xl' : 'max-w-xl'} rounded-xl bg-white shadow-2xl`}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-slate-500 hover:bg-slate-100" aria-label="Đóng"><X size={18} /></button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div role="tablist" className="flex flex-wrap gap-1 border-b border-slate-200">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}
          className={`-mb-px border-b-2 px-3.5 py-2 text-sm font-medium ${value === t.key ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
          {t.label}{t.count !== undefined && <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 text-xs text-slate-600">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Field({ label, hint, error, children, required }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold text-slate-600">{label}{required && <span className="text-red-600"> *</span>}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs font-medium text-red-600">{error}</span>}
    </label>
  )
}

export function Notice({ tone = 'info', children, className = '' }) {
  const tones = {
    info: 'border-sky-200 bg-sky-50 text-sky-900',
    warning: 'border-amber-300 bg-amber-50 text-amber-900',
    danger: 'border-red-200 bg-red-50 text-red-900',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    neutral: 'border-slate-200 bg-slate-50 text-slate-700',
  }
  return <div className={`rounded-lg border px-3 py-2 text-sm ${tones[tone]} ${className}`}>{children}</div>
}

export function SampleTag({ className = '' }) {
  return <span className={`inline-flex items-center rounded border border-amber-400 bg-amber-50 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-800 ${className}`}>Dữ liệu mẫu / giả lập</span>
}

export function NoPermission({ action }) {
  return <Notice tone="neutral">Vai trò của bạn chỉ được xem, không có quyền {action}. Đăng nhập bằng tài khoản có quyền phù hợp nếu cần.</Notice>
}
