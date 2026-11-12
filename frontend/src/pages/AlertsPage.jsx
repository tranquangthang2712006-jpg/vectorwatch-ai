import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Check, MapPinned, PencilLine, Send, X } from 'lucide-react'
import { useApp, useAsync, useToast } from '../lib/context.jsx'
import { api, qs } from '../lib/api.js'
import { fmtDateTime, fmtNum } from '../lib/format.js'
import { AlertStatusBadge, Badge, Button, Card, EmptyState, ErrorState, Field, Loading, Modal, Notice, SeverityBadge } from '../components/ui.jsx'

const HISTORY_LABELS = { created: 'Tạo đề xuất', updated: 'Cập nhật số liệu', approved: 'Phê duyệt', rejected: 'Từ chối', revision_requested: 'Yêu cầu chỉnh sửa', resubmitted: 'Chỉnh sửa và gửi lại' }
const DECISIONS = {
  approve: { label: 'Phê duyệt', variant: 'success', icon: Check, noteRequired: false, confirm: 'Phê duyệt đề xuất này? Đề xuất sẽ chuyển sang “Đã phê duyệt” và xuất hiện trong báo cáo như khuyến nghị có hiệu lực.' },
  reject: { label: 'Từ chối', variant: 'danger', icon: X, noteRequired: true, confirm: 'Từ chối đề xuất này? Cần ghi rõ lý do.' },
  request_revision: { label: 'Yêu cầu chỉnh sửa', variant: 'secondary', icon: PencilLine, noteRequired: true, confirm: 'Trả lại đề xuất để người tạo chỉnh sửa? Cần ghi rõ nội dung cần sửa.' },
}

