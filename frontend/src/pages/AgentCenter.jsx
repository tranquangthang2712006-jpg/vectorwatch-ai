import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Ban, Bot, Check, CheckCircle2, XCircle, CircleDashed, Clock, Loader2, Plus, RotateCcw, SkipForward, UserCheck, X } from 'lucide-react'
import { useApp, useAsync, useToast } from '../lib/context.jsx'
import { api } from '../lib/api.js'
import { addDays, duration, fmtDate, fmtDateTime, fmtTime } from '../lib/format.js'
import { Badge, Button, Card, EmptyState, ErrorState, Field, Loading, Modal, NoPermission, Notice, Tabs, TaskStatusBadge } from '../components/ui.jsx'
import AssistantPanel from '../components/AssistantPanel.jsx'

const STEP_STYLE = {
  pending: { color: '#94a3b8', label: 'Chưa chạy', icon: CircleDashed },
  running: { color: '#1d5fd1', label: 'Đang chạy', icon: Loader2 },
  success: { color: '#15803d', label: 'Thành công', icon: Check },
  waiting: { color: '#b45309', label: 'Đang chờ', icon: UserCheck },
  failed: { color: '#b91c1c', label: 'Thất bại', icon: X },
  skipped: { color: '#64748b', label: 'Bỏ qua', icon: SkipForward },
  cancelled: { color: '#475569', label: 'Đã hủy', icon: Ban },
  partial: { color: '#0369a1', label: 'Đang theo dõi', icon: Clock },
}
const SOURCES = [['weather', 'Thời tiết'], ['water', 'Điểm nước đọng'], ['survey', 'Khảo sát thực địa']]
const ACTIVE = ['queued', 'running']

