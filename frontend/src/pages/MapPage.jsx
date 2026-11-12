import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import L from 'leaflet'
import { MapContainer, Marker, Polygon, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { ClipboardPlus, LocateFixed, Microscope, Search } from 'lucide-react'
import { useApp, useAsync, useToast } from '../lib/context.jsx'
import { api, qs } from '../lib/api.js'
import { ESS_LEVELS, essKey, fmtDate, fmtNum, missingText } from '../lib/format.js'
import { Button, Card, EmptyState, ErrorState, EssBadge, Field, Loading, Modal, Notice, PisBadge, SampleTag } from '../components/ui.jsx'

const waterIcon = (resolved) => L.divIcon({
  className: 'vw-marker', iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -10],
  html: `<svg width="22" height="22" viewBox="0 0 22 22"><circle cx="11" cy="11" r="10" fill="${resolved ? '#e2e8f0' : '#0284c7'}" stroke="#fff" stroke-width="2"/><path d="M11 5.2c2.3 3 3.6 4.9 3.6 6.7a3.6 3.6 0 0 1-7.2 0c0-1.8 1.3-3.7 3.6-6.7z" fill="${resolved ? '#64748b' : '#fff'}"/></svg>`,
})
const SURVEY_STYLE = { larvae_present: ['#7c3aed', '+'], adult_present: ['#7c3aed', '+'], none_found: ['#475569', '–'], not_surveyed: ['#fff', '?'] }
const surveyIcon = (result) => {
  const [fill, glyph] = SURVEY_STYLE[result] || SURVEY_STYLE.not_surveyed
  const text = fill === '#fff' ? '#475569' : '#fff'
  return L.divIcon({
    className: 'vw-marker', iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -10],
    html: `<svg width="22" height="22" viewBox="0 0 22 22"><rect x="2" y="2" width="18" height="18" rx="3" transform="rotate(45 11 11)" fill="${fill}" stroke="${fill === '#fff' ? '#475569' : '#fff'}" stroke-width="2"/><text x="11" y="15.5" text-anchor="middle" font-size="13" font-weight="700" fill="${text}" font-family="Arial">${glyph}</text></svg>`,
  })
}

function FitBounds({ bounds, trigger }) {
  const map = useMap()
  useEffect(() => {
    if (!bounds) return
    // Chừa chỗ cho khung chú giải ở góc trái để không che khu vực.
    const wide = map.getSize().x > 700
    map.fitBounds(bounds, { paddingTopLeft: [wide ? 250 : 20, 20], paddingBottomRight: [20, 20] })
  }, [map, bounds, trigger])
  return null
}
function FlyTo({ target }) {
  const map = useMap()
  useEffect(() => { if (target) map.flyTo(target.center, 15, { duration: 0.6 }) }, [map, target])
  return null
}

function Row({ label, children }) {
  return <div className="flex justify-between gap-3"><span className="text-slate-500">{label}</span><span className="text-right font-medium text-slate-800">{children}</span></div>
}

function AreaSummary({ area }) {
  const f = area.features
  return (
    <div className="space-y-0.5">
      <Row label="ESS">{area.ess === null ? 'Không tính được' : `${area.ess}/100 · ${area.ess_class.label}`}</Row>
      <Row label="PIS">{area.pis === null ? '—' : `${area.pis}/100 · ${area.pis_class.label}`}</Row>
      <Row label="Mưa quy đổi 7 ngày">{f.rainfall_7d === null ? 'Thiếu' : `${fmtNum(f.rainfall_7d)} mm`}</Row>
      <Row label="Nhiệt độ TB">{f.temperature_mean === null ? 'Thiếu' : `${fmtNum(f.temperature_mean)} °C`}</Row>
      <Row label="Độ ẩm TB">{f.humidity_mean === null ? 'Thiếu' : `${fmtNum(f.humidity_mean)} %`}</Row>
      <Row label="Điểm nước đọng">{f.water_points_active === null ? 'Thiếu' : f.water_points_active}</Row>
      <Row label="Khảo sát dương tính">{f.survey_positive_ratio === null ? 'Thiếu' : `${Math.round(f.survey_positive_ratio * 100)}% / ${f.survey_valid_count} lượt`}</Row>
      <Row label="Dữ liệu thiếu">{area.missing.length ? missingText(area.missing) : 'Không'}</Row>
    </div>
  )
}

