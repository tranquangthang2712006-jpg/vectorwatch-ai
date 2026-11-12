import { useRef, useState } from 'react'
import { CheckCircle2, Download, FileUp, PencilLine, UploadCloud, XCircle } from 'lucide-react'
import { useApp, useAsync, useToast } from '../lib/context.jsx'
import { api, qs } from '../lib/api.js'
import { addDays, fmtDate, fmtDateTime, fmtNum } from '../lib/format.js'
import { Badge, Button, Card, EmptyState, ErrorState, Field, Loading, Modal, NoPermission, Notice, SampleTag, Tabs } from '../components/ui.jsx'

const KINDS = {
  weather: {
    label: 'Dữ liệu thời tiết',
    columns: [['area_code', 'Khu vực'], ['date', 'Ngày', fmtDate], ['rainfall_mm', 'Mưa (mm)'], ['temperature_c', 'Nhiệt độ (°C)'], ['humidity_pct', 'Độ ẩm (%)'], ['source', 'Nguồn'], ['batch_id', 'Mã batch']],
    form: [
      { name: 'area_code', label: 'Khu vực', type: 'area', required: true },
      { name: 'date', label: 'Ngày quan sát', type: 'date', required: true },
      { name: 'rainfall_mm', label: 'Lượng mưa (mm)', type: 'number', hint: 'Để trống nếu không có số liệu (không nhập 0 thay cho thiếu).' },
      { name: 'temperature_c', label: 'Nhiệt độ trung bình (°C)', type: 'number' },
      { name: 'humidity_pct', label: 'Độ ẩm tương đối (%)', type: 'number' },
      { name: 'source', label: 'Nguồn', type: 'text', placeholder: 'Ví dụ: Trạm quan trắc mẫu' },
    ],
  },
  survey: {
    label: 'Khảo sát thực địa',
    columns: [['code', 'Mã điểm'], ['area_code', 'Khu vực'], ['latitude', 'Vĩ độ'], ['longitude', 'Kinh độ'], ['survey_date', 'Ngày khảo sát', fmtDate], ['species', 'Loài'], ['result_label', 'Quan sát'], ['vector_count', 'Số lượng'], ['notes', 'Ghi chú'], ['entered_by', 'Người nhập'], ['source', 'Nguồn']],
    form: [
      { name: 'latitude', label: 'Vĩ độ (WGS84)', type: 'number', required: true, placeholder: '21.0251' },
      { name: 'longitude', label: 'Kinh độ (WGS84)', type: 'number', required: true, placeholder: '105.7852' },
      { name: 'survey_date', label: 'Ngày khảo sát', type: 'date', required: true },
      { name: 'species', label: 'Loài', type: 'select', options: [['aedes', 'Aedes'], ['anopheles', 'Anopheles'], ['culex', 'Culex']] },
      { name: 'result', label: 'Kết quả quan sát', type: 'select', required: true, options: [['larvae_present', 'Có ấu trùng/bọ gậy'], ['adult_present', 'Có muỗi trưởng thành'], ['none_found', 'Đã khảo sát, không ghi nhận'], ['not_surveyed', 'Chưa khảo sát']] },
      { name: 'vector_count', label: 'Số lượng đếm', type: 'number', hint: 'Để trống nếu không đếm.' },
      { name: 'notes', label: 'Ghi chú', type: 'text' },
      { name: 'source', label: 'Nguồn', type: 'text', placeholder: 'Ví dụ: Khảo sát thực địa' },
    ],
  },
  water: {
    label: 'Điểm nước đọng',
    columns: [['code', 'Mã điểm'], ['area_code', 'Khu vực'], ['latitude', 'Vĩ độ'], ['longitude', 'Kinh độ'], ['water_type', 'Loại điểm'], ['status', 'Trạng thái', (v) => (v === 'active' ? 'Đang tồn tại' : 'Đã xử lý')], ['persistence_days', 'Tồn tại (ngày)'], ['observed_date', 'Ngày ghi nhận', fmtDate], ['notes', 'Ghi chú'], ['source', 'Nguồn']],
    form: [
      { name: 'latitude', label: 'Vĩ độ (WGS84)', type: 'number', required: true, placeholder: '21.0251' },
      { name: 'longitude', label: 'Kinh độ (WGS84)', type: 'number', required: true, placeholder: '105.7852' },
      { name: 'water_type', label: 'Loại điểm', type: 'select', required: true, options: ['Lốp xe cũ', 'Chum/vại chứa nước', 'Phế thải chứa nước', 'Vũng nước', 'Cống rãnh', 'Chậu cây cảnh', 'Thùng phuy'].map((v) => [v, v]) },
      { name: 'status', label: 'Trạng thái', type: 'select', options: [['active', 'Đang tồn tại'], ['resolved', 'Đã xử lý']] },
      { name: 'persistence_days', label: 'Số ngày tồn tại', type: 'number' },
      { name: 'observed_date', label: 'Ngày ghi nhận', type: 'date', required: true },
      { name: 'notes', label: 'Ghi chú', type: 'text' },
      { name: 'source', label: 'Nguồn', type: 'text', placeholder: 'Ví dụ: Khảo sát thực địa' },
    ],
  },
}