function NewTaskModal({ onClose, onCreated }) {
  const { meta } = useApp()
  const latest = meta.data.latest_date
  const [step, setStep] = useState('form')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({
    objective: 'Phân tích điều kiện môi trường thuận lợi cho Aedes sau đợt mưa và đề xuất khu vực cần ưu tiên kiểm tra',
    area_ids: meta.areas.map((a) => a.id), start: latest ? addDays(latest, -6) : '', end: latest || '', species: 'aedes',
    sources: ['weather', 'water', 'survey'], notes: '', simulate_fault: 'none',
  })
  const set = (patch) => setForm((f) => ({ ...f, ...patch }))
  const toggle = (key, value) => set({ [key]: form[key].includes(value) ? form[key].filter((v) => v !== value) : [...form[key], value] })
  const problems = []
  if (form.objective.trim().length < 5) problems.push('Mô tả mục tiêu (ít nhất 5 ký tự).')
  if (!form.area_ids.length) problems.push('Chọn ít nhất một khu vực.')
  if (!form.start || !form.end || form.start > form.end) problems.push('Chọn khoảng thời gian hợp lệ.')
  if (!form.sources.length) problems.push('Chọn ít nhất một nguồn dữ liệu.')

  async function start() {
    setBusy(true); setError(null)
    try { onCreated(await api.post('/api/tasks', form)) } catch (err) { setError(err.message); setStep('form') } finally { setBusy(false) }
  }

  return (
    <Modal wide title={step === 'form' ? 'Tạo nhiệm vụ phân tích' : 'Xác nhận thông tin nhiệm vụ'} onClose={onClose}
      footer={step === 'form' ? (
        <><Button variant="secondary" onClick={onClose}>Hủy</Button><Button disabled={problems.length > 0} onClick={() => setStep('confirm')}>Tiếp tục → Xác nhận</Button></>
      ) : (
        <><Button variant="secondary" onClick={() => setStep('form')}>← Sửa lại</Button><Button loading={busy} icon={Bot} onClick={start}>Bắt đầu</Button></>
      )}>
      {error && <Notice tone="danger" className="mb-3">{error}</Notice>}
      {step === 'form' ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="md:col-span-2"><Field label="Mục tiêu phân tích" required hint="Hệ thống chỉ phân tích điều kiện môi trường; yêu cầu chẩn đoán hay dự đoán ca bệnh sẽ không được thực hiện.">
            <textarea className="input" rows={2} value={form.objective} onChange={(e) => set({ objective: e.target.value })} /></Field></div>
          <div className="md:col-span-2">
            <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-600"><span>Khu vực <span className="text-red-600">*</span> ({form.area_ids.length}/{meta.areas.length})</span>
              <span className="flex gap-3 font-medium"><button className="text-brand-700" onClick={() => set({ area_ids: meta.areas.map((a) => a.id) })}>Chọn tất cả</button><button className="text-brand-700" onClick={() => set({ area_ids: [] })}>Bỏ chọn</button></span></div>
            <div className="grid grid-cols-3 gap-1.5 rounded-lg border border-slate-200 p-2 sm:grid-cols-4 lg:grid-cols-6">
              {meta.areas.map((a) => <label key={a.id} className="flex cursor-pointer items-center gap-1.5 rounded px-1.5 py-1 text-sm hover:bg-slate-50"><input type="checkbox" checked={form.area_ids.includes(a.id)} onChange={() => toggle('area_ids', a.id)} />{a.name}</label>)}
            </div>
          </div>
          <Field label="Từ ngày" required><input type="date" className="input" value={form.start} min={meta.data.earliest_date} max={form.end} onChange={(e) => set({ start: e.target.value })} /></Field>
          <Field label="Đến ngày" required><input type="date" className="input" value={form.end} min={form.start} max={latest} onChange={(e) => set({ end: e.target.value })} /></Field>
          <Field label="Loài véc-tơ"><select className="input" value={form.species} onChange={(e) => set({ species: e.target.value })}>
            {meta.species.map((s) => <option key={s.key} value={s.key} disabled={!s.configured}>{s.label}{s.configured ? '' : ' (chưa cấu hình trong MVP)'}</option>)}</select></Field>
          <div>
            <div className="mb-1 text-xs font-semibold text-slate-600">Nguồn dữ liệu <span className="text-red-600">*</span></div>
            <div className="flex flex-wrap gap-3 rounded-lg border border-slate-200 px-3 py-2">
              {SOURCES.map(([key, label]) => <label key={key} className="flex cursor-pointer items-center gap-1.5 text-sm"><input type="checkbox" checked={form.sources.includes(key)} onChange={() => toggle('sources', key)} />{label}</label>)}
            </div>
            <div className="mt-1 text-xs text-slate-500">Nguồn không chọn sẽ được coi là thiếu dữ liệu (không tính là 0).</div>
          </div>
          <Field label="Ghi chú"><textarea className="input" rows={2} value={form.notes} onChange={(e) => set({ notes: e.target.value })} /></Field>
          <Field label="Mô phỏng lỗi công cụ (chỉ để kiểm thử)" hint="Dùng để trình diễn xử lý lỗi: lỗi được chèn vào công cụ get_weather_data.">
            <select className="input" value={form.simulate_fault} onChange={(e) => set({ simulate_fault: e.target.value })}>
              <option value="none">Không mô phỏng lỗi (chạy bình thường)</option>
              <option value="transient">Lỗi tạm thời — thất bại 1 lần rồi thành công</option>
              <option value="permanent">Lỗi kéo dài — hết số lần thử lại, nhiệm vụ thất bại</option>
            </select></Field>
          {problems.length > 0 && <Notice tone="warning" className="md:col-span-2">Cần hoàn thiện: {problems.join(' ')}</Notice>}
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <dl className="grid grid-cols-[150px_1fr] gap-y-2">
            <dt className="text-slate-500">Mục tiêu</dt><dd>{form.objective}</dd>
            <dt className="text-slate-500">Khu vực</dt><dd>{form.area_ids.length === meta.areas.length ? `Tất cả ${meta.areas.length} khu vực` : meta.areas.filter((a) => form.area_ids.includes(a.id)).map((a) => a.name).join(', ')}</dd>
            <dt className="text-slate-500">Thời gian</dt><dd>{fmtDate(form.start)} → {fmtDate(form.end)}</dd>
            <dt className="text-slate-500">Loài</dt><dd>{meta.species.find((s) => s.key === form.species)?.label}</dd>
            <dt className="text-slate-500">Nguồn dữ liệu</dt><dd>{SOURCES.filter(([k]) => form.sources.includes(k)).map(([, l]) => l).join(', ')}</dd>
            <dt className="text-slate-500">Ghi chú</dt><dd>{form.notes || '—'}</dd>
            <dt className="text-slate-500">Mô phỏng lỗi</dt><dd>{form.simulate_fault === 'none' ? 'Không' : form.simulate_fault === 'transient' ? 'Lỗi tạm thời (kiểm thử)' : 'Lỗi kéo dài (kiểm thử)'}</dd>
          </dl>
          <Notice tone="info">Orchestrator sẽ điều phối 4 Agent theo {meta.agent.workflow.length} bước. Điểm ESS/PIS do scoring service tính. Mọi đề xuất dừng ở trạng thái <b>chờ phê duyệt</b>; Agent không tự phát hành hành động ra ngoài hệ thống.</Notice>
          <Notice tone="neutral">Chế độ Agent hiện tại: <b>{meta.agent.llm_description}</b>. {meta.agent.llm_mode === 'llm' ? 'LLM chỉ phân loại ý định và diễn đạt lại; kế hoạch, công cụ và điểm số do hệ thống xác định.' : 'Việc phân loại ý định và lập kế hoạch là mô phỏng theo luật.'} Các lần gọi công cụ là thật trên dữ liệu mẫu.</Notice>
        </div>
      )}
    </Modal>
  )
}

