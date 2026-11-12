# Phân công nhóm VectorWatch AI

Nhóm 5 thành viên. Mỗi người phụ trách một mảng có khối lượng tương đương: một phần backend, phần giao diện tương ứng và test của mảng đó. Mỗi người tự commit phần việc của mình bằng tài khoản GitHub riêng, để lịch sử Git cho thấy ai làm phần nào.

## Bảng phân công

| Thành viên | Mảng phụ trách | Thư mục / file chính | Giao diện liên quan |
|---|---|---|---|
| **Thắng** | AI Agent: Orchestrator, 4 Agent, công cụ, lớp LLM, Trợ lý hỏi đáp; quản lý repo và triển khai Render | `backend/app/agents/`, `backend/app/routers/tasks.py`, `backend/app/routers/agent.py`, `render.yaml` | AI Agent Center (`AgentCenter.jsx`, `AssistantPanel.jsx`) |
| **Thảo** | Khung giao diện và trải nghiệm người dùng: bố cục, điều hướng, đăng nhập, Dashboard, thành phần dùng chung | `frontend/src/components/Layout.jsx`, `frontend/src/components/ui.jsx`, `frontend/src/lib/`, `frontend/src/App.jsx` | Đăng nhập, Dashboard, Cài đặt (`Login.jsx`, `Dashboard.jsx`, `SettingsPage.jsx`) |
| **Thành** | Dữ liệu: cơ sở dữ liệu, dữ liệu mẫu, nhập CSV/Excel và kiểm tra dữ liệu | `backend/app/db.py`, `backend/app/seed.py`, `backend/app/services/validation.py`, `backend/app/routers/data.py`, `sample_data/` | Quản lý dữ liệu (`DataPage.jsx`) |
| **Tâm** | Phân tích: công thức ESS/PIS, tạo đặc trưng, phân tích theo khu vực, bản đồ | `backend/app/services/scoring.py`, `features.py`, `analysis.py`, `overview.py`, `geo.py`, `backend/app/routers/analysis.py`, `mapdata.py`, `dashboard.py` | Phân tích môi trường, Bản đồ nguy cơ (`AnalysisPage.jsx`, `MapPage.jsx`) |
| **Việt** | Cảnh báo, phê duyệt, phân quyền, báo cáo, kiểm thử và tài liệu | `backend/app/services/alerts.py`, `reports.py`, `testcases.py`, `backend/app/security.py`, `backend/app/routers/alerts.py`, `reports.py`, `auth.py`, `backend/tests/`, `README.md` | Cảnh báo & phê duyệt, Báo cáo & đánh giá (`AlertsPage.jsx`, `ReportsPage.jsx`) |

Việc chung: mỗi người viết hoặc cập nhật test cho mảng của mình, và trình bày mảng đó khi demo. Thắng gộp code vào nhánh `main` và gắn tag phiên bản demo.

## Quy ước Git

**Tên nhánh:** `ten/mang-viec`, viết không dấu, chữ thường. Ví dụ:

- `thang/agent-orchestrator`
- `thao/giao-dien-dashboard`
- `thanh/nhap-du-lieu`
- `tam/scoring-ess-pis`
- `viet/canh-bao-bao-cao`

**Nội dung commit:** `loại(mảng): mô tả ngắn`. Ví dụ:

- `feat(agent): thêm bước xác minh kết quả`
- `fix(du-lieu): báo lỗi khi tọa độ bị đảo`
- `test(scoring): thêm ca thiếu dữ liệu độ ẩm`
- `docs(readme): cập nhật hướng dẫn chạy`

Loại thường dùng: `feat` (chức năng mới), `fix` (sửa lỗi), `test`, `docs`, `refactor`, `style`.

**Quy trình:**

1. Lấy bản mới nhất: `git checkout main` rồi `git pull`.
2. Tạo nhánh của mình: `git checkout -b ten/mang-viec`.
3. Sửa code, chạy test (`cd backend && python -m pytest -q tests`), rồi `git add` và `git commit`.
4. Đẩy nhánh lên: `git push -u origin ten/mang-viec`.
5. Tạo **Pull Request** vào `main` trên GitHub; một thành viên khác xem lại rồi gộp.

Trước khi commit, cấu hình đúng tên và email của mình (chỉ cần làm một lần trên mỗi máy):

```bash
git config --global user.name "Họ Tên"
git config --global user.email "email-github-cua-ban@example.com"
```

**Không commit:** file `.env`, khóa API, mật khẩu thật, thư mục `.venv`, `node_modules`, file `backend/data/*.db`. Các mục này đã có trong `.gitignore`.