export default function MapPage() {
  const { meta, areaId, days, can } = useApp()
  const toast = useToast()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [species, setSpecies] = useState('aedes')
  const [levels, setLevels] = useState(() => new Set(Object.keys(ESS_LEVELS)))
  const [show, setShow] = useState({ areas: true, water: true, survey: true })
  const [sortBy, setSortBy] = useState('pis')
  const [search, setSearch] = useState('')
  const [resetTick, setResetTick] = useState(0)
  const [flyTarget, setFlyTarget] = useState(null)
  const [requestArea, setRequestArea] = useState(null)
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)
  const { data, loading, error, reload } = useAsync(() => api.get(`/api/map${qs({ species, days })}`), [species, days])

  const focusId = Number(params.get('area') || areaId || 0)
  const areas = useMemo(() => (data?.areas || []).filter((a) => levels.has(essKey(a.ess_class))), [data, levels])
  const visibleIds = useMemo(() => new Set(areas.map((a) => a.area_id)), [areas])
  const byId = useMemo(() => Object.fromEntries((data?.areas || []).map((a) => [a.area_id, a])), [data])
  const bounds = useMemo(() => {
    if (!data?.areas?.length) return null
    const focus = focusId && byId[focusId]
    return L.latLngBounds((focus ? [focus] : data.areas).flatMap((a) => a.polygon))
  }, [data, focusId, byId])

  const ranked = useMemo(() => {
    const term = search.trim().toLowerCase()
    const list = areas.filter((a) => !term || a.area_name.toLowerCase().includes(term) || a.area_code.toLowerCase().includes(term))
    const value = (a) => (sortBy === 'pis' ? a.pis : sortBy === 'ess' ? a.ess : a.completeness)
    return [...list].sort((a, b) => (sortBy === 'completeness' ? (value(a) - value(b)) : ((value(b) ?? -1) - (value(a) ?? -1))))
  }, [areas, sortBy, search])

  async function submitRequest() {
    setSending(true)
    try {
      const alert = await api.post('/api/alerts', { area_id: requestArea.area_id, note })
      toast.success(alert.is_new ? `Đã tạo đề xuất ${alert.code} — đang chờ người có thẩm quyền duyệt.` : `Đã cập nhật đề xuất đang chờ ${alert.code} (không tạo trùng).`)
      setRequestArea(null); setNote('')
      window.dispatchEvent(new Event('vw-alerts-changed'))
      navigate(`/alerts?id=${alert.id}`)
    } catch (err) { toast.error(err.message) } finally { setSending(false) }
  }

  if (loading) return <Loading label="Đang tải lớp bản đồ…" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data.has_data) return <Card><EmptyState title="Chưa có dữ liệu để hiển thị bản đồ" hint="Nhập dữ liệu thời tiết ở trang Quản lý dữ liệu." /></Card>

  const toggleLevel = (key) => setLevels((prev) => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next })
  const actions = (area) => (
    <div className="mt-2 flex flex-wrap gap-1.5">
      <Button size="sm" variant="secondary" icon={Microscope} onClick={() => navigate(`/analysis?area=${area.area_id}`)}>Xem phân tích</Button>
      <Button size="sm" icon={ClipboardPlus} disabled={!can('alert.create')} title={can('alert.create') ? '' : 'Vai trò của bạn không có quyền tạo đề xuất'} onClick={() => setRequestArea(area)}>Tạo yêu cầu kiểm tra</Button>
    </div>
  )

  return (
    <div className="flex h-full min-h-[560px] flex-col gap-3">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-2 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <label className="flex flex-col text-xs font-semibold text-slate-600">Loài véc-tơ
          <select className="input mt-1 !w-48 !py-1.5" value={species} onChange={(e) => setSpecies(e.target.value)}>
            {meta.species.map((s) => <option key={s.key} value={s.key} disabled={!s.configured}>{s.label}{s.configured ? '' : ' (chưa cấu hình trong MVP)'}</option>)}
          </select>
        </label>
        <div className="text-xs">
          <div className="font-semibold text-slate-600">Kỳ phân tích (theo bộ lọc thời gian)</div>
          <div className="mt-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-sm">{fmtDate(data.period.start)} → {fmtDate(data.period.end)}</div>
        </div>
        <fieldset className="text-xs">
          <legend className="font-semibold text-slate-600">Mức đánh giá ESS</legend>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {Object.entries(ESS_LEVELS).map(([key, lv]) => (
              <label key={key} className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-2 py-1 ${levels.has(key) ? 'border-slate-400 bg-white' : 'border-slate-200 bg-slate-100 text-slate-400'}`}>
                <input type="checkbox" className="sr-only" checked={levels.has(key)} onChange={() => toggleLevel(key)} />
                <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: lv.color, opacity: levels.has(key) ? 1 : 0.35 }} />{lv.label}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="text-xs">
          <legend className="font-semibold text-slate-600">Loại điểm / lớp</legend>
          <div className="mt-1 flex gap-3 py-1">
            {[['areas', 'Khu vực'], ['water', 'Điểm nước đọng'], ['survey', 'Điểm khảo sát']].map(([key, label]) => (
              <label key={key} className="flex cursor-pointer items-center gap-1.5"><input type="checkbox" checked={show[key]} onChange={() => setShow((s) => ({ ...s, [key]: !s[key] }))} />{label}</label>
            ))}
          </div>
        </fieldset>
        <Button variant="secondary" size="sm" icon={LocateFixed} onClick={() => setResetTick((t) => t + 1)} className="ml-auto">Về toàn cảnh</Button>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[1fr_340px]">
        <div className="relative min-h-[420px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <MapContainer bounds={bounds} className="h-full w-full" scrollWheelZoom zoomSnap={0.25}>
            <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            <FitBounds bounds={bounds} trigger={resetTick} />
            <FlyTo target={flyTarget} />
            {show.areas && areas.map((a) => {
              const lv = ESS_LEVELS[essKey(a.ess_class)]
              const focused = a.area_id === focusId
              return (
                <Polygon key={`${a.area_id}-${focused}`} positions={a.polygon}
                  pathOptions={{ color: focused ? '#0f172a' : '#334155', weight: focused ? 3 : 1.2, fillColor: lv.color, fillOpacity: a.ess === null ? 0.25 : 0.42, dashArray: a.ess === null ? '5 5' : null }}>
                  <Tooltip permanent direction="center" className="area-label">{a.area_code.replace('KV-', '')} · {a.ess === null ? 'thiếu DL' : a.ess}</Tooltip>
                  <Popup>
                    <div className="mb-1 flex items-center justify-between gap-2"><b className="text-sm">{a.area_name}</b><span className="text-[11px] text-slate-500">{a.area_code}</span></div>
                    <AreaSummary area={a} />
                    <div className="mt-1.5 text-[11px] text-slate-500">Kỳ {fmtDate(a.start_date)} → {fmtDate(a.end_date)} · scoring {a.scoring_version}<br />Nguồn: {a.sources.join('; ') || '—'} · Ô lưới giả lập, không phải ranh giới hành chính thật.</div>
                    {actions(a)}
                  </Popup>
                </Polygon>
              )
            })}
            {show.water && data.water_points.filter((p) => visibleIds.has(p.area_id)).map((p) => (
              <Marker key={`w${p.id}`} position={[p.latitude, p.longitude]} icon={waterIcon(p.status !== 'active')}>
                <Popup>
                  <b className="text-sm">Điểm nước đọng {p.code}</b>
                  <div className="mt-1 space-y-0.5">
                    <Row label="Tọa độ">{p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}</Row>
                    <Row label="Ngày ghi nhận">{fmtDate(p.observed_date)}</Row>
                    <Row label="Loại điểm">{p.water_type}</Row>
                    <Row label="Trạng thái">{p.status === 'active' ? 'Đang tồn tại' : 'Đã xử lý'}</Row>
                    <Row label="Tồn tại">{p.persistence_days ?? '—'} ngày</Row>
                    <Row label="Khu vực">{byId[p.area_id]?.area_name}</Row>
                    <Row label="ESS / PIS khu vực">{byId[p.area_id]?.ess ?? '—'} / {byId[p.area_id]?.pis ?? '—'}</Row>
                    <Row label="Dữ liệu thiếu (khu vực)">{missingText(byId[p.area_id]?.missing) || 'Không'}</Row>
                    <Row label="Nguồn">{p.source}</Row>
                  </div>
                  {byId[p.area_id] && actions(byId[p.area_id])}
                </Popup>
              </Marker>
            ))}
            {show.survey && data.surveys.filter((s) => visibleIds.has(s.area_id)).map((s) => (
              <Marker key={`s${s.id}`} position={[s.latitude, s.longitude]} icon={surveyIcon(s.result)}>
                <Popup>
                  <b className="text-sm">Điểm khảo sát {s.code}</b>
                  <div className="mt-1 space-y-0.5">
                    <Row label="Tọa độ">{s.latitude.toFixed(5)}, {s.longitude.toFixed(5)}</Row>
                    <Row label="Ngày khảo sát">{fmtDate(s.survey_date)}</Row>
                    <Row label="Loài">{s.species}</Row>
                    <Row label="Kết quả">{s.result_label}</Row>
                    <Row label="Số lượng đếm">{s.vector_count ?? 'Không đếm'}</Row>
                    <Row label="Khu vực">{byId[s.area_id]?.area_name}</Row>
                    <Row label="ESS / PIS khu vực">{byId[s.area_id]?.ess ?? '—'} / {byId[s.area_id]?.pis ?? '—'}</Row>
                    <Row label="Dữ liệu thiếu (khu vực)">{missingText(byId[s.area_id]?.missing) || 'Không'}</Row>
                    <Row label="Nguồn">{s.source}</Row>
                  </div>
                  {s.result === 'not_surveyed' && <div className="mt-1 text-[11px] text-amber-700">“Chưa khảo sát” không phải bằng chứng không có véc-tơ.</div>}
                  {byId[s.area_id] && actions(byId[s.area_id])}
                </Popup>
              </Marker>
            ))}
          </MapContainer>

          <div className="absolute bottom-3 left-3 z-[500] w-56 rounded-lg border border-slate-200 bg-white/95 p-3 text-xs shadow">
            <div className="mb-1.5 flex items-center justify-between font-semibold text-slate-800">Chú giải <SampleTag /></div>
            <div className="mb-1 font-medium text-slate-600">Nhóm ESS (0–100, ngưỡng minh họa)</div>
            {Object.entries(ESS_LEVELS).map(([key, lv]) => (
              <div key={key} className="flex items-center gap-2 py-0.5">
                <span className="h-3 w-5 rounded-sm border border-slate-400" style={{ backgroundColor: lv.color, opacity: key === 'not_scored' ? 0.6 : 0.75, borderStyle: key === 'not_scored' ? 'dashed' : 'solid' }} />
                <span>{lv.label}</span><span className="ml-auto text-slate-400">{lv.range}</span>
              </div>
            ))}
            <div className="mb-1 mt-2 font-medium text-slate-600">Ký hiệu điểm</div>
            <div className="flex items-center gap-2 py-0.5"><span dangerouslySetInnerHTML={{ __html: waterIcon(false).options.html }} />Nước đọng (tròn, xám = đã xử lý)</div>
            <div className="flex items-center gap-2 py-0.5"><span dangerouslySetInnerHTML={{ __html: surveyIcon('larvae_present').options.html }} />Khảo sát: + có ghi nhận</div>
            <div className="flex items-center gap-2 py-0.5"><span dangerouslySetInnerHTML={{ __html: surveyIcon('none_found').options.html }} />Khảo sát: – không ghi nhận</div>
            <div className="flex items-center gap-2 py-0.5"><span dangerouslySetInnerHTML={{ __html: surveyIcon('not_surveyed').options.html }} />Khảo sát: ? chưa khảo sát</div>
          </div>
        </div>

        <Card title="Khu vực ưu tiên" subtitle={`${ranked.length} khu vực theo bộ lọc`} bodyClass="p-0" className="flex min-h-0 flex-col">
          <div className="space-y-2 border-b border-slate-100 p-3">
            <div className="relative">
              <Search size={15} className="absolute left-2.5 top-2.5 text-slate-400" />
              <input className="input !pl-8" placeholder="Tìm khu vực…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Tìm khu vực" />
            </div>
            <select className="input !py-1.5" value={sortBy} onChange={(e) => setSortBy(e.target.value)} aria-label="Sắp xếp">
              <option value="pis">Sắp xếp: PIS cao → thấp</option>
              <option value="ess">Sắp xếp: ESS cao → thấp</option>
              <option value="completeness">Sắp xếp: thiếu dữ liệu nhiều nhất</option>
            </select>
          </div>
          {ranked.length === 0 ? <EmptyState title="Không có khu vực phù hợp" hint="Bật thêm mức đánh giá hoặc xóa từ khóa tìm kiếm." /> : (
            <ul className="max-h-[calc(100vh-420px)] min-h-48 divide-y divide-slate-100 overflow-y-auto">
              {ranked.map((a, i) => (
                <li key={a.area_id} className={`p-3 ${a.area_id === focusId ? 'bg-brand-50' : ''}`}>
                  <button className="w-full text-left" onClick={() => setFlyTarget({ center: a.centroid, t: Date.now() })} title="Phóng tới khu vực trên bản đồ">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-800">{i + 1}. {a.area_name}</span>
                      <PisBadge cls={a.pis_class} value={a.pis} />
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <EssBadge cls={a.ess_class} value={a.ess} />
                      <span>{a.features.water_points_active ?? '—'} điểm nước đọng</span>
                      {a.missing.length > 0 && <span className="font-medium text-amber-700">Thiếu: {missingText(a.missing)}</span>}
                    </div>
                  </button>
                  {actions(a)}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {requestArea && (
        <Modal title={`Tạo yêu cầu kiểm tra — ${requestArea.area_name}`} onClose={() => setRequestArea(null)}
          footer={<><Button variant="secondary" onClick={() => setRequestArea(null)}>Hủy</Button><Button loading={sending} onClick={submitRequest}>Tạo đề xuất (chờ duyệt)</Button></>}>
          <div className="space-y-3">
            <Notice tone="info">Hệ thống sẽ chạy lại phân tích 7 ngày gần nhất cho khu vực và tạo một <b>đề xuất ở trạng thái chờ duyệt</b>. Không có hành động nào được phát ra ngoài hệ thống trước khi người có thẩm quyền phê duyệt.</Notice>
            <div className="rounded-lg border border-slate-200 p-3 text-sm"><AreaSummary area={requestArea} /></div>
            <Field label="Ghi chú (tùy chọn)"><textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ví dụ: người dân phản ánh nhiều lốp xe cũ đọng nước sau mưa" /></Field>
          </div>
        </Modal>
      )}
    </div>
  )
}
