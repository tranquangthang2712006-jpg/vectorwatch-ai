import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, CheckCircle2, ChevronDown, ChevronRight, MessageSquarePlus, Send, ShieldCheck, User, XCircle } from 'lucide-react'
import { useApp, useAsync, useToast } from '../lib/context.jsx'
import { api } from '../lib/api.js'
import { fmtDate, fmtNum, fmtTime } from '../lib/format.js'
import { Badge, Button, Card, EmptyState, ErrorState, Loading, Notice } from './ui.jsx'

const STORE_KEY = 'vw_conversation'

function cell(col, value) {
  if (value === null || value === undefined || value === '') return <span className="text-slate-400">—</span>
  if (col.num && typeof value === 'number') return fmtNum(value, 2)
  return value
}

function Details({ m }) {
  const [open, setOpen] = useState(false)
  const Icon = open ? ChevronDown : ChevronRight
  return (
    <div className="mt-2 rounded-lg border border-slate-200 bg-white">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-xs font-semibold text-slate-600 hover:bg-slate-50">
        <Icon size={14} /> Cách Agent xử lý câu hỏi · {m.tool_calls.length} lần gọi công cụ · {m.verification.filter((c) => c.passed).length}/{m.verification.length} kiểm tra đạt
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-200 px-3 py-3 text-xs">
          <div>
            <div className="mb-1 font-semibold text-slate-700">Truy vết</div>
            <ol className="space-y-1">{m.trace.map((s, i) => <li key={i} className="flex gap-2"><span className="w-28 shrink-0 text-slate-500">{s.step}</span><span><b>{s.agent}:</b> {s.detail}</span></li>)}</ol>
          </div>
          {m.tool_calls.length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-slate-700">Công cụ đã gọi (chỉ đọc)</div>
              <table className="w-full"><tbody className="divide-y divide-slate-100">
                {m.tool_calls.map((c, i) => <tr key={i}><td className="py-1 pr-2">{c.agent}</td><td className="py-1 pr-2 font-mono">{c.tool}</td><td className="py-1 pr-2">{c.status === 'success' ? 'Thành công' : `${c.status} ${c.error_code || ''}`}</td><td className="py-1 text-right text-slate-500">{c.duration_ms} ms</td></tr>)}
              </tbody></table>
            </div>
          )}
          <div>
            <div className="mb-1 font-semibold text-slate-700">Xác minh trước khi trả lời</div>
            <ul className="space-y-1">{m.verification.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5">{c.passed ? <CheckCircle2 size={13} className="mt-0.5 text-emerald-600" /> : <XCircle size={13} className="mt-0.5 text-red-600" />}<span><b>{c.label}:</b> {c.detail}</span></li>
            ))}</ul>
          </div>
          <div>
            <div className="mb-1 font-semibold text-slate-700">Dữ kiện gốc (từ công cụ, trước khi diễn đạt)</div>
            <ul className="list-disc space-y-0.5 pl-4 text-slate-600">{m.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>
          </div>
          <div className="text-slate-500">Mã truy vết: <span className="font-mono">{m.trace_id}</span></div>
        </div>
      )}
    </div>
  )
}