function Timeline({ steps }) {
  return (
    <div className="overflow-x-auto"><ol className="flex min-w-[760px]">
      {steps.map((s, i) => {
        const st = STEP_STYLE[s.status] || STEP_STYLE.pending
        const Icon = st.icon
        return (
          <li key={s.key} className="flex min-w-0 flex-1 flex-col items-center text-center">
            <div className="flex w-full items-center">
              <div className="h-0.5 flex-1" style={{ backgroundColor: i === 0 ? 'transparent' : (s.status === 'pending' ? '#e2e8f0' : st.color) }} />
              <div className={`flex h-9 w-9 items-center justify-center rounded-full border-2 bg-white ${s.status === 'waiting' ? 'pulse' : ''}`} style={{ borderColor: st.color, color: st.color }}>
                <Icon size={17} className={s.status === 'running' ? 'spin' : ''} />
              </div>
              <div className="h-0.5 flex-1" style={{ backgroundColor: i === steps.length - 1 ? 'transparent' : (steps[i + 1].status === 'pending' ? '#e2e8f0' : (STEP_STYLE[steps[i + 1].status] || STEP_STYLE.pending).color) }} />
            </div>
            <div className="mt-1.5 px-1 text-xs font-semibold text-slate-800">{i + 1}. {s.label}</div>
            <div className="text-[11px]" style={{ color: st.color }}>{st.label}</div>
            <div className="text-[11px] text-slate-400">{s.started_at ? fmtTime(s.started_at) : ''}</div>
          </li>
        )
      })}
    </ol></div>
  )
}

