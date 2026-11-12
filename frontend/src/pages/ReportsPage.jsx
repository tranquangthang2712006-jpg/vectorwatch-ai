import { Fragment, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CheckCircle2, ChevronDown, ChevronRight, FileSpreadsheet, FlaskConical, Printer, RefreshCw, XCircle } from 'lucide-react'
import { useApp, useAsync, useToast } from '../lib/context.jsx'
import { api, qs } from '../lib/api.js'
import { ESS_LEVELS, addDays, fmtDate, fmtDateTime, fmtNum } from '../lib/format.js'
import { Badge, Button, Card, EmptyState, ErrorState, Field, Loading, NoPermission, Notice, Tabs } from '../components/ui.jsx'

// Bản đồ tĩnh (SVG) để in được: vẽ các ô khu vực theo tọa độ, tô màu theo nhóm ESS và ghi nhãn.
function StaticMap({ areas }) {
  const pts = areas.flatMap((a) => a.polygon)
  const lats = pts.map((p) => p[0]); const lngs = pts.map((p) => p[1])
  const [minLat, maxLat, minLng, maxLng] = [Math.min(...lats), Math.max(...lats), Math.min(...lngs), Math.max(...lngs)]
  const W = 560; const H = 330; const pad = 10
  const x = (lng) => pad + ((lng - minLng) / (maxLng - minLng || 1)) * (W - 2 * pad)
  const y = (lat) => H - pad - ((lat - minLat) / (maxLat - minLat || 1)) * (H - 2 * pad)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-lg border border-slate-200 bg-slate-50" role="img" aria-label="Bản đồ khu vực theo nhóm ESS">
      {areas.map((a) => {
        const level = ESS_LEVELS[a.ess_class_key || 'not_scored']
        return (
          <g key={a.area_id}>
            <polygon points={a.polygon.map((p) => `${x(p[1])},${y(p[0])}`).join(' ')} fill={level.color} fillOpacity={a.ess === null ? 0.3 : 0.6} stroke="#334155" strokeWidth="1" strokeDasharray={a.ess === null ? '4 3' : undefined} />
            <text x={x(a.centroid[1])} y={y(a.centroid[0]) - 3} textAnchor="middle" fontSize="12" fontWeight="700" fill="#0f172a">{a.code.replace('KV-', '')}</text>
            <text x={x(a.centroid[1])} y={y(a.centroid[0]) + 12} textAnchor="middle" fontSize="10.5" fill="#0f172a">{a.ess === null ? 'thiếu DL' : `ESS ${a.ess}`}</text>
          </g>
        )
      })}
    </svg>
  )
}

function Section({ n, title, children }) {
  return <section className="avoid-break"><h3 className="mb-2 border-b border-slate-200 pb-1 text-sm font-bold uppercase tracking-wide text-slate-700">{n}. {title}</h3>{children}</section>
}

