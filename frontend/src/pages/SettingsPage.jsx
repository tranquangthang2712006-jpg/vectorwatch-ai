import { Lock } from 'lucide-react'
import { useApp } from '../lib/context.jsx'
import { Badge, Card, Notice } from '../components/ui.jsx'

const FACTOR = { rainfall: 'Lượng mưa quy đổi 7 ngày (mm)', temperature: 'Nhiệt độ trung bình (°C)', humidity: 'Độ ẩm trung bình (%)', water: 'Số điểm nước đọng đang tồn tại', survey: 'Bằng chứng khảo sát' }

export default function SettingsPage() {
  const { meta, user } = useApp()
  const sc = meta.scoring
  const aedes = sc.species.aedes
  return (
    <div className="space-y-4">
      <Notice tone="warning"><b>Cấu hình minh họa — chưa được chuyên gia xác nhận.</b> {sc.notice}</Notice>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title={`Công thức ESS — Aedes (${sc.version})`} subtitle="ESS = Σ trọng số × điểm thành phần; thiếu thành phần nào thì chia lại trọng số trên phần còn lại"
          actions={<span className="inline-flex items-center gap-1 text-xs text-slate-500"><Lock size={12} />Chỉ đọc</span>}>
          <table className="w-full"><thead className="bg-slate-50"><tr><th className="th">Thành phần</th><th className="th">Trọng số</th><th className="th">Đường cong điểm (giá trị → điểm)</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(aedes.ess_weights).map(([key, w]) => (
                <tr key={key}><td className="td font-medium">{FACTOR[key]}</td><td className="td num">{Math.round(w * 100)}%</td>
                  <td className="td text-xs">{key === 'survey' ? `Điểm = ${aedes.survey.base_when_none_found} + ${aedes.survey.span} × tỷ lệ lượt khảo sát dương tính (30 ngày)` : aedes.curves[key].map(([x, y]) => `${x} → ${y}`).join(' · ')}</td></tr>
              ))}
            </tbody></table>
          <p className="mt-3 text-xs text-slate-500">Cần ít nhất {Math.round(sc.min_completeness * 100)}% trọng số có dữ liệu thì mới tính ESS. Thay đổi cấu hình phải qua sửa mã nguồn có kiểm soát (<code>backend/app/services/scoring.py</code>) và tăng phiên bản.</p>
        </Card>
        <Card title="Công thức PIS và ngưỡng phân loại" actions={<span className="inline-flex items-center gap-1 text-xs text-slate-500"><Lock size={12} />Chỉ đọc</span>}>
          <p className="text-sm text-slate-700">PIS = {Object.entries(sc.pis_weights).map(([k, w]) => `${w} × ${{ ess: 'ESS', water: 'WaterScore', survey: 'SurveyEvidence', change: 'ChangeScore' }[k]}`).join(' + ')}</p>
          <p className="mt-1 text-xs text-slate-500">ChangeScore = clamp(ΔESS so với kỳ trước × {sc.change_points_per_ess}, 0, 100) — chỉ tính phần ESS tăng.</p>
          <div className="mt-3 grid grid-cols-2 gap-4">
            <div><div className="mb-1 text-xs font-semibold text-slate-600">Nhóm ESS</div>
              <ul className="space-y-1 text-sm">{sc.ess_classes.map((c) => <li key={c.key} className="flex justify-between gap-2"><span>{c.label}</span><span className="num text-slate-500">{c.min}–{c.max === 100 ? 100 : c.max - 1}</span></li>)}</ul></div>
            <div><div className="mb-1 text-xs font-semibold text-slate-600">Mức PIS</div>
              <ul className="space-y-1 text-sm">{sc.pis_classes.map((c) => <li key={c.key} className="flex justify-between gap-2"><span>{c.label}</span><span className="num text-slate-500">{c.min}–{c.max === 100 ? 100 : c.max - 1}</span></li>)}</ul></div>
          </div>
        </Card>
        <Card title="Danh mục loài (species registry)">
          <ul className="space-y-2 text-sm">{meta.species.map((s) => <li key={s.key} className="flex items-center justify-between"><span>{s.label}</span>{s.configured ? <Badge color="#15803d">Đã cấu hình (demo)</Badge> : <Badge color="#64748b">Chưa cấu hình — không tính điểm</Badge>}</li>)}</ul>
          <p className="mt-3 text-xs text-slate-500">Không dùng chung ngưỡng Aedes cho loài khác. Loài chưa cấu hình sẽ bị từ chối ở API.</p>
        </Card>
        <Card title="AI Agent">
          <dl className="grid grid-cols-[150px_1fr] gap-y-1.5 text-sm">
            <dt className="text-slate-500">Chế độ LLM</dt><dd>{meta.agent.llm_description}</dd>
            {meta.agent.llm_mode === 'llm' && <><dt className="text-slate-500">Máy chủ LLM</dt><dd>{meta.agent.llm_host} · khóa API: {meta.agent.llm_key_configured ? 'đã cấu hình (ẩn)' : 'không có'}</dd></>}
            {meta.agent.llm_warning && <><dt className="text-slate-500">Cảnh báo cấu hình</dt><dd className="text-amber-700">{meta.agent.llm_warning}</dd></>}
            <dt className="text-slate-500">Lần gọi LLM</dt><dd>{Object.keys(meta.agent.llm_call_stats).length ? Object.entries(meta.agent.llm_call_stats).map(([k, v]) => `${k}: ${v}`).join(' · ') : 'Chưa có'}</dd>
            <dt className="text-slate-500">Workflow</dt><dd>{meta.agent.workflow.map((w) => w.label).join(' → ')}</dd>
            <dt className="text-slate-500">Công cụ cho phép</dt><dd className="font-mono text-xs">{meta.agent.tools.join(', ')}</dd>
            <dt className="text-slate-500">Retry công cụ</dt><dd>Tối đa {meta.agent.max_tool_retries} lần thử lại mỗi lần gọi</dd>
          </dl>
          <p className="mt-3 text-xs text-slate-500">Bật LLM thật bằng biến VW_LLM_PROVIDER=openai_compatible, VW_LLM_BASE_URL, VW_LLM_MODEL, VW_LLM_API_KEY trong file .env. LLM chỉ phân loại ý định và diễn đạt lại; đầu ra bị kiểm tra, lỗi thì dùng luật dự phòng. Tính điểm và gọi công cụ luôn do hệ thống thực hiện.</p>
        </Card>
        <Card title="Chính sách công cụ (Tool Guardrails)" className="xl:col-span-2" subtitle="Mỗi công cụ chỉ được gọi bởi Agent được cấp quyền; Trợ lý hỏi đáp chỉ được dùng công cụ không ghi dữ liệu">
          <table className="w-full"><thead className="bg-slate-50"><tr><th className="th">Công cụ</th><th className="th">Agent được phép</th><th className="th">Ghi dữ liệu</th></tr></thead>
            <tbody className="divide-y divide-slate-100">{meta.agent.tool_policy.map((t) => <tr key={t.name}><td className="td font-mono text-xs">{t.name}</td><td className="td">{t.agents.join(', ')}</td><td className="td">{t.writes ? <Badge color="#b45309">Có — {t.writes_what}</Badge> : <Badge color="#15803d">Không (chỉ đọc)</Badge>}</td></tr>)}</tbody></table>
        </Card>
        <Card title="Vai trò và quyền" className="xl:col-span-2" subtitle={`Bạn đang đăng nhập với vai trò: ${user.role_label}`}>
          <table className="w-full"><thead className="bg-slate-50"><tr><th className="th">Vai trò</th><th className="th">Quyền thao tác (ngoài quyền xem)</th></tr></thead>
            <tbody className="divide-y divide-slate-100">{meta.roles.map((r) => <tr key={r.key} className={r.key === user.role ? 'bg-brand-50' : ''}><td className="td font-medium">{r.label}</td><td className="td">{r.permissions.length ? r.permissions.join(' · ') : 'Chỉ xem'}</td></tr>)}</tbody></table>
          <p className="mt-3 text-xs text-slate-500">Quản lý tài khoản, đổi mật khẩu và cấu hình nguồn dữ liệu chưa có giao diện trong bản MVP.</p>
        </Card>
      </div>
    </div>
  )
}