function DataTable({ kind, refreshKey }) {
  const { areaId, days, meta } = useApp()
  const [page, setPage] = useState(1)
  const since = meta.data.latest_date ? addDays(meta.data.latest_date, -(days - 1)) : ''
  const { data, loading, error, reload } = useAsync(
    () => api.get(`/api/data/${kind}${qs({ area_id: areaId, since, page, page_size: 15 })}`), [kind, areaId, since, page, refreshKey])
  const columns = KINDS[kind].columns
  if (loading) return <Loading />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (data.total === 0) return <EmptyState title="Không có bản ghi nào theo bộ lọc" hint="Đổi bộ lọc khu vực/thời gian ở thanh trên, hoặc nhập thêm dữ liệu." />
  const pages = Math.ceil(data.total / data.page_size)
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-slate-200 bg-slate-50"><tr>{columns.map(([key, label]) => <th key={key} className="th">{label}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.rows.map((row) => (
              <tr key={row.id} className="hover:bg-slate-50">
                {columns.map(([key, , format]) => {
                  const value = row[key]
                  const missing = value === null || value === undefined || value === ''
                  const measured = ['rainfall_mm', 'temperature_c', 'humidity_pct'].includes(key)
                  return <td key={key} className="td num whitespace-nowrap">{missing ? (measured ? <Badge color="#b45309">Thiếu</Badge> : <span className="text-slate-400">—</span>) : format ? format(value) : typeof value === 'number' && !Number.isInteger(value) ? fmtNum(value, 5) : String(value)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
        <span>{data.total} bản ghi · trang {data.page}/{pages}</span>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Trước</Button>
          <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Sau</Button>
        </div>
      </div>
    </>
  )
}

function History({ refreshKey }) {
  const { data, loading, error, reload } = useAsync(() => api.get('/api/data/batches/history'), [refreshKey])
  if (loading) return <Loading />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data.length) return <EmptyState title="Chưa có lần nhập nào" />
  const labels = { weather: 'Thời tiết', water: 'Điểm nước đọng', survey: 'Khảo sát', all: 'Tất cả (seed)' }
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="border-b border-slate-200 bg-slate-50"><tr>
          <th className="th">Mã batch</th><th className="th">Loại</th><th className="th">Tên tệp</th><th className="th">Người nhập</th><th className="th">Thời gian</th><th className="th">Thêm</th><th className="th">Cập nhật</th><th className="th">Bỏ qua (trùng)</th><th className="th">Từ chối</th>
        </tr></thead>
        <tbody className="divide-y divide-slate-100">
          {data.map((b) => (
            <tr key={b.id}>
              <td className="td font-medium">{b.id}</td><td className="td">{labels[b.kind] || b.kind}</td><td className="td">{b.filename || '(biểu mẫu)'}</td>
              <td className="td">{b.user_name}</td><td className="td whitespace-nowrap">{fmtDateTime(b.created_at)}</td>
              <td className="td num">{b.rows_added}</td><td className="td num">{b.rows_updated}</td><td className="td num">{b.rows_skipped}</td><td className="td num">{b.rows_rejected}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ImportModal({ kind, mode, onClose, onDone }) {
  const { meta } = useApp()
  const toast = useToast()
  const spec = KINDS[kind]
  const fileRef = useRef(null)
  const [form, setForm] = useState(() => Object.fromEntries(spec.form.map((f) => [f.name, f.type === 'select' && !f.required ? f.options[0][0] : ''])))
  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [policy, setPolicy] = useState('skip')
  const [confirmOverwrite, setConfirmOverwrite] = useState(false)
  const [result, setResult] = useState(null)

  async function runPreview() {
    setBusy(true); setError(null)
    try {
      const body = new FormData()
      if (mode === 'file') {
        if (!file) throw new Error('Hãy chọn hoặc kéo-thả một tệp .csv / .xlsx.')
        body.append('file', file)
      } else {
        body.append('rows', JSON.stringify([form]))
      }
      setReport(await api.upload(`/api/data/${kind}/preview`, body))
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function commit() {
    setBusy(true); setError(null)
    try {
      const res = await api.post(`/api/data/${kind}/commit`, {
        rows: report.rows.map((r) => r.raw), filename: report.filename, duplicate_policy: policy, confirm_overwrite: confirmOverwrite,
      })
      setResult(res)
      toast.success(`Đã lưu batch ${res.batch_id}: thêm ${res.added}, cập nhật ${res.updated}, bỏ qua ${res.skipped}, từ chối ${res.rejected}.`)
      onDone()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const summary = report?.summary
  const savable = summary ? summary.valid - (policy === 'skip' ? summary.duplicates : 0) : 0
  const title = `${mode === 'file' ? 'Nhập CSV/Excel' : 'Nhập bằng biểu mẫu'} — ${spec.label}`

  if (result) {
    return (
      <Modal title={title} onClose={onClose} footer={<Button onClick={onClose}>Đóng</Button>}>
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <CheckCircle2 className="text-emerald-600" size={36} />
          <div className="text-base font-semibold">Đã lưu dữ liệu</div>
          <div className="text-sm text-slate-600">Mã batch để truy xuất: <b>{result.batch_id}</b></div>
          <div className="text-sm text-slate-600">Thêm mới {result.added} · Cập nhật {result.updated} · Bỏ qua do trùng {result.skipped} · Từ chối do lỗi {result.rejected}</div>
          <div className="text-xs text-slate-500">Hãy chạy lại phân tích hoặc tạo nhiệm vụ Agent để điểm ESS/PIS phản ánh dữ liệu mới.</div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal wide title={title} onClose={onClose}
      footer={report ? (
        <>
          <Button variant="secondary" onClick={() => { setReport(null); setError(null) }}>← Quay lại chỉnh sửa</Button>
          <Button loading={busy} disabled={savable <= 0 || (policy === 'overwrite' && !confirmOverwrite)} onClick={commit}>Xác nhận lưu {savable > 0 ? `${savable} dòng` : ''}</Button>
        </>
      ) : (
        <><Button variant="secondary" onClick={onClose}>Hủy</Button><Button loading={busy} onClick={runPreview}>Xem trước & kiểm tra</Button></>
      )}>
      {error && <Notice tone="danger" className="mb-3">{error}</Notice>}
      {!report && mode === 'form' && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {spec.form.map((f) => (
            <Field key={f.name} label={f.label} required={f.required} hint={f.hint}>
              {f.type === 'area' ? (
                <select className="input" value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}>
                  <option value="">— Chọn khu vực —</option>
                  {meta.areas.map((a) => <option key={a.id} value={a.code}>{a.name} ({a.code})</option>)}
                </select>
              ) : f.type === 'select' ? (
                <select className="input" value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}>
                  {f.required && <option value="">— Chọn —</option>}
                  {f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              ) : (
                <input className="input" type={f.type === 'date' ? 'date' : 'text'} inputMode={f.type === 'number' ? 'decimal' : undefined} placeholder={f.placeholder}
                  value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} />
              )}
            </Field>
          ))}
          {kind !== 'weather' && meta.extent && (
            <Notice tone="neutral" className="sm:col-span-2">Khu vực thí điểm (giả lập): vĩ độ {meta.extent.min_lat.toFixed(4)}–{meta.extent.max_lat.toFixed(4)}, kinh độ {meta.extent.min_lng.toFixed(4)}–{meta.extent.max_lng.toFixed(4)}. Tọa độ ngoài phạm vi sẽ bị từ chối.</Notice>
          )}
        </div>
      )}
      {!report && mode === 'file' && (
        <div className="space-y-3">
          <div onDragOver={(e) => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]) }}
            className={`flex flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center ${dragging ? 'border-brand-500 bg-brand-50' : 'border-slate-300 bg-slate-50'}`}>
            <UploadCloud size={30} className="text-slate-400" />
            <div className="text-sm text-slate-700">{file ? <>Đã chọn: <b>{file.name}</b> ({Math.max(1, Math.round(file.size / 1024))} KB)</> : 'Kéo-thả tệp .csv hoặc .xlsx vào đây'}</div>
            <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={(e) => setFile(e.target.files[0] || null)} />
            <Button variant="secondary" size="sm" onClick={() => fileRef.current.click()}>{file ? 'Chọn tệp khác' : 'Chọn tệp từ máy'}</Button>
          </div>
          <Notice tone="neutral">Cột của tệp: <code className="text-xs">{spec.form.length ? (kind === 'weather' ? 'area_code, date, rainfall_mm, temperature_c, humidity_pct, source' : kind === 'water' ? 'code, latitude, longitude, water_type, status, persistence_days, observed_date, notes, source' : 'code, latitude, longitude, survey_date, species, result, vector_count, notes, source') : ''}</code>. Dùng nút “Tải tệp mẫu” để có đúng tên cột. Chưa có gì được lưu cho tới khi bạn xác nhận ở bước xem trước.</Notice>
        </div>
      )}
      {report && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2 text-sm">
            <Badge color="#334155">Tổng {summary.total} dòng</Badge>
            <Badge color="#15803d">{summary.valid} hợp lệ</Badge>
            <Badge color="#b91c1c">{summary.invalid} lỗi (sẽ không lưu)</Badge>
            <Badge color="#b45309">{summary.duplicates} trùng bản ghi đã có</Badge>
          </div>
          <div className="max-h-[46vh] overflow-auto rounded-lg border border-slate-200">
            <table className="w-full">
              <thead className="sticky top-0 border-b border-slate-200 bg-slate-50"><tr>
                <th className="th">Dòng</th><th className="th">Kết quả</th><th className="th">Lỗi / cảnh báo và cách sửa</th>{report.columns.map((c) => <th key={c} className="th normal-case">{c}</th>)}
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {report.rows.map((r) => {
                  const badFields = new Set(r.errors.map((e) => e.field))
                  return (
                    <tr key={r.row} className={r.valid ? '' : 'bg-red-50/60'}>
                      <td className="td num">{r.row}</td>
                      <td className="td whitespace-nowrap">{r.valid ? (r.duplicate ? <Badge color="#b45309">Trùng</Badge> : <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 size={14} />Hợp lệ</span>) : <span className="inline-flex items-center gap-1 font-medium text-red-700"><XCircle size={14} />Lỗi</span>}</td>
                      <td className="td min-w-72 text-xs">
                        {r.errors.map((e, i) => <div key={`e${i}`} className="mb-1 text-red-800"><b>{e.field}</b>: {e.message} <span className="text-slate-600">→ {e.fix}</span></div>)}
                        {r.warnings.map((e, i) => <div key={`w${i}`} className="mb-1 text-amber-800"><b>{e.field}</b>: {e.message}</div>)}
                        {r.valid && r.duplicate && <div className="text-amber-800">Đã có bản ghi cùng khóa trong CSDL.</div>}
                      </td>
                      {report.columns.map((c) => <td key={c} className={`td whitespace-nowrap ${badFields.has(c) ? 'font-semibold text-red-700 underline decoration-wavy' : ''}`}>{r.raw[c] || <span className="text-slate-400">(trống)</span>}</td>)}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {summary.invalid > 0 && <Notice tone="warning">Các dòng lỗi sẽ bị loại khỏi lần lưu này. Sửa theo gợi ý rồi nhập lại riêng các dòng đó.</Notice>}
          {summary.duplicates > 0 && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
              <div className="font-semibold text-amber-900">{summary.duplicates} dòng trùng với bản ghi đã có — bạn muốn xử lý thế nào?</div>
              <label className="mt-2 flex items-center gap-2"><input type="radio" checked={policy === 'skip'} onChange={() => { setPolicy('skip'); setConfirmOverwrite(false) }} />Giữ nguyên dữ liệu cũ, bỏ qua các dòng trùng (mặc định)</label>
              <label className="mt-1 flex items-center gap-2"><input type="radio" checked={policy === 'overwrite'} onChange={() => setPolicy('overwrite')} />Ghi đè bản ghi cũ bằng dòng mới</label>
              {policy === 'overwrite' && <label className="mt-2 flex items-center gap-2 font-medium text-red-800"><input type="checkbox" checked={confirmOverwrite} onChange={(e) => setConfirmOverwrite(e.target.checked)} />Tôi xác nhận ghi đè {summary.duplicates} bản ghi đã có (không hoàn tác được).</label>}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

export default function DataPage() {
  const { can, refreshMeta } = useApp()
  const toast = useToast()
  const [tab, setTab] = useState('weather')
  const [modal, setModal] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const kind = tab === 'history' ? null : tab

  async function downloadTemplate() {
    try { await api.download(`/api/data/${kind}/template.csv`, `mau_${kind}.csv`) } catch (err) { toast.error(err.message) }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm text-slate-600">Dữ liệu ban đầu là <SampleTag />. Bản ghi bạn nhập thêm mang nguồn do bạn khai báo.</div>
        {kind && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" icon={Download} onClick={downloadTemplate}>Tải tệp mẫu (.csv)</Button>
            <Button variant="secondary" icon={PencilLine} disabled={!can('data.write')} onClick={() => setModal('form')}>Nhập bằng biểu mẫu</Button>
            <Button icon={FileUp} disabled={!can('data.write')} onClick={() => setModal('file')}>Nhập CSV/Excel</Button>
          </div>
        )}
      </div>
      {!can('data.write') && <NoPermission action="nhập hoặc sửa dữ liệu" />}
      <Card bodyClass="p-0">
        <div className="px-3 pt-2">
          <Tabs value={tab} onChange={setTab} tabs={[{ key: 'weather', label: 'Dữ liệu thời tiết' }, { key: 'survey', label: 'Khảo sát thực địa' }, { key: 'water', label: 'Điểm nước đọng' }, { key: 'history', label: 'Lịch sử nhập' }]} />
        </div>
        {kind ? <DataTable key={kind} kind={kind} refreshKey={refreshKey} /> : <History refreshKey={refreshKey} />}
      </Card>
      {modal && <ImportModal kind={kind} mode={modal} onClose={() => setModal(null)} onDone={() => { setRefreshKey((k) => k + 1); refreshMeta() }} />}
    </div>
  )
}