function ReportTab() {
  const { meta, can } = useApp()
  const toast = useToast()
  const latest = meta.data.latest_date
  const [filters, setFilters] = useState({ area_id: '', species: 'aedes', start: latest ? addDays(latest, -6) : '', end: latest || '' })
  const [applied, setApplied] = useState(null)
  const [exporting, setExporting] = useState(false)
  const report = useAsync(() => (applied ? api.get(`/api/reports/preview${qs(applied)}`) : Promise.resolve(null)), [applied])
  const r = report.data

  async function exportExcel() {
    setExporting(true)
    try { await api.download(`/api/reports/export.xlsx${qs(applied)}`, 'vectorwatch_bao_cao.xlsx'); toast.success('Đã tạo tệp Excel. Kiểm tra thư mục tải xuống.') }
    catch (err) { toast.error(err.message) } finally { setExporting(false) }
  }

  return (
    <div className="space-y-4">
      <Card className="no-print">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-52"><Field label="Khu vực"><select className="input" value={filters.area_id} onChange={(e) => setFilters({ ...filters, area_id: e.target.value })}>
            <option value="">Tất cả khu vực</option>{meta.areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field></div>
          <div className="w-48"><Field label="Loài"><select className="input" value={filters.species} onChange={(e) => setFilters({ ...filters, species: e.target.value })}>
            {meta.species.map((s) => <option key={s.key} value={s.key} disabled={!s.configured}>{s.label}{s.configured ? '' : ' (chưa cấu hình)'}</option>)}</select></Field></div>
          <div className="w-40"><Field label="Từ ngày"><input type="date" className="input" value={filters.start} max={filters.end} onChange={(e) => setFilters({ ...filters, start: e.target.value })} /></Field></div>
          <div className="w-40"><Field label="Đến ngày"><input type="date" className="input" value={filters.end} min={filters.start} max={latest} onChange={(e) => setFilters({ ...filters, end: e.target.value })} /></Field></div>
          <div className="w-52"><Field label="Phiên bản scoring"><input className="input" value={meta.scoring.version} disabled /></Field></div>
          <Button icon={RefreshCw} loading={report.loading && !!applied} disabled={!filters.start || !filters.end} onClick={() => setApplied({ ...filters })}>Tạo bản xem trước</Button>
          {r && (
            <div className="ml-auto flex gap-2">
              <Button variant="secondary" icon={FileSpreadsheet} loading={exporting} disabled={!can('report.export') || !r.has_data} title={can('report.export') ? '' : 'Vai trò của bạn không có quyền xuất báo cáo'} onClick={exportExcel}>Xuất Excel</Button>
              <Button variant="secondary" icon={Printer} disabled={!can('report.export')} onClick={() => window.print()} title="Mở hộp thoại in của trình duyệt, chọn “Lưu dưới dạng PDF”">In / Lưu PDF</Button>
            </div>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-500">Loại báo cáo: tổng hợp giám sát môi trường theo kỳ. Excel được tạo trên máy chủ; PDF được tạo bằng chức năng In → “Lưu dưới dạng PDF” của trình duyệt (chưa có bộ dựng PDF phía máy chủ).</p>
        {r && !can('report.export') && <div className="mt-2"><NoPermission action="xuất báo cáo" /></div>}
      </Card>

      {!applied ? <Card><EmptyState title="Chưa có bản xem trước" hint="Chọn bộ lọc rồi nhấn “Tạo bản xem trước” để dựng báo cáo từ dữ liệu và kết quả hiện có." /></Card>
        : report.loading ? <Card><Loading label="Đang dựng báo cáo…" /></Card>
          : report.error ? <Card><ErrorState message={report.error} onRetry={report.reload} /></Card>
            : r && (
              <div className="print-area mx-auto max-w-5xl space-y-5 rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
                <header className="border-b-2 border-navy-800 pb-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div><div className="text-xs font-semibold uppercase tracking-widest text-brand-700">VectorWatch AI</div><h2 className="text-xl font-bold text-slate-900">{r.title}</h2></div>
                    <span className="rounded border-2 border-amber-500 px-2 py-1 text-xs font-bold text-amber-700">{r.data_label}</span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-0.5 text-xs text-slate-600 md:grid-cols-3">
                    <span>Kỳ: <b>{fmtDate(r.period.start)} → {fmtDate(r.period.end)}</b></span><span>Loài: <b>{r.species}</b></span><span>Scoring: <b>{r.scoring_version}</b></span>
                    <span>Tạo lúc: {fmtDateTime(r.generated_at)}</span><span>Người tạo: {r.generated_by}</span><span>Ứng dụng: v{r.app_version}</span>
                    {r.last_task && <span className="col-span-full">Nhiệm vụ Agent gần nhất: <b>{r.last_task.id}</b> · trace_id <code>{r.last_task.trace_id}</code></span>}
                  </div>
                </header>

                {!r.has_data && <Notice tone="warning">Không khu vực nào đủ dữ liệu để tính ESS trong kỳ này. Báo cáo chỉ liệt kê tình trạng dữ liệu; không có kết luận về điều kiện môi trường.</Notice>}

                <Section n={1} title="Tóm tắt">
                  <ul className="list-disc space-y-1 pl-5 text-sm text-slate-800">{r.summary.map((s, i) => <li key={i}>{s}</li>)}</ul>
                  <p className="mt-1 text-xs text-slate-500">{r.summary_generated_by}.</p>
                </Section>

                <Section n={2} title="Dữ liệu đầu vào và kết quả theo khu vực">
                  <div className="overflow-x-auto"><table className="w-full border border-slate-200 text-xs">
                    <thead className="bg-slate-100"><tr>{['Khu vực', 'Mưa 7 ngày (mm)', 'Nhiệt độ TB (°C)', 'Độ ẩm TB (%)', 'Điểm nước đọng', 'KS dương tính', 'ESS', 'Nhóm ESS', 'PIS', 'Mức PIS', 'Đầy đủ', 'Dữ liệu thiếu'].map((h) => <th key={h} className="border border-slate-200 px-2 py-1.5 text-left font-semibold">{h}</th>)}</tr></thead>
                    <tbody>{r.areas.map((a) => {
                      const cell = (v, d = 1) => (v === null || v === undefined ? <span className="font-semibold text-amber-700">Thiếu</span> : fmtNum(v, d))
                      return (
                        <tr key={a.area_id}>
                          <td className="border border-slate-200 px-2 py-1 font-medium">{a.name}</td>
                          <td className="num border border-slate-200 px-2 py-1">{cell(a.rainfall_7d)}</td><td className="num border border-slate-200 px-2 py-1">{cell(a.temperature_mean)}</td>
                          <td className="num border border-slate-200 px-2 py-1">{cell(a.humidity_mean)}</td><td className="num border border-slate-200 px-2 py-1">{cell(a.water_points_active, 0)}</td>
                          <td className="num border border-slate-200 px-2 py-1">{a.survey_positive_ratio === null ? <span className="font-semibold text-amber-700">Thiếu</span> : `${Math.round(a.survey_positive_ratio * 100)}% (${a.survey_valid_count})`}</td>
                          <td className="num border border-slate-200 px-2 py-1 font-semibold">{cell(a.ess)}</td><td className="border border-slate-200 px-2 py-1">{a.ess_class || 'Không đủ dữ liệu'}</td>
                          <td className="num border border-slate-200 px-2 py-1 font-semibold">{cell(a.pis)}</td><td className="border border-slate-200 px-2 py-1">{a.pis_class || '—'}</td>
                          <td className="num border border-slate-200 px-2 py-1">{Math.round(a.completeness * 100)}%</td><td className="border border-slate-200 px-2 py-1">{a.missing.join('; ') || 'Không'}</td>
                        </tr>
                      )
                    })}</tbody></table></div>
                </Section>

                <Section n={3} title="Bản đồ và biểu đồ">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div>
                      <StaticMap areas={r.areas} />
                      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-600">{Object.entries(ESS_LEVELS).map(([k, lv]) => <span key={k} className="inline-flex items-center gap-1"><span className="h-2.5 w-4 rounded-sm" style={{ backgroundColor: lv.color, opacity: 0.7 }} />{lv.label} ({lv.range})</span>)}</div>
                      <p className="mt-1 text-[11px] text-slate-500">Ô lưới giả lập, không trùng ranh giới hành chính thật.</p>
                    </div>
                    <div className="space-y-3">
                      <div className="h-40"><ResponsiveContainer width="100%" height="100%">
                        <LineChart data={r.trend} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(d) => fmtDate(d).slice(0, 5)} tick={{ fontSize: 10 }} /><YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                          <Tooltip labelFormatter={(d) => fmtDate(d)} /><Legend wrapperStyle={{ fontSize: 11 }} />
                          <Line isAnimationActive={false} dataKey="ess" name="ESS TB" stroke="#1d5fd1" strokeWidth={2} dot={false} /><Line isAnimationActive={false} dataKey="pis" name="PIS TB" stroke="#c2410c" strokeWidth={2} strokeDasharray="5 4" dot={false} />
                        </LineChart></ResponsiveContainer></div>
                      <div className="h-40"><ResponsiveContainer width="100%" height="100%">
                        <BarChart data={r.distribution.filter((d) => d.key !== 'not_scored' || d.count > 0)} margin={{ top: 14, right: 8, left: -20, bottom: 0 }}>
                          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 10 }} interval={0} /><YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                          <Bar isAnimationActive={false} dataKey="count" name="Số khu vực">{r.distribution.map((d) => <Cell key={d.key} fill={ESS_LEVELS[d.key].color} />)}<LabelList dataKey="count" position="top" style={{ fontSize: 11 }} /></Bar>
                        </BarChart></ResponsiveContainer></div>
                      <p className="text-[11px] text-slate-500">Trên: ESS/PIS trung bình 14 ngày đến cuối kỳ (cửa sổ 7 ngày). Dưới: số khu vực theo nhóm ESS.</p>
                    </div>
                  </div>
                </Section>

                <Section n={4} title="Cảnh báo">
                  {r.alerts.length === 0 ? <p className="text-sm text-slate-600">Chưa có cảnh báo nào cho phạm vi này.</p> : (
                    <table className="w-full border border-slate-200 text-xs"><thead className="bg-slate-100"><tr>{['Mã', 'Khu vực', 'Loại', 'Mức', 'Trạng thái', 'ESS', 'PIS', 'Thời điểm tạo'].map((h) => <th key={h} className="border border-slate-200 px-2 py-1.5 text-left font-semibold">{h}</th>)}</tr></thead>
                      <tbody>{r.alerts.map((a) => <tr key={a.code}>{[a.code, a.area_name, a.type_label, a.severity_label, a.status_label, fmtNum(a.ess), fmtNum(a.pis), fmtDateTime(a.created_at)].map((v, i) => <td key={i} className="border border-slate-200 px-2 py-1">{v}</td>)}</tr>)}</tbody></table>
                  )}
                </Section>

                <Section n={5} title="Khuyến nghị">
                  {r.recommendations.length === 0 ? <p className="text-sm text-slate-600">Chưa có đề xuất nào. Khuyến nghị chỉ xuất hiện khi có đề xuất được tạo và phê duyệt.</p> : (
                    <ul className="space-y-1.5 text-sm">{r.recommendations.map((x) => (
                      <li key={x.code} className="rounded border border-slate-200 px-3 py-2"><b>{x.code} · {x.area}</b> — {x.action} <Badge color={x.status === 'Đã phê duyệt' ? '#15803d' : '#b45309'}>{x.status}</Badge></li>
                    ))}</ul>
                  )}
                </Section>

                <Section n={6} title="Giới hạn">
                  <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">{r.limitations.map((s, i) => <li key={i}>{s}</li>)}</ul>
                </Section>
                <Section n={7} title="Nguồn dữ liệu">
                  <ul className="list-disc pl-5 text-sm text-slate-700">{(r.sources.length ? r.sources : ['(không có nguồn nào trong kỳ)']).map((s) => <li key={s}>{s}</li>)}</ul>
                </Section>
              </div>
            )}
    </div>
  )
}

