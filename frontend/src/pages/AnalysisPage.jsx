import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Lock, Play } from 'lucide-react'
import { useApp, useAsync, useToast } from '../lib/context.jsx'
import { api, qs } from '../lib/api.js'
import { ESS_LEVELS, PIS_LEVELS, addDays, essKey, fmtDate, fmtDateTime, fmtNum } from '../lib/format.js'
import { Badge, Button, Card, EmptyState, ErrorState, EssBadge, Field, Loading, Notice, PisBadge, SampleTag, Tabs } from '../components/ui.jsx'

const STATUS = {
  ok: ['Đủ dữ liệu', '#15803d'], partial: ['Thiếu một phần dữ liệu', '#b45309'],
  insufficient_data: ['Không đủ dữ liệu — không tính điểm', '#b91c1c'], unsupported_species: ['Loài chưa cấu hình', '#b91c1c'],
}

function ScoreTile({ title, value, level, note }) {
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</div>
      <div className="mt-1 flex items-end gap-2">
        <span className="num text-4xl font-bold" style={{ color: level?.color || '#64748b' }}>{value === null ? '—' : value}</span>
        <span className="pb-1 text-sm text-slate-400">/ 100</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full" style={{ width: `${value || 0}%`, backgroundColor: level?.color || '#cbd5e1' }} /></div>
      <div className="mt-2 text-sm font-semibold" style={{ color: level?.color || '#64748b' }}>{level?.label || 'Không tính được'}</div>
      {note && <div className="mt-0.5 text-xs text-slate-500">{note}</div>}
    </div>
  )
}