function Detail({ alertId, onChanged }) {
  const { can, user } = useApp()
  const toast = useToast()
  const { data: alert, loading, error, reload } = useAsync(() => api.get(`/api/alerts/${alertId}`), [alertId])
  const [decision, setDecision] = useState(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState(null)
  const [revised, setRevised] = useState('')
  useEffect(() => { if (alert) setRevised(alert.recommended_action) }, [alert])

  if (loading) return <Card><Loading /></Card>
  if (error) return <Card><ErrorState message={error} onRetry={reload} /></Card>

  async function submitDecision() {
    const spec = DECISIONS[decision]
    if (spec.noteRequired && note.trim().length < 5) { setFormError('Bắt buộc nhập ghi chú (ít nhất 5 ký tự) khi từ chối hoặc yêu cầu chỉnh sửa.'); return }
    setBusy(true); setFormError(null)
    try {
      await api.post(`/api/alerts/${alert.id}/decision`, { action: decision, note })
      toast.success(`Đã ghi nhận quyết định “${spec.label}” cho ${alert.code}.`)
      setDecision(null); setNote(''); reload(true); onChanged(); window.dispatchEvent(new Event('vw-alerts-changed'))
    } catch (err) { setFormError(err.message) } finally { setBusy(false) }
  }
  async function resubmit() {
    setBusy(true)
    try {
      await api.post(`/api/alerts/${alert.id}/resubmit`, { recommended_action: revised })
      toast.success(`Đã gửi lại ${alert.code} để chờ duyệt.`); reload(true); onChanged(); window.dispatchEvent(new Event('vw-alerts-changed'))
    } catch (err) { toast.error(err.message) } finally { setBusy(false) }
  }

  return (
    <Card title={`${alert.code} · ${alert.type_label}`} subtitle={`${alert.area_name} (${alert.area_code}) · tạo ${fmtDateTime(alert.created_at)} bởi ${alert.created_by}`}
      actions={<><SeverityBadge severity={alert.severity} label={`Mức ${alert.severity_label}`} /><AlertStatusBadge status={alert.status} label={alert.status_label} /></>}>
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="rounded-lg border border-slate-200 p-2"><div className="text-xs text-slate-500">ESS</div><div className="num text-xl font-bold">{fmtNum(alert.ess)}</div></div>
          <div className="rounded-lg border border-slate-200 p-2"><div className="text-xs text-slate-500">PIS</div><div className="num text-xl font-bold">{fmtNum(alert.pis)}</div></div>
          <div className="rounded-lg border border-slate-200 p-2"><div className="text-xs text-slate-500">Nguồn gốc</div><div className="text-sm font-semibold">{alert.origin === 'agent' ? 'Risk & Alert Agent' : 'Người dùng tạo'}</div></div>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-slate-900">Lý do kích hoạt</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">{alert.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-slate-900">Yếu tố đóng góp</h3>
          <div className="mt-1 overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full"><thead className="bg-slate-50"><tr><th className="th">Yếu tố</th><th className="th">Giá trị</th><th className="th">Điểm</th><th className="th">Đóng góp ESS</th></tr></thead>
              <tbody className="divide-y divide-slate-100">{alert.factors.map((f) => (
                <tr key={f.key}><td className="td">{f.label}</td>
                  <td className="td num">{f.missing ? <Badge color="#b45309">Thiếu</Badge> : `${f.key === 'survey' ? Math.round(f.value * 100) + '%' : fmtNum(f.value)} ${f.key === 'survey' ? '' : f.unit}`}</td>
                  <td className="td num">{f.missing ? '—' : f.score}</td><td className="td num">{f.missing ? '—' : `+${f.contribution}`}</td></tr>
              ))}</tbody></table>
          </div>
        </div>

        <div className="rounded-lg border border-brand-100 bg-brand-50 p-3">
          <h3 className="text-sm font-semibold text-slate-900">Đề xuất hành động <span className="font-normal text-slate-500">(chỉ có hiệu lực sau khi được phê duyệt)</span></h3>
          <p className="mt-1 text-sm text-slate-800">{alert.recommended_action}</p>
          <p className="mt-1 text-xs text-slate-500">Đơn vị dự kiến phụ trách: {alert.assignee}</p>
        </div>

        <div className="text-xs text-slate-600">
          <b>Nguồn dữ liệu:</b> {alert.sources.join('; ') || '—'}
          <div className="mt-2 flex flex-wrap gap-2">
            <Link to={`/map?area=${alert.area_id}`}><Button variant="secondary" size="sm" icon={MapPinned}>Xem trên bản đồ</Button></Link>
            {alert.run_id && <Link to={`/analysis?run=${alert.run_id}`}><Button variant="secondary" size="sm">Mở phân tích #{alert.run_id}</Button></Link>}
            {alert.task_id && <Link to={`/agent?task=${alert.task_id}`}><Button variant="secondary" size="sm">Nhiệm vụ {alert.task_id}</Button></Link>}
          </div>
        </div>

        <div className="border-t border-slate-200 pt-3">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Quyết định của người có thẩm quyền</h3>
          {alert.status === 'pending' && can('alert.approve') && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(DECISIONS).map(([key, d]) => <Button key={key} variant={d.variant} icon={d.icon} onClick={() => { setDecision(key); setNote(''); setFormError(null) }}>{d.label}</Button>)}
            </div>
          )}
          {alert.status === 'pending' && !can('alert.approve') && (
            <>
              <div className="flex flex-wrap gap-2">{Object.values(DECISIONS).map((d) => <Button key={d.label} variant="secondary" icon={d.icon} disabled title="Vai trò của bạn không có quyền phê duyệt">{d.label}</Button>)}</div>
              <Notice tone="neutral" className="mt-2">Vai trò “{user.role_label}” chỉ được xem, không có quyền phê duyệt. Tài khoản Cán bộ giám sát hoặc Quản trị mới ra quyết định được.</Notice>
            </>
          )}
          {alert.status === 'needs_revision' && (can('alert.create') ? (
            <div className="space-y-2">
              <Notice tone="warning">Người duyệt yêu cầu chỉnh sửa (xem ghi chú trong lịch sử). Cập nhật nội dung đề xuất rồi gửi lại để duyệt.</Notice>
              <Field label="Nội dung đề xuất sau chỉnh sửa"><textarea className="input" rows={3} value={revised} onChange={(e) => setRevised(e.target.value)} /></Field>
              <Button icon={Send} loading={busy} onClick={resubmit}>Gửi lại để duyệt</Button>
            </div>
          ) : <Notice tone="neutral">Đề xuất đang chờ người tạo chỉnh sửa và gửi lại.</Notice>)}
          {['approved', 'rejected'].includes(alert.status) && <Notice tone={alert.status === 'approved' ? 'success' : 'neutral'}>Đề xuất đã có quyết định cuối: <b>{alert.status_label}</b>. Xem người thực hiện và ghi chú ở lịch sử bên dưới.</Notice>}
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Lịch sử xử lý (audit log)</h3>
          <ol className="space-y-2 border-l-2 border-slate-200 pl-4">
            {alert.history.map((h) => (
              <li key={h.id} className="relative text-sm">
                <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-brand-500 ring-2 ring-white" />
                <div><b>{HISTORY_LABELS[h.action] || h.action}</b> — {h.actor} <span className="text-xs text-slate-500">({h.actor_role})</span></div>
                <div className="text-xs text-slate-500">{fmtDateTime(h.created_at)}</div>
                {h.note && <div className="mt-0.5 rounded bg-slate-50 px-2 py-1 text-xs text-slate-700">{h.note}</div>}
              </li>
            ))}
          </ol>
        </div>
      </div>

      {decision && (
        <Modal title={`${DECISIONS[decision].label} — ${alert.code}`} onClose={() => setDecision(null)}
          footer={<><Button variant="secondary" onClick={() => setDecision(null)}>Hủy</Button><Button variant={DECISIONS[decision].variant === 'secondary' ? 'primary' : DECISIONS[decision].variant} loading={busy} onClick={submitDecision}>Xác nhận {DECISIONS[decision].label.toLowerCase()}</Button></>}>
          <p className="mb-3 text-sm text-slate-700">{DECISIONS[decision].confirm}</p>
          <Field label={`Ghi chú${DECISIONS[decision].noteRequired ? '' : ' (tùy chọn)'}`} required={DECISIONS[decision].noteRequired} error={formError}>
            <textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} autoFocus placeholder={DECISIONS[decision].noteRequired ? 'Nêu rõ lý do / nội dung cần sửa' : 'Ví dụ: đồng ý, bố trí kiểm tra trong tuần'} />
          </Field>
          <p className="mt-2 text-xs text-slate-500">Quyết định được lưu kèm tên bạn ({user.full_name}), vai trò và thời gian.</p>
        </Modal>
      )}
    </Card>
  )
}