function Json({ value }) {
  return <pre className="max-h-64 overflow-auto rounded-lg bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">{JSON.stringify(value, null, 2)}</pre>
}

function EvaluationTab() {
  const { can } = useApp()
  const toast = useToast()
  const tests = useAsync(() => api.get('/api/tests'), [])
  const [running, setRunning] = useState(false)
  const [open, setOpen] = useState(null)
  const [override, setOverride] = useState(null)
  const data = override || tests.data

  async function run() {
    setRunning(true)
    try {
      const res = await api.post('/api/tests/run')
      setOverride(res)
      res.passed === res.total ? toast.success(`Đã chạy ${res.total} test case: tất cả đạt.`) : toast.warning(`Đã chạy ${res.total} test case: ${res.total - res.passed} không đạt — mở từng ca để xem chi tiết.`)
    } catch (err) { toast.error(err.message) } finally { setRunning(false) }
  }

  if (tests.loading) return <Card><Loading /></Card>
  if (tests.error) return <Card><ErrorState message={tests.error} onRetry={tests.reload} /></Card>
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-slate-700">
            <b>Bộ 6 tình huống kiểm thử (TC01–TC06).</b> Mỗi lần chạy thực thi mã thật của scoring, validation, workflow Agent và phân quyền, rồi lưu input / expected / actual / pass-fail.
            {data.suite_run_id && <div className="mt-1 text-xs text-slate-500">Lần chạy gần nhất: {data.suite_run_id} · {fmtDateTime(data.run_at)} · bởi {data.run_by} · scoring {data.scoring_version}</div>}
          </div>
          <div className="flex items-center gap-3">
            {data.suite_run_id && <Badge color={data.passed === data.total ? '#15803d' : '#b91c1c'}>{data.passed}/{data.total} đạt</Badge>}
            <Button icon={FlaskConical} loading={running} disabled={!can('tests.run')} title={can('tests.run') ? '' : 'Vai trò của bạn không có quyền chạy test'} onClick={run}>Chạy bộ test</Button>
          </div>
        </div>
        {!can('tests.run') && <div className="mt-2"><NoPermission action="chạy bộ test (vẫn xem được kết quả đã lưu)" /></div>}
      </Card>
      <Card bodyClass="p-0">
        {data.cases.length === 0 ? <EmptyState icon={FlaskConical} title="Chưa có kết quả test nào được lưu" hint="Nhấn “Chạy bộ test” để thực thi 6 tình huống và lưu kết quả thực tế." /> : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-200 bg-slate-50"><tr><th className="th w-8"></th><th className="th">Mã</th><th className="th">Mô tả</th><th className="th">Kết quả</th><th className="th">Nhận xét</th><th className="th">Thời gian chạy</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.cases.map((c) => (
                  <Fragment key={c.case_code}>
                    <tr className="cursor-pointer hover:bg-brand-50" onClick={() => setOpen(open === c.case_code ? null : c.case_code)}>
                      <td className="td">{open === c.case_code ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
                      <td className="td font-semibold">{c.case_code}</td><td className="td">{c.title}</td>
                      <td className="td">{c.passed ? <span className="inline-flex items-center gap-1 font-semibold text-emerald-700"><CheckCircle2 size={15} />PASS</span> : <span className="inline-flex items-center gap-1 font-semibold text-red-700"><XCircle size={15} />FAIL</span>}</td>
                      <td className="td text-xs">{c.comment}</td><td className="td num whitespace-nowrap text-xs">{c.duration_ms} ms · {fmtDateTime(c.run_at)}</td>
                    </tr>
                    {open === c.case_code && (
                      <tr><td colSpan={6} className="bg-slate-50 p-3">
                        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                          <div><div className="mb-1 text-xs font-semibold text-slate-600">Input</div><Json value={c.input} /></div>
                          <div><div className="mb-1 text-xs font-semibold text-slate-600">Expected output</div><Json value={c.expected} /></div>
                          <div><div className="mb-1 text-xs font-semibold text-slate-600">Actual output</div><Json value={c.actual} /></div>
                        </div>
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {data.history?.length > 1 && (
        <Card title="Lịch sử các lần chạy" bodyClass="p-0">
          <table className="w-full"><thead className="bg-slate-50"><tr><th className="th">Mã lần chạy</th><th className="th">Thời điểm</th><th className="th">Người chạy</th><th className="th">Kết quả</th></tr></thead>
            <tbody className="divide-y divide-slate-100">{data.history.map((h) => <tr key={h.suite_run_id}><td className="td font-mono text-xs">{h.suite_run_id}</td><td className="td">{fmtDateTime(h.run_at)}</td><td className="td">{h.run_by}</td><td className="td num">{h.passed}/{h.total} đạt</td></tr>)}</tbody></table>
        </Card>
      )}
      <Notice tone="neutral">TC05 dùng lỗi công cụ được mô phỏng có chủ đích; TC06 kiểm tra lớp phân quyền mà API phê duyệt sử dụng. Bộ test đơn vị đầy đủ hơn nằm ở <code>backend/tests</code> (chạy bằng <code>pytest</code>).</Notice>
    </div>
  )
}

export default function ReportsPage() {
  const [tab, setTab] = useState('report')
  return (
    <div className="space-y-4">
      <div className="no-print"><Tabs value={tab} onChange={setTab} tabs={[{ key: 'report', label: 'Báo cáo' }, { key: 'evaluation', label: 'Đánh giá (test case)' }]} /></div>
      {tab === 'report' ? <ReportTab /> : <EvaluationTab />}
    </div>
  )
}