function TaskDetail({ taskId, onChanged }) {
  const { can, meta } = useApp()
  const toast = useToast()
  const [task, setTask] = useState(null)
  const [error, setError] = useState(null)
  const [openStep, setOpenStep] = useState(null)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const lastStatus = useRef(null)
  const [pollKey, setPollKey] = useState(0)

  useEffect(() => {
    let alive = true
    let timer
    async function tick() {
      try {
        const t = await api.get(`/api/tasks/${taskId}`)
        if (!alive) return
        setTask(t); setError(null)
        if (lastStatus.current && lastStatus.current !== t.status) onChanged()
        lastStatus.current = t.status
        const delay = ACTIVE.includes(t.status) ? 700 : t.status === 'waiting_approval' ? 4000 : null
        if (delay) timer = setTimeout(tick, delay)
      } catch (err) { if (alive) setError(err.message) }
    }
    tick()
    return () => { alive = false; clearTimeout(timer) }
  }, [taskId, pollKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const agents = useMemo(() => {
    if (!task) return []
    const groups = new Map()
    task.steps.forEach((s) => { if (!groups.has(s.agent)) groups.set(s.agent, []); groups.get(s.agent).push(s) })
    return [...groups.entries()].map(([name, steps]) => {
      const has = (st) => steps.some((s) => s.status === st)
      const urgent = ['failed', 'running', 'waiting', 'cancelled'].find(has)
      const allDone = steps.every((s) => ['success', 'skipped'].includes(s.status))
      const status = urgent || (allDone ? (has('success') ? 'success' : 'skipped') : has('success') ? 'partial' : 'pending')
      const started = steps.map((s) => s.started_at).filter(Boolean).sort()[0]
      const ended = steps.every((s) => s.ended_at) ? steps.map((s) => s.ended_at).sort().slice(-1)[0] : null
      return { name, steps, status, started, ended, calls: task.tool_calls.filter((c) => c.agent === name).length }
    })
  }, [task])

  if (error) return <Card><ErrorState message={error} /></Card>
  if (!task) return <Card><Loading label="Đang tải nhiệm vụ…" /></Card>

  async function act(fn, okMessage) {
    setBusy(true)
    try { setTask(await fn()); toast.success(okMessage); onChanged(); setPollKey((k) => k + 1) } catch (err) { toast.error(err.message) } finally { setBusy(false) }
  }
  const retry = () => act(() => api.post(`/api/tasks/${task.id}/retry`), 'Đã đưa nhiệm vụ vào chạy lại.')
  const cancel = () => act(() => api.post(`/api/tasks/${task.id}/cancel`, { reason }), 'Đã ghi nhận yêu cầu hủy nhiệm vụ.').then(() => setCancelOpen(false))
  const roles = { 'Orchestrator': 'Phân loại yêu cầu, lập kế hoạch, điều phối và tổng hợp', 'Data Agent': 'Truy xuất, kiểm tra, chuẩn hóa dữ liệu', 'Environmental Analysis Agent': 'Tạo đặc trưng, gọi scoring service ESS/PIS', 'Geospatial Agent': 'Liên kết kết quả với vị trí, chuẩn bị lớp bản đồ', 'Risk & Alert Agent': 'Xếp hạng ưu tiên và tạo đề xuất', 'Con người (người duyệt)': 'Phê duyệt / từ chối / yêu cầu chỉnh sửa đề xuất' }
  const p = task.params

  return (
    <div className="space-y-4">
      <Card title={task.objective} subtitle={`${task.id} · tạo bởi ${task.created_by} lúc ${fmtDateTime(task.created_at)}`}
        actions={<>
          <TaskStatusBadge status={task.status} label={task.status_label} />
          {task.status === 'failed' && <Button size="sm" icon={RotateCcw} loading={busy} disabled={!can('task.create')} onClick={retry}>Thử lại</Button>}
          {['queued', 'running', 'waiting_approval'].includes(task.status) && <Button size="sm" variant="secondary" icon={Ban} disabled={!can('task.create')} onClick={() => setCancelOpen(true)}>Hủy nhiệm vụ</Button>}
        </>}>
        <Timeline steps={task.steps} />
        {task.status === 'failed' && task.error && (
          <Notice tone="danger" className="mt-4"><b>Nhiệm vụ thất bại.</b> {task.error.message} <span className="block text-xs">trace_id: {task.trace_id}</span></Notice>
        )}
        {task.status === 'cancelled' && <Notice tone="neutral" className="mt-4">Đã hủy bởi {task.cancelled_by || '—'}{task.ended_at ? ` lúc ${fmtDateTime(task.ended_at)}` : ''}. Lý do: {task.cancel_reason || 'không ghi'}.</Notice>}
        {task.status === 'waiting_approval' && (
          <Notice tone="warning" className="mt-4">Workflow đang dừng ở bước <b>Chờ phê duyệt</b>: {task.result?.alert_codes.length} đề xuất cần quyết định của người có thẩm quyền. <Link className="font-semibold underline" to="/alerts?status=pending">Mở trang phê duyệt →</Link></Notice>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Trạng thái (state)" className="xl:col-span-1">
          <dl className="grid grid-cols-[130px_1fr] gap-y-1.5 text-sm">
            <dt className="text-slate-500">task_id</dt><dd className="break-all font-mono text-xs">{task.id}</dd>
            <dt className="text-slate-500">trace_id</dt><dd className="break-all font-mono text-xs">{task.trace_id}</dd>
            <dt className="text-slate-500">Trạng thái</dt><dd>{task.status_label}</dd>
            <dt className="text-slate-500">Bước hiện tại</dt><dd>{task.current_step_label || (task.status === 'completed' ? 'Hoàn tất' : '—')}</dd>
            <dt className="text-slate-500">Bước tiếp theo</dt><dd>{task.next_step_label || '—'}</dd>
            <dt className="text-slate-500">Số lần thử lại</dt><dd>{task.retry_count} lần gọi lại công cụ{p.rerun_count > 0 && ` · ${p.rerun_count} lần chạy lại nhiệm vụ`}</dd>
            <dt className="text-slate-500">Checkpoint</dt><dd>{task.checkpoint ? task.steps.find((s) => s.key === task.checkpoint)?.label : '—'}</dd>
            <dt className="text-slate-500">Bắt đầu / kết thúc</dt><dd>{fmtTime(task.started_at)} / {fmtTime(task.ended_at)}</dd>
            <dt className="text-slate-500">Phạm vi</dt><dd>{p.area_ids.length} khu vực · {fmtDate(p.start)} → {fmtDate(p.end)} · {p.species}</dd>
            <dt className="text-slate-500">Nguồn dữ liệu</dt><dd>{SOURCES.filter(([k]) => p.sources.includes(k)).map(([, l]) => l).join(', ')}</dd>
            <dt className="text-slate-500">Ghi chú</dt><dd>{p.notes || '—'}</dd>
            <dt className="text-slate-500">Chế độ LLM</dt><dd>{task.llm_description}</dd>
            {p.simulate_fault !== 'none' && <><dt className="text-slate-500">Mô phỏng lỗi</dt><dd><Badge color="#b45309">{p.simulate_fault === 'transient' ? 'Lỗi tạm thời' : 'Lỗi kéo dài'}</Badge></dd></>}
          </dl>
        </Card>
        <Card title="Các Agent" subtitle="Nhấn một bước để xem chi tiết kết quả" className="xl:col-span-2" bodyClass="p-3">
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {agents.map((a) => {
              const st = STEP_STYLE[a.status]
              return (
                <div key={a.name} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div><div className="text-sm font-semibold text-slate-900">{a.name}</div><div className="text-xs text-slate-500">{roles[a.name]}</div></div>
                    <Badge color={st.color}>{st.label}</Badge>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-slate-500">
                    <span className="inline-flex items-center gap-1"><Clock size={11} />{a.started ? `${fmtTime(a.started)} → ${a.ended ? fmtTime(a.ended) : '…'}` : 'chưa bắt đầu'}</span>
                    <span>{a.calls} lần gọi công cụ</span>
                  </div>
                  <ul className="mt-2 space-y-1.5">
                    {a.steps.map((s) => (
                      <li key={s.key}>
                        <button className="w-full rounded border border-slate-100 bg-slate-50 px-2 py-1.5 text-left text-xs hover:border-brand-500" onClick={() => setOpenStep(s)}>
                          <span className="font-semibold" style={{ color: STEP_STYLE[s.status].color }}>{s.label}: </span>
                          <span className="text-slate-700">{s.summary || STEP_STYLE[s.status].label}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        </Card>
      </div>

      <Card title="Tool-call log" subtitle="Mọi lần gọi công cụ (kể cả lần thất bại) do máy chủ ghi lại khi thực thi; input đã làm sạch" bodyClass="p-0">
        {task.tool_calls.length === 0 ? <EmptyState title="Chưa có lần gọi công cụ nào" hint="Log xuất hiện khi các Agent bắt đầu chạy." /> : (
          <div className="max-h-96 overflow-auto">
            <table className="w-full">
              <thead className="sticky top-0 border-b border-slate-200 bg-slate-50"><tr><th className="th">Thời gian</th><th className="th">Agent</th><th className="th">Công cụ</th><th className="th">Lần</th><th className="th">Input (đã làm sạch)</th><th className="th">Output tóm tắt</th><th className="th">ms</th><th className="th">Trạng thái</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {task.tool_calls.map((c) => (
                  <tr key={c.id} className={c.status === 'failed' ? 'bg-red-50/60' : c.status === 'retrying' ? 'bg-amber-50/60' : ''}>
                    <td className="td whitespace-nowrap text-xs">{fmtTime(c.started_at)}</td>
                    <td className="td text-xs">{c.agent}</td>
                    <td className="td break-all font-mono text-[11px]">{c.tool}</td>
                    <td className="td num">{c.attempt}</td>
                    <td className="td max-w-[190px]"><code className="line-clamp-2 break-all text-[11px] text-slate-600" title={JSON.stringify(c.input)}>{JSON.stringify(c.input)}</code></td>
                    <td className="td min-w-44 text-xs">{c.output?.summary || '—'}{c.error_message && <div className="text-red-700">[{c.error_code}] {c.error_message}</div>}</td>
                    <td className="td num text-xs">{c.duration_ms}</td>
                    <td className="td"><Badge color={c.status === 'success' ? '#15803d' : c.status === 'retrying' ? '#b45309' : '#b91c1c'}>{c.status === 'success' ? 'Thành công' : c.status === 'retrying' ? 'Lỗi, thử lại' : 'Thất bại'}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {task.result && (
        <Card title="Kết quả cuối" subtitle={`Tạo lúc ${fmtDateTime(task.result.generated_at)} · scoring ${task.result.scoring_version} · ${task.result.summary_generated_by}`}>
          <p className="text-sm text-slate-800">{task.result.summary}</p>
          {task.result.ranking.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">{task.result.ranking.slice(0, 6).map((r) => <Badge key={r.area_id} color="#334155">#{r.rank} {r.area_code} · PIS {r.pis} · {r.pis_class}</Badge>)}</div>
          )}
          <div className="mt-3 grid grid-cols-1 gap-3 text-xs text-slate-600 md:grid-cols-2">
            <div><b>Nguồn dữ liệu:</b> {task.result.data_sources.join('; ') || '—'}<br /><b>Kỳ:</b> {fmtDate(task.result.period.start)} → {fmtDate(task.result.period.end)}</div>
            <div><b>Phần còn thiếu:</b> {task.result.missing.length === 0 ? 'Không' : <ul className="list-disc pl-4">{task.result.missing.slice(0, 6).map((m, i) => <li key={i}>{m}</li>)}</ul>}</div>
          </div>
          {task.result.verification && (
            <div className="mt-3 rounded-lg border border-slate-200 p-3 text-xs">
              <div className="mb-1.5 font-semibold text-slate-700">Orchestrator xác minh kết quả trước khi chuyển sang phê duyệt</div>
              <ul className="grid grid-cols-1 gap-1 md:grid-cols-2">{task.result.verification.map((c) => (
                <li key={c.key} className="flex items-start gap-1.5">{c.passed ? <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-emerald-600" /> : <XCircle size={13} className="mt-0.5 shrink-0 text-red-600" />}<span><b>{c.label}:</b> {c.detail}</span></li>
              ))}</ul>
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Link to="/map"><Button variant="secondary" size="sm">Xem trên bản đồ</Button></Link>
            {task.result.run_ids[0] && <Link to={`/analysis?run=${task.result.run_ids[0]}`}><Button variant="secondary" size="sm">Mở phân tích chi tiết</Button></Link>}
            <Link to="/alerts"><Button variant="secondary" size="sm">Cảnh báo & phê duyệt ({task.result.alert_codes.length})</Button></Link>
            <Link to="/reports"><Button variant="secondary" size="sm">Tạo báo cáo</Button></Link>
          </div>
          <p className="mt-3 text-xs text-slate-500">{task.result.notice}</p>
        </Card>
      )}

      {openStep && (
        <Modal title={`${openStep.agent} — ${openStep.label}`} onClose={() => setOpenStep(null)}>
          <div className="space-y-2 text-sm">
            <div className="flex flex-wrap gap-2"><Badge color={STEP_STYLE[openStep.status].color}>{STEP_STYLE[openStep.status].label}</Badge><span className="text-xs text-slate-500">{fmtTime(openStep.started_at)} → {fmtTime(openStep.ended_at)} ({duration(openStep.started_at, openStep.ended_at)})</span></div>
            <p>{openStep.summary || 'Chưa có kết quả.'}</p>
            {openStep.detail?.warnings?.length > 0 && <Notice tone="warning"><ul className="list-disc pl-4">{openStep.detail.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></Notice>}
            {openStep.detail && <pre className="max-h-72 overflow-auto rounded-lg bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">{JSON.stringify(openStep.detail, null, 2)}</pre>}
          </div>
        </Modal>
      )}
      {cancelOpen && (
        <Modal title="Xác nhận hủy nhiệm vụ" onClose={() => setCancelOpen(false)}
          footer={<><Button variant="secondary" onClick={() => setCancelOpen(false)}>Không hủy</Button><Button variant="danger" loading={busy} onClick={cancel}>Xác nhận hủy</Button></>}>
          <p className="mb-3 text-sm text-slate-700">Nhiệm vụ {task.id} sẽ dừng ở bước hiện tại. Thao tác được ghi lại kèm tên bạn và thời gian. Các đề xuất đã tạo (nếu có) vẫn giữ nguyên để người duyệt xử lý.</p>
          <Field label="Lý do hủy (tùy chọn)"><textarea className="input" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        </Modal>
      )}
      <p className="text-xs text-slate-500">Workflow: {meta.agent.workflow.map((w) => w.label).join(' → ')}. Tối đa {meta.agent.max_tool_retries} lần thử lại cho mỗi lần gọi công cụ.</p>
    </div>
  )
}

export default function AgentCenter() {
  const { can } = useApp()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const [showNew, setShowNew] = useState(params.get('new') === '1' && can('task.create'))
  const tasks = useAsync(() => api.get('/api/tasks'), [])
  const selected = params.get('task') || tasks.data?.[0]?.id || null

  const view = params.get('view') === 'chat' ? 'chat' : 'tasks'
  function select(id) { setParams({ task: id }, { replace: true }) }

  const tabs = (
    <Tabs value={view} onChange={(v) => setParams(v === 'chat' ? { view: 'chat' } : {}, { replace: true })}
      tabs={[{ key: 'tasks', label: 'Nhiệm vụ workflow' }, { key: 'chat', label: 'Trợ lý hỏi đáp' }]} />
  )
  if (view === 'chat') {
    return (
      <div className="space-y-4">
        {tabs}
        <AssistantPanel onTaskCreated={(task) => { tasks.reload(true); setParams({ task: task.id }, { replace: true }) }} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
    {tabs}
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[300px_1fr]">
      <div className="space-y-3">
        <Button icon={Plus} className="w-full" disabled={!can('task.create')} onClick={() => setShowNew(true)}>Tạo nhiệm vụ</Button>
        {!can('task.create') && <NoPermission action="tạo, hủy hoặc thử lại nhiệm vụ" />}
        <Card title="Nhiệm vụ gần đây" bodyClass="p-0">
          {tasks.loading ? <Loading /> : tasks.error ? <ErrorState message={tasks.error} onRetry={tasks.reload} /> : tasks.data.length === 0 ? (
            <EmptyState title="Chưa có nhiệm vụ nào" hint="Nhấn “Tạo nhiệm vụ” để Orchestrator bắt đầu một lần phân tích." />
          ) : (
            <ul className="max-h-[70vh] divide-y divide-slate-100 overflow-y-auto">
              {tasks.data.map((t) => (
                <li key={t.id}>
                  <button onClick={() => select(t.id)} className={`w-full px-3 py-2.5 text-left hover:bg-brand-50 ${selected === t.id ? 'border-l-4 border-brand-600 bg-brand-50' : 'border-l-4 border-transparent'}`}>
                    <div className="flex items-center justify-between gap-2"><span className="font-mono text-[11px] text-slate-600">{t.id}</span><TaskStatusBadge status={t.status} label={t.status_label} /></div>
                    <div className="mt-1 line-clamp-2 text-sm text-slate-800">{t.objective}</div>
                    <div className="mt-0.5 text-[11px] text-slate-500">{fmtDateTime(t.created_at)}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <div className="min-w-0">
        {selected ? <TaskDetail key={selected} taskId={selected} onChanged={() => tasks.reload(true)} /> : !tasks.loading && (
          <Card><EmptyState icon={Bot} title="Chọn hoặc tạo một nhiệm vụ" hint="Tại đây bạn theo dõi Orchestrator điều phối Data Agent, Environmental Analysis Agent, Geospatial Agent và Risk & Alert Agent, kèm nhật ký gọi công cụ." /></Card>
        )}
      </div>
      {showNew && <NewTaskModal onClose={() => { setShowNew(false); if (params.get('new')) setParams({}, { replace: true }) }}
        onCreated={(task) => { setShowNew(false); toast.success(`Đã tạo ${task.id}. Workflow đang chạy.`); tasks.reload(true); select(task.id) }} />}
    </div>
    </div>
  )
}
