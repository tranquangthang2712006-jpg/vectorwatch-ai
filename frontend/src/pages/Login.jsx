import { useState } from 'react'
import { LogIn } from 'lucide-react'
import { useApp, useAsync } from '../lib/context.jsx'
import { api } from '../lib/api.js'
import { Button, Field, Notice, SampleTag } from '../components/ui.jsx'

export default function Login() {
  const { login } = useApp()
  const accounts = useAsync(() => api.get('/api/auth/demo-accounts'), [])
  const [email, setEmail] = useState('analyst@vectorwatch.local')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!password) { setError('Hãy nhập mật khẩu demo (xem README hoặc file .env).'); return }
    setLoading(true); setError(null)
    try { await login(email, password) } catch (err) { setError(err.message) } finally { setLoading(false) }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-navy-900 via-navy-800 to-brand-700 p-4">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl bg-white shadow-2xl md:grid-cols-2">
        <div className="hidden flex-col justify-between bg-navy-800 p-8 text-slate-200 md:flex">
          <div>
            <div className="text-2xl font-bold text-white">VectorWatch <span className="text-sky-300">AI</span></div>
            <p className="mt-2 text-sm text-slate-300">Nền tảng hỗ trợ giám sát điều kiện môi trường thuận lợi cho véc-tơ truyền bệnh (MVP: Aedes).</p>
            <ul className="mt-6 space-y-2 text-sm text-slate-300">
              <li>• Phân tích thời tiết, điểm nước đọng và khảo sát thực địa</li>
              <li>• Điểm ESS/PIS tính bằng service xác định, có phiên bản</li>
              <li>• Orchestrator + 4 Agent, có nhật ký gọi công cụ</li>
              <li>• Đề xuất kiểm tra phải được con người phê duyệt</li>
            </ul>
          </div>
          <p className="text-xs text-slate-400">Không chẩn đoán bệnh, không dự đoán ca bệnh, không kết luận có dịch hay có véc-tơ.</p>
        </div>
        <form onSubmit={submit} className="space-y-4 p-8">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">Đăng nhập</h1>
            <div className="mt-1"><SampleTag /></div>
          </div>
          <Field label="Tài khoản demo" hint="Mỗi tài khoản có một vai trò và quyền khác nhau.">
            <select className="input" value={email} onChange={(e) => setEmail(e.target.value)} disabled={accounts.loading}>
              {(accounts.data || [{ email, role_label: '' }]).map((a) => <option key={a.email} value={a.email}>{a.email}{a.role_label ? ` — ${a.role_label}` : ''}</option>)}
            </select>
          </Field>
          <Field label="Mật khẩu" hint="Mật khẩu demo chung cho cả 4 tài khoản (xem README).">
            <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
          </Field>
          {accounts.error && <Notice tone="danger">{accounts.error}</Notice>}
          {error && <Notice tone="danger">{error}</Notice>}
          <Button type="submit" icon={LogIn} loading={loading} className="w-full">Đăng nhập</Button>
        </form>
      </div>
    </div>
  )
}