function ResultTab({ run }) {
  const [label, color] = STATUS[run.status] || [run.status, '#64748b']
  return (
    <div className="space-y-4">
      {run.message && <Notice tone={run.ess === null ? 'danger' : 'warning'}>{run.message}</Notice>}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ScoreTile title="ESS — mức thuận lợi môi trường" value={run.ess} level={run.ess_class ? ESS_LEVELS[essKey(run.ess_class)] : null} note={run.ess_class?.meaning} />
        <ScoreTile title="PIS — mức ưu tiên kiểm tra" value={run.pis} level={run.pis_class ? PIS_LEVELS[run.pis_class.key] : null} note={run.pis_message} />
        <div className="space-y-1.5 rounded-xl border border-slate-200 p-4 text-sm">
          <div className="flex justify-between"><span className="text-slate-500">Trạng thái dữ liệu</span><Badge color={color}>{label}</Badge></div>
          <div className="flex justify-between"><span className="text-slate-500">Độ đầy đủ dữ liệu</span><b className="num">{Math.round(run.completeness * 100)}% trọng số</b></div>
          <div className="flex justify-between"><span className="text-slate-500">Thời điểm chạy</span><span>{fmtDateTime(run.created_at)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Người chạy</span><span>{run.created_by}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Phiên bản scoring</span><code className="text-xs">{run.scoring_version}</code></div>
          <div className="flex justify-between"><span className="text-slate-500">Mã lần chạy</span><span>#{run.run_id}{run.task_id && <> · <Link className="text-brand-700 underline" to={`/agent?task=${run.task_id}`}>{run.task_id}</Link></>}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Kỳ trước (so sánh)</span><span className="num">ESS {run.previous_period.ess ?? 'không tính được'}</span></div>
        </div>
      </div>

      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Bảng yếu tố đóng góp vào ESS</h3>
          <span className="inline-flex items-center gap-1 text-xs text-slate-500"><Lock size={12} />Trọng số chỉ đọc — không chỉnh được trong màn hình kết quả</span>
        </div>
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full">
            <thead className="border-b border-slate-200 bg-slate-50"><tr>
              <th className="th">Yếu tố</th><th className="th">Giá trị</th><th className="th">Đơn vị</th><th className="th">Điểm thành phần</th><th className="th">Trọng số (hiệu lực)</th><th className="th">Đóng góp</th><th className="th">Nguồn</th><th className="th">Giải thích</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {run.components.map((c) => (
                <tr key={c.key} className={c.missing ? 'bg-amber-50/60' : ''}>
                  <td className="td font-medium">{c.label}</td>
                  <td className="td num">{c.missing ? <Badge color="#b45309">Thiếu</Badge> : c.key === 'survey' ? `${Math.round(c.value * 100)}%` : fmtNum(c.value)}</td>
                  <td className="td text-xs">{c.unit}</td>
                  <td className="td num">{c.missing ? '—' : (
                    <div className="flex items-center gap-2"><span className="w-9">{c.score}</span><span className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100"><span className="block h-full bg-brand-500" style={{ width: `${c.score}%` }} /></span></div>
                  )}</td>
                  <td className="td num whitespace-nowrap">{Math.round(c.weight * 100)}%{!c.missing && c.effective_weight !== c.weight && <span className="text-amber-700"> → {(c.effective_weight * 100).toFixed(1)}%</span>}{c.missing && <span className="text-amber-700"> → 0%</span>}</td>
                  <td className="td num font-semibold">{c.missing ? '—' : `+${c.contribution}`}</td>
                  <td className="td text-xs">{c.source || '—'}</td>
                  <td className="td min-w-64 text-xs text-slate-600">{c.explanation}{c.detail && <div className="mt-0.5 text-slate-400">{c.detail}</div>}{c.reference && <div className="mt-0.5 text-slate-400">Tham chiếu demo: {c.reference}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {run.pis_components.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Thành phần PIS</h3>
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full">
              <thead className="border-b border-slate-200 bg-slate-50"><tr><th className="th">Thành phần</th><th className="th">Điểm</th><th className="th">Trọng số (hiệu lực)</th><th className="th">Đóng góp</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {run.pis_components.map((c) => (
                  <tr key={c.key}><td className="td font-medium">{c.label}</td><td className="td num">{c.missing ? <Badge color="#b45309">Thiếu</Badge> : c.score}</td>
                    <td className="td num">{Math.round(c.weight * 100)}%{c.effective_weight !== c.weight && <span className="text-amber-700"> → {(c.effective_weight * 100).toFixed(1)}%</span>}</td>
                    <td className="td num font-semibold">{c.missing ? '—' : `+${c.contribution}`}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function InputsTab({ run, labels }) {
  const inputs = run.inputs || { weather: [], water_points: [], surveys: [] }
  const Cell = ({ v, unit = '' }) => (v === null || v === undefined ? <Badge color="#b45309">Thiếu</Badge> : <>{fmtNum(v)}{unit}</>)
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div>
        <h3 className="mb-2 text-sm font-semibold">Thời tiết theo ngày ({inputs.weather.length} ngày)</h3>
        <div className="max-h-96 overflow-auto rounded-lg border border-slate-200">
          <table className="w-full"><thead className="sticky top-0 bg-slate-50"><tr><th className="th">Ngày</th><th className="th">Mưa (mm)</th><th className="th">Nhiệt độ (°C)</th><th className="th">Độ ẩm (%)</th><th className="th">Nguồn</th></tr></thead>
            <tbody className="divide-y divide-slate-100">{inputs.weather.map((w) => (
              <tr key={w.date}><td className="td">{fmtDate(w.date)}</td><td className="td num"><Cell v={w.rainfall_mm} /></td><td className="td num"><Cell v={w.temperature_c} /></td><td className="td num"><Cell v={w.humidity_pct} /></td><td className="td text-xs">{w.source || '—'}</td></tr>
            ))}</tbody></table>
        </div>
      </div>
      <div className="space-y-4">
        <div>
          <h3 className="mb-2 text-sm font-semibold">Điểm nước đọng ({inputs.water_points.length})</h3>
          {inputs.water_points.length === 0 ? <Notice tone="warning">Chưa có bản ghi điểm nước đọng — coi là thiếu dữ liệu, không phải “không có nước đọng”.</Notice> : (
            <div className="max-h-48 overflow-auto rounded-lg border border-slate-200">
              <table className="w-full"><thead className="sticky top-0 bg-slate-50"><tr><th className="th">Mã</th><th className="th">Loại</th><th className="th">Trạng thái</th><th className="th">Ngày</th><th className="th">Nguồn</th></tr></thead>
                <tbody className="divide-y divide-slate-100">{inputs.water_points.map((p) => (
                  <tr key={p.id}><td className="td">{p.code}</td><td className="td">{p.water_type}</td><td className="td">{p.status === 'active' ? 'Đang tồn tại' : 'Đã xử lý'}</td><td className="td">{fmtDate(p.observed_date)}</td><td className="td text-xs">{p.source}</td></tr>
                ))}</tbody></table>
            </div>
          )}
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold">Khảo sát trong 30 ngày ({inputs.surveys.length})</h3>
          {inputs.surveys.length === 0 ? <Notice tone="warning">Không có lượt khảo sát nào — thành phần khảo sát được coi là thiếu.</Notice> : (
            <div className="max-h-48 overflow-auto rounded-lg border border-slate-200">
              <table className="w-full"><thead className="sticky top-0 bg-slate-50"><tr><th className="th">Mã</th><th className="th">Ngày</th><th className="th">Kết quả</th><th className="th">Số lượng</th><th className="th">Nguồn</th></tr></thead>
                <tbody className="divide-y divide-slate-100">{inputs.surveys.map((s) => (
                  <tr key={s.id}><td className="td">{s.code}</td><td className="td">{fmtDate(s.survey_date)}</td><td className="td">{labels[s.result] || s.result}</td><td className="td num">{s.vector_count ?? '—'}</td><td className="td text-xs">{s.source}</td></tr>
                ))}</tbody></table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function AnalysisPage() {
  const { meta, can } = useApp()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const latest = meta.data.latest_date
  const [areaId, setAreaId] = useState(() => params.get('area') || String(meta.areas[0]?.id || ''))
  const [species, setSpecies] = useState('aedes')
  const [start, setStart] = useState(() => (latest ? addDays(latest, -6) : ''))
  const [end, setEnd] = useState(latest || '')
  const [tab, setTab] = useState('result')
  const [run, setRun] = useState(null)
  const [running, setRunning] = useState(false)
  const [loadingRun, setLoadingRun] = useState(false)
  const [runError, setRunError] = useState(null)
  const history = useAsync(() => api.get(`/api/analysis/runs${qs({ area_id: areaId, limit: 30 })}`), [areaId, run?.run_id])

  async function openRun(id) {
    setLoadingRun(true); setRunError(null)
    try {
      const r = await api.get(`/api/analysis/runs/${id}`)
      setRun(r); setAreaId(String(r.area_id)); setStart(r.start_date); setEnd(r.end_date); setTab('result')
    } catch (err) { setRunError(err.message) } finally { setLoadingRun(false) }
  }

  // Mở theo ?run=… hoặc tự mở lần chạy gần nhất của khu vực đang chọn.
  useEffect(() => { const id = params.get('run'); if (id) openRun(id) }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (params.get('run') || history.loading || !history.data) return
    if (history.data.length && String(history.data[0].area_id) !== String(areaId)) return  // dữ liệu cũ của khu vực trước
    if (run && String(run.area_id) === String(areaId)) return
    if (history.data.length) openRun(history.data[0].id)
    else setRun(null)
  }, [history.data, history.loading, areaId])  // eslint-disable-line react-hooks/exhaustive-deps

  async function execute() {
    setRunning(true); setRunError(null)
    try {
      const r = await api.post('/api/analysis/run', { area_id: Number(areaId), species, start, end })
      setRun(r); setTab('result'); setParams({}, { replace: true })
      toast.success(r.ess === null ? 'Đã chạy phân tích nhưng không đủ dữ liệu để tính ESS.' : `Đã chạy phân tích: ESS ${r.ess}, PIS ${r.pis ?? '—'}.`)
    } catch (err) { setRunError(err.message); toast.error(err.message) } finally { setRunning(false) }
  }

  const area = meta.areas.find((a) => String(a.id) === String(areaId))
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-52"><Field label="Khu vực"><select className="input" value={areaId} onChange={(e) => { setAreaId(e.target.value); setParams({}, { replace: true }) }}>
            {meta.areas.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.code})</option>)}</select></Field></div>
          <div className="w-52"><Field label="Loài véc-tơ"><select className="input" value={species} onChange={(e) => setSpecies(e.target.value)}>
            {meta.species.map((s) => <option key={s.key} value={s.key} disabled={!s.configured}>{s.label}{s.configured ? '' : ' (chưa cấu hình)'}</option>)}</select></Field></div>
          <div className="w-40"><Field label="Từ ngày"><input type="date" className="input" value={start} min={meta.data.earliest_date} max={end} onChange={(e) => setStart(e.target.value)} /></Field></div>
          <div className="w-40"><Field label="Đến ngày"><input type="date" className="input" value={end} min={start} max={latest} onChange={(e) => setEnd(e.target.value)} /></Field></div>
          <Button icon={Play} loading={running} disabled={!can('analysis.run') || !start || !end} title={can('analysis.run') ? '' : 'Vai trò của bạn không có quyền chạy phân tích'} onClick={execute}>Chạy phân tích</Button>
          <div className="ml-auto text-right text-xs text-slate-500">Scoring <code>{meta.scoring.version}</code><br /><SampleTag /></div>
        </div>
        {!can('analysis.run') && <p className="mt-2 text-xs text-slate-500">Bạn đang ở chế độ chỉ xem: có thể mở các lần phân tích đã lưu ở tab Lịch sử.</p>}
      </Card>

      {runError && <Notice tone="danger">{runError}</Notice>}
      <Card bodyClass="p-0" title={run ? `${meta.areas.find((a) => a.id === run.area_id)?.name || ''} · ${fmtDate(run.start_date)} → ${fmtDate(run.end_date)} · ${run.species}` : `${area?.name || ''}`}
        subtitle={run ? 'Kết quả đã lưu kèm đầu vào, tham số và phiên bản công thức' : undefined}>
        <div className="px-3 pt-2">
          <Tabs value={tab} onChange={setTab} tabs={[{ key: 'result', label: 'Kết quả' }, { key: 'inputs', label: 'Dữ liệu đầu vào' }, { key: 'explain', label: 'Giải thích' }, { key: 'history', label: 'Lịch sử', count: history.data?.length }]} />
        </div>
        <div className="p-4">
          {tab === 'history' ? (
            history.loading ? <Loading /> : history.error ? <ErrorState message={history.error} onRetry={history.reload} /> : history.data.length === 0 ? <EmptyState title="Chưa có lần phân tích nào cho khu vực này" hint="Nhấn “Chạy phân tích” để tạo lần đầu tiên." /> : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full"><thead className="bg-slate-50"><tr><th className="th">#</th><th className="th">Thời điểm chạy</th><th className="th">Kỳ</th><th className="th">ESS</th><th className="th">PIS</th><th className="th">Đầy đủ</th><th className="th">Scoring</th><th className="th">Người chạy</th><th className="th">Nhiệm vụ</th><th className="th"></th></tr></thead>
                  <tbody className="divide-y divide-slate-100">{history.data.map((h) => (
                    <tr key={h.id} className={run?.run_id === h.id ? 'bg-brand-50' : ''}>
                      <td className="td num">{h.id}</td><td className="td whitespace-nowrap">{fmtDateTime(h.created_at)}</td><td className="td whitespace-nowrap">{fmtDate(h.start_date)} → {fmtDate(h.end_date)}</td>
                      <td className="td"><EssBadge cls={h.ess_class} value={h.ess} /></td><td className="td"><PisBadge cls={h.pis_class} value={h.pis} /></td>
                      <td className="td num">{Math.round(h.completeness * 100)}%</td><td className="td text-xs">{h.scoring_version}</td><td className="td text-xs">{h.created_by}</td><td className="td text-xs">{h.task_id || '—'}</td>
                      <td className="td"><Button variant="ghost" size="sm" onClick={() => openRun(h.id)}>Mở</Button></td>
                    </tr>))}</tbody></table>
              </div>
            )
          ) : loadingRun || running ? <Loading label={running ? 'Đang tính đặc trưng và điểm…' : 'Đang mở kết quả…'} /> : !run ? (
            <EmptyState title="Chưa có kết quả phân tích cho khu vực này" hint="Chọn khu vực, loài và khoảng thời gian rồi nhấn “Chạy phân tích”. Điểm được tính bằng service Python xác định." />
          ) : tab === 'result' ? <ResultTab run={run} /> : tab === 'inputs' ? <InputsTab run={run} labels={meta.survey_result_labels} /> : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-slate-200 p-4">
                <h3 className="text-sm font-semibold text-slate-900">Kết luận và yếu tố chính</h3>
                <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-slate-700">{run.explanation.summary.map((s, i) => <li key={i}>{s}</li>)}</ul>
                <p className="mt-3 text-xs text-slate-500">Sinh bởi: {run.explanation.generated_by}.</p>
              </div>
              <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
                <h3 className="text-sm font-semibold text-amber-900">Dữ liệu thiếu và giới hạn</h3>
                <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-amber-900">{run.explanation.limitations.map((s, i) => <li key={i}>{s}</li>)}</ul>
                <p className="mt-3 text-xs text-amber-800">{meta.scoring.notice}</p>
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
