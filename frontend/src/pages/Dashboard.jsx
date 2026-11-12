import { useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, BellRing, MapPinned, Plus, Radar } from 'lucide-react'
import { useApp, useAsync } from '../lib/context.jsx'
import { api, qs } from '../lib/api.js'
import { ESS_LEVELS, fmtDate, fmtDateTime, fmtNum, missingText } from '../lib/format.js'
import { AlertStatusBadge, Button, Card, EmptyState, ErrorState, EssBadge, Loading, PisBadge, SampleTag, SeverityBadge, TaskStatusBadge } from '../components/ui.jsx'

function Kpi({ icon: Icon, label, value, note, tone, onClick }) {
  return (
    <button onClick={onClick} className="group rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-brand-500 hover:shadow">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</span>
        <span className="rounded-lg p-1.5" style={{ backgroundColor: `${tone}18`, color: tone }}><Icon size={17} /></span>
      </div>
      <div className="num mt-2 text-3xl font-bold text-slate-900">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{note}</div>
      <div className="mt-2 text-xs font-medium text-brand-700 opacity-0 transition group-hover:opacity-100">Mở chi tiết →</div>
    </button>
  )
}

export default function Dashboard() {
  const { areaId, days, can } = useApp()
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => api.get(`/api/dashboard${qs({ area_id: areaId, days })}`), [areaId, days])

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data.has_data) {
    return <Card><EmptyState title="Chưa có dữ liệu thời tiết" hint="Hãy nhập dữ liệu ở trang Quản lý dữ liệu để bắt đầu giám sát."
      action={<Button onClick={() => navigate('/data')}>Mở Quản lý dữ liệu</Button>} /></Card>
  }
  const k = data.kpis
  const dist = data.distribution.filter((d) => d.key !== 'not_scored' || d.count > 0)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-slate-600">
          Kỳ tính điểm: <b>{fmtDate(data.period.start)} → {fmtDate(data.period.end)}</b> (cửa sổ 7 ngày đến ngày dữ liệu mới nhất) · Loài: <b>Aedes</b> · <SampleTag />
        </div>
        <Button icon={Plus} disabled={!can('task.create')} title={can('task.create') ? '' : 'Vai trò của bạn không có quyền tạo nhiệm vụ'} onClick={() => navigate('/agent?new=1')}>Tạo nhiệm vụ phân tích</Button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi icon={MapPinned} tone="#1d5fd1" label="Khu vực giám sát" value={k.areas_monitored}
          note={`${k.areas_scored} khu vực tính được ESS · ${k.areas_partial} thiếu một phần dữ liệu`} onClick={() => navigate('/map')} />
        <Kpi icon={BellRing} tone="#c81e1e" label="Cảnh báo mới (chờ duyệt)" value={k.pending_alerts}
          note="Đề xuất do Agent hoặc người dùng tạo, chưa có quyết định" onClick={() => navigate('/alerts?status=pending')} />
        <Kpi icon={Radar} tone="#d97706" label="Khu vực cần kiểm tra" value={k.areas_to_inspect}
          note="Số khu vực có PIS ≥ 50 (mức “Cần kiểm tra” trở lên)" onClick={() => navigate('/map')} />
        <Kpi icon={Activity} tone="#0f766e" label="ESS trung bình" value={k.mean_ess === null ? '—' : fmtNum(k.mean_ess)}
          note="Điểm 0–100, trung bình các khu vực tính được; không phải xác suất" onClick={() => navigate('/analysis')} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Xu hướng ESS / PIS trung bình theo ngày"
          subtitle={`${data.period.trend_days} ngày gần nhất · mỗi điểm dùng cửa sổ 7 ngày kết thúc tại ngày đó · thang 0–100 · nguồn: dữ liệu mẫu giả lập`}>
          {data.trend.length === 0 ? <EmptyState title="Chưa đủ dữ liệu để vẽ xu hướng" hint="Cần ít nhất 7 ngày dữ liệu thời tiết liên tiếp." /> : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.trend} margin={{ top: 8, right: 16, left: -12, bottom: 0 }}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={(d) => fmtDate(d).slice(0, 5)} tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                  <Tooltip labelFormatter={(d) => `Ngày ${fmtDate(d)}`} formatter={(v, name) => [v === null ? 'Không tính được' : `${v} điểm`, name]} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="ess" name="ESS trung bình" stroke="#1d5fd1" strokeWidth={2.5} dot={{ r: 2.5 }} connectNulls={false} />
                  <Line type="monotone" dataKey="pis" name="PIS trung bình" stroke="#c2410c" strokeWidth={2.5} strokeDasharray="6 4" dot={{ r: 2.5 }} connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
        <Card title="Phân bố khu vực theo nhóm ESS" subtitle="Mức phù hợp môi trường theo quy tắc của hệ thống (ngưỡng minh họa)">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dist} layout="vertical" margin={{ top: 4, right: 28, left: 28, bottom: 0 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={92} />
                <Tooltip formatter={(v, _n, item) => [`${v} khu vực`, `ESS ${item.payload.range}`]} />
                <Bar dataKey="count" name="Số khu vực" radius={[0, 5, 5, 0]}>
                  {dist.map((d) => <Cell key={d.key} fill={ESS_LEVELS[d.key].color} />)}
                  <LabelList dataKey="count" position="right" style={{ fontSize: 12, fontWeight: 600, fill: '#334155' }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Cảnh báo gần đây" bodyClass="p-0"
          actions={<Button variant="ghost" size="sm" onClick={() => navigate('/alerts')}>Xem tất cả</Button>}>
          {data.recent_alerts.length === 0 ? (
            <EmptyState title="Chưa có cảnh báo nào" hint="Cảnh báo/đề xuất được tạo khi bạn chạy một nhiệm vụ phân tích trong AI Agent Center."
              action={can('task.create') && <Button size="sm" onClick={() => navigate('/agent?new=1')}>Tạo nhiệm vụ phân tích</Button>} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-slate-200 bg-slate-50"><tr>
                  <th className="th">Mã</th><th className="th">Khu vực</th><th className="th">Lý do</th><th className="th">Thời điểm</th><th className="th">Mức</th><th className="th">Trạng thái</th><th className="th">Phụ trách (dự kiến)</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {data.recent_alerts.map((a) => (
                    <tr key={a.id} className="cursor-pointer hover:bg-brand-50" onClick={() => navigate(`/alerts?id=${a.id}`)}>
                      <td className="td font-medium text-brand-700">{a.code}</td>
                      <td className="td whitespace-nowrap">{a.area_name}</td>
                      <td className="td max-w-xs"><div className="font-medium">{a.type_label}</div><div className="truncate text-xs text-slate-500">{a.reasons[0]}</div></td>
                      <td className="td whitespace-nowrap text-xs">{fmtDateTime(a.created_at)}</td>
                      <td className="td"><SeverityBadge severity={a.severity} label={a.severity_label} /></td>
                      <td className="td"><AlertStatusBadge status={a.status} label={a.status_label} /></td>
                      <td className="td text-xs text-slate-500">{a.assignee}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Hoạt động Agent gần nhất" bodyClass="p-0" actions={<Button variant="ghost" size="sm" onClick={() => navigate('/agent')}>Mở Agent Center</Button>}>
          {data.recent_tasks.length === 0 ? <EmptyState title="Chưa có nhiệm vụ Agent" hint="Tạo nhiệm vụ để Orchestrator điều phối các Agent phân tích dữ liệu." /> : (
            <ul className="divide-y divide-slate-100">
              {data.recent_tasks.map((t) => (
                <li key={t.id}>
                  <button className="w-full px-4 py-3 text-left hover:bg-brand-50" onClick={() => navigate(`/agent?task=${t.id}`)}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-slate-700">{t.id}</span>
                      <TaskStatusBadge status={t.status} label={t.status_label} />
                    </div>
                    <div className="mt-1 line-clamp-2 text-sm text-slate-700">{t.objective}</div>
                    <div className="mt-1 text-xs text-slate-500">{fmtDateTime(t.created_at)} · {t.created_by}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Xếp hạng khu vực theo PIS" subtitle="Điểm cao không khẳng định có véc-tơ; cần xác minh thực địa" bodyClass="p-0">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-slate-200 bg-slate-50"><tr>
              <th className="th">Khu vực</th><th className="th">ESS</th><th className="th">PIS</th><th className="th">Mưa quy đổi 7 ngày</th><th className="th">Nhiệt độ TB</th><th className="th">Độ ẩm TB</th><th className="th">Điểm nước đọng</th><th className="th">Độ đầy đủ dữ liệu</th><th className="th"></th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.areas.map((a) => (
                <tr key={a.area_id}>
                  <td className="td whitespace-nowrap font-medium">{a.area_name} <span className="text-xs text-slate-400">{a.area_code}</span></td>
                  <td className="td"><EssBadge cls={a.ess_class} value={a.ess} /></td>
                  <td className="td"><PisBadge cls={a.pis_class} value={a.pis} /></td>
                  <td className="td num">{fmtNum(a.features.rainfall_7d)} mm</td>
                  <td className="td num">{fmtNum(a.features.temperature_mean)} °C</td>
                  <td className="td num">{a.features.humidity_mean === null ? <span className="font-medium text-amber-700">Thiếu</span> : `${fmtNum(a.features.humidity_mean)} %`}</td>
                  <td className="td num">{fmtNum(a.features.water_points_active, 0)}</td>
                  <td className="td num">{Math.round(a.completeness * 100)}%{a.missing.length > 0 && <span className="ml-1 text-xs text-amber-700">(thiếu: {missingText(a.missing)})</span>}</td>
                  <td className="td"><Button variant="ghost" size="sm" onClick={() => navigate(`/analysis?area=${a.area_id}`)}>Phân tích</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