function AssistantMessage({ m, onConfirm, busyAction }) {
  return (
    <div className="flex gap-2.5">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"><Bot size={15} /></div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
          <Badge color="#1d5fd1">{m.intent_label}</Badge>
          {m.agents.map((a) => <Badge key={a} color="#475569">{a}</Badge>)}
          <span>{fmtTime(m.created_at)}</span>
        </div>
        <div className="rounded-xl rounded-tl-sm border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm leading-relaxed text-slate-800">{m.content}</div>
        {m.guardrail_note && <Notice tone="warning" className="mt-2 text-xs"><ShieldCheck size={13} className="mr-1 inline" />{m.guardrail_note}</Notice>}
        {m.table && m.table.rows.length > 0 && (
          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600">{m.table.title}</div>
            <table className="w-full text-xs">
              <thead className="bg-slate-50"><tr>{m.table.columns.map((c) => <th key={c.key} className={`px-2.5 py-1.5 font-semibold text-slate-600 ${c.num ? 'text-right' : 'text-left'}`}>{c.label}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">{m.table.rows.slice(0, 15).map((r, i) => (
                <tr key={i}>{m.table.columns.map((c) => <td key={c.key} className={`px-2.5 py-1.5 ${c.num ? 'text-right tabular-nums' : ''}`}>{cell(c, r[c.key])}</td>)}</tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {m.action?.type === 'create_task' && (
          <div className="mt-2 rounded-lg border border-sky-200 bg-brand-50 px-3 py-2 text-xs text-slate-700">
            <div className="mb-1.5">Nhiệm vụ đề xuất: <b>{m.scope.area_codes.join(', ')}</b>, {fmtDate(m.action.params.start)} → {fmtDate(m.action.params.end)}, Aedes, đủ 3 nguồn dữ liệu. Agent không tự chạy khi chưa có xác nhận của bạn.</div>
            <Button size="sm" loading={busyAction === m.id} onClick={() => onConfirm(m)}>{m.action.label}</Button>
          </div>
        )}
        {m.links?.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{m.links.map((l) => <Link key={l.to + l.label} to={l.to}><Button variant="secondary" size="sm">{l.label}</Button></Link>)}</div>}
        <div className="mt-2 text-[11px] leading-relaxed text-slate-500">
          Phạm vi: {m.scope.area_codes.length} khu vực ({m.scope.from}), {fmtDate(m.scope.start)} → {fmtDate(m.scope.end)}
          {m.sources.length > 0 && <> · Nguồn: {m.sources.join('; ')}</>}
          {m.scoring_version && <> · scoring {m.scoring_version}</>} · {m.answer_generated_by}
          {m.limitations.length > 0 && <ul className="mt-1 list-disc pl-4">{m.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>}
        </div>
        <Details m={m} />
      </div>
    </div>
  )
}

export default function AssistantPanel({ onTaskCreated }) {
  const { meta } = useApp()
  const toast = useToast()
  const suggestions = useAsync(() => api.get('/api/agent/suggestions'), [])
  const [conversationId, setConversationId] = useState(() => { try { return sessionStorage.getItem(STORE_KEY) } catch { return null } })
  const [messages, setMessages] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(Boolean(conversationId))
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [busyAction, setBusyAction] = useState(null)
  const endRef = useRef(null)

  useEffect(() => {
    if (!conversationId) return
    api.get(`/api/agent/conversations/${conversationId}`)
      .then((d) => setMessages(d.messages))
      .catch(() => { setConversationId(null); try { sessionStorage.removeItem(STORE_KEY) } catch { /* bỏ qua */ } })
      .finally(() => setLoadingHistory(false))
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [messages, sending])

  async function send(text) {
    const message = (text ?? input).trim()
    if (!message || sending) return
    setError(null)
    setSending(true)
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: 'user', content: message, created_at: new Date().toISOString() }])
    setInput('')
    try {
      const res = await api.post('/api/agent/chat', { message, conversation_id: conversationId })
      setConversationId(res.conversation_id)
      try { sessionStorage.setItem(STORE_KEY, res.conversation_id) } catch { /* bỏ qua */ }
      setMessages((prev) => [...prev, res.message])
    } catch (e) {
      setError(e.message)
      setMessages((prev) => prev.slice(0, -1))
      setInput(message)
    } finally {
      setSending(false)
    }
  }

  async function confirm(m) {
    setBusyAction(m.id)
    try {
      const task = await api.post('/api/tasks', m.action.params)
      toast.success(`Đã tạo ${task.id}. Workflow đang chạy.`)
      onTaskCreated(task)
    } catch (e) {
      toast.error(e.message)
    } finally {
      setBusyAction(null)
    }
  }

  function reset() {
    setConversationId(null)
    setMessages([])
    setError(null)
    try { sessionStorage.removeItem(STORE_KEY) } catch { /* bỏ qua */ }
  }

  return (
    <Card title="Trợ lý AI Agent" subtitle={`Hỏi bằng tiếng Việt · ${meta.agent.llm_description}`}
      actions={<Button variant="secondary" size="sm" icon={MessageSquarePlus} onClick={reset} disabled={!messages.length}>Cuộc trò chuyện mới</Button>} bodyClass="p-0">
      {meta.agent.llm_warning && <Notice tone="warning" className="m-4 mb-0">{meta.agent.llm_warning}</Notice>}
      <div className="max-h-[62vh] min-h-[320px] space-y-5 overflow-y-auto px-4 py-4">
        {loadingHistory ? <Loading label="Đang tải cuộc trò chuyện…" /> : messages.length === 0 ? (
          <div>
            <EmptyState icon={Bot} title="Hỏi về điều kiện môi trường, khu vực ưu tiên, dữ liệu hoặc cảnh báo"
              hint="Trợ lý gọi các Agent và công cụ chỉ đọc, câu trả lời có kỳ dữ liệu, nguồn và giới hạn. Mọi số liệu do scoring service tính, không do mô hình ngôn ngữ tự nghĩ ra." />
            {suggestions.error ? <ErrorState message={suggestions.error} onRetry={suggestions.reload} /> : (
              <div className="mx-auto flex max-w-3xl flex-wrap justify-center gap-2">
                {(suggestions.data || []).map((s) => <button key={s} onClick={() => send(s)} className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700 hover:border-brand-500 hover:text-brand-700">{s}</button>)}
              </div>
            )}
          </div>
        ) : messages.map((m) => m.role === 'user' ? (
          <div key={m.id} className="flex justify-end gap-2.5">
            <div className="max-w-[80%] rounded-xl rounded-tr-sm bg-brand-600 px-3.5 py-2 text-sm text-white">{m.content}</div>
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-600"><User size={15} /></div>
          </div>
        ) : <AssistantMessage key={m.id} m={m} onConfirm={confirm} busyAction={busyAction} />)}
        {sending && <div className="flex items-center gap-2 text-sm text-slate-500"><Bot size={15} className="animate-pulse" /> Orchestrator đang phân loại câu hỏi và gọi Agent…</div>}
        <div ref={endRef} />
      </div>
      <div className="border-t border-slate-200 p-3">
        {error && <Notice tone="danger" className="mb-2">{error}</Notice>}
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); send() }}>
          <input className="input flex-1" maxLength={1000} placeholder="Ví dụ: Vì sao ESS của KV-C cao? · Khu vực nào cần ưu tiên kiểm tra 14 ngày qua?"
            value={input} onChange={(e) => setInput(e.target.value)} disabled={sending} />
          <Button type="submit" icon={Send} loading={sending} disabled={!input.trim()}>Gửi</Button>
        </form>
        <p className="mt-1.5 text-[11px] text-slate-500">
          Nếu câu hỏi không nêu khu vực, trợ lý dùng toàn bộ {meta.areas.length} khu vực thí điểm; không nêu thời gian thì dùng 7 ngày gần nhất (tối đa 31 ngày). Trợ lý không chẩn đoán bệnh, không dự đoán ca bệnh hay dịch, và không tự thực hiện hành động ghi.
        </p>
      </div>
    </Card>
  )
}