export default function AlertsPage() {
  const { areaId, days } = useApp()
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState(params.get('status') || '')
  const [severity, setSeverity] = useState('')
  const [useTime, setUseTime] = useState(false)
  const since = useTime ? new Date(Date.now() - days * 86400000).toISOString() : ''
  const list = useAsync(() => api.get(`/api/alerts${qs({ status, severity, area_id: areaId, since })}`), [status, severity, areaId, useTime, days])
  const selectedId = Number(params.get('id')) || list.data?.[0]?.id || null

  useEffect(() => {
    // Ghim cảnh báo đang xem để nó không bị đổi khi danh sách sắp xếp lại sau một quyết định.
    if (!params.get('id') && list.data?.length) setParams((prev) => { const next = new URLSearchParams(prev); next.set('id', list.data[0].id); return next }, { replace: true })
  }, [list.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const select = (id) => setParams((prev) => { const next = new URLSearchParams(prev); next.set('id', id); return next }, { replace: true })

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <Card title="Danh sách cảnh báo / đề xuất" subtitle="Đề xuất do Agent hoặc người dùng tạo; chưa có hiệu lực cho tới khi được phê duyệt" bodyClass="p-0">
        <div className="flex flex-wrap items-end gap-2 border-b border-slate-100 p-3">
          <label className="flex flex-col text-xs font-semibold text-slate-600">Trạng thái
            <select className="input mt-1 !w-44 !py-1.5" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Tất cả</option><option value="pending">Chờ phê duyệt</option><option value="needs_revision">Yêu cầu chỉnh sửa</option><option value="approved">Đã phê duyệt</option><option value="rejected">Đã từ chối</option>
            </select></label>
          <label className="flex flex-col text-xs font-semibold text-slate-600">Mức ưu tiên
            <select className="input mt-1 !w-36 !py-1.5" value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="">Tất cả</option><option value="high">Cao</option><option value="medium">Trung bình</option><option value="low">Thấp</option><option value="info">Thông tin</option>
            </select></label>
          <label className="flex items-center gap-1.5 pb-2 text-xs text-slate-600"><input type="checkbox" checked={useTime} onChange={(e) => setUseTime(e.target.checked)} />Chỉ {days} ngày gần nhất</label>
          <span className="ml-auto pb-2 text-xs text-slate-500">Khu vực: lọc ở thanh trên</span>
        </div>
        {list.loading ? <Loading /> : list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : list.data.length === 0 ? (
          <EmptyState title="Không có cảnh báo nào theo bộ lọc" hint="Cảnh báo được tạo khi chạy nhiệm vụ trong AI Agent Center hoặc khi bạn tạo yêu cầu kiểm tra từ bản đồ. Thử bỏ bớt bộ lọc."
            action={<Link to="/agent?new=1"><Button size="sm">Mở AI Agent Center</Button></Link>} />
        ) : (
          <div className="max-h-[72vh] overflow-auto">
            <table className="w-full">
              <thead className="sticky top-0 border-b border-slate-200 bg-slate-50"><tr><th className="th">Mã</th><th className="th">Khu vực</th><th className="th">Loại</th><th className="th">Trạng thái</th><th className="th">Mức</th><th className="th">PIS</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {list.data.map((a) => (
                  <tr key={a.id} onClick={() => select(a.id)} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') select(a.id) }}
                    className={`cursor-pointer hover:bg-brand-50 ${selectedId === a.id ? 'bg-brand-50' : ''}`}>
                    <td className="td whitespace-nowrap font-medium text-brand-700">{a.code}</td><td className="td whitespace-nowrap">{a.area_name}</td><td className="td min-w-36 text-xs">{a.type_label}<div className="text-[11px] text-slate-400">{fmtDateTime(a.updated_at)}</div></td>
                    <td className="td"><AlertStatusBadge status={a.status} label={a.status_label} /></td>
                    <td className="td"><SeverityBadge severity={a.severity} label={a.severity_label} /></td><td className="td num">{fmtNum(a.pis)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="min-w-0">
        {selectedId ? <Detail key={selectedId} alertId={selectedId} onChanged={() => list.reload(true)} /> : !list.loading && <Card><EmptyState title="Chọn một cảnh báo để xem chi tiết" /></Card>}
      </div>
    </div>
  )
}
