# VectorWatch AI — MVP

Hệ thống hỗ trợ giám sát môi trường thuận lợi cho véc-tơ truyền bệnh (muỗi...), dùng dữ liệu môi trường (mưa, nhiệt độ, độ ẩm, điểm nước đọng, khảo sát thực địa) để tính **điểm mức độ thuận lợi môi trường (ESS)** và **điểm ưu tiên kiểm tra (PIS)**, hỗ trợ đề xuất hành động với quy trình con người phê duyệt (human-in-the-loop).

> ⚠️ **Phạm vi:** Hệ thống KHÔNG chẩn đoán bệnh, KHÔNG dự đoán ca bệnh hoặc kết luận đang có dịch, KHÔNG khẳng định có véc-tơ chỉ từ dữ liệu thời tiết. Toàn bộ dữ liệu demo là **dữ liệu mẫu/giả lập**. "Chưa khảo sát" không được dùng làm bằng chứng không có véc-tơ. Trọng số/ngưỡng chấm điểm là minh hoạ, chưa được chuyên gia thẩm định.

## Dùng ngay bản online

**Link:** https://vectorwatch-ai.onrender.com

| Tài khoản | Vai trò |
|---|---|
| `officer@vectorwatch.local` | Cán bộ giám sát — có quyền phê duyệt cảnh báo (nên dùng để demo) |
| `analyst@vectorwatch.local` | Chuyên viên phân tích — tạo nhiệm vụ, nhập dữ liệu, không được duyệt |
| `admin@vectorwatch.local` | Quản trị — mọi quyền |
| `viewer@vectorwatch.local` | Người xem / giám khảo — chỉ xem |

**Mật khẩu chung cho cả 4 tài khoản:** `VW-demo-2026!`

Bản online chạy trên gói miễn phí của Render: lần mở đầu tiên sau một lúc không ai dùng có thể chờ 30–60 giây; dữ liệu trở về dữ liệu mẫu mỗi khi máy chủ khởi động lại.

## Kiến trúc tóm tắt

- **Backend:** FastAPI + SQLite thuần (không ORM), token tự ký (HMAC), phân quyền theo vai trò (admin/analyst/officer/viewer).
- **Frontend:** React 19 + Vite + Tailwind CSS v4 + React-Leaflet + Recharts.
- **AI Agent:** Orchestrator điều phối 4 agent (Data, Environmental Analysis, Geospatial, Risk & Alert) theo 2 chế độ:
  - **Nhiệm vụ workflow** (AI Agent Center → tab *Nhiệm vụ workflow*): 8 bước, gọi công cụ có log, retry, hủy/thử lại, **Orchestrator xác minh kết quả** (đúng khu vực, đúng kỳ, có phiên bản công thức, điểm có nguồn, không suy diễn khi thiếu dữ liệu, đề xuất ở trạng thái chờ duyệt) trước khi chuyển sang người duyệt.
  - **Trợ lý hỏi đáp** (tab *Trợ lý hỏi đáp*, API `POST /api/agent/chat`): hỏi bằng tiếng Việt (có dấu hoặc không dấu). Orchestrator phân loại 11 loại ý định, trích khu vực/số ngày, kiểm tra quyền, định tuyến động tới Agent phù hợp, chỉ dùng **công cụ chỉ đọc**, xác minh rồi trả lời kèm bảng số liệu, kỳ dữ liệu, nguồn, phiên bản công thức, giới hạn và truy vết. Yêu cầu "chạy phân tích" chỉ tạo **đề xuất nhiệm vụ** — người có quyền phải bấm xác nhận.
- **Chính sách công cụ:** mỗi công cụ chỉ được gọi bởi Agent được cấp quyền; công cụ ghi dữ liệu bị chặn trong chế độ chỉ đọc; mọi lần gọi (kể cả bị chặn) đều ghi log (xem *Cài đặt → Chính sách công cụ*).
- **LLM:** mặc định **mô phỏng theo luật** (không gọi mô hình). Có thể bật **LLM thật** kiểu OpenAI-compatible qua `.env` (xem mục *Bật LLM thật*). LLM chỉ phân loại ý định/trích phạm vi và diễn đạt lại; mọi điểm ESS/PIS do `backend/app/services/scoring.py` tính.
- Mọi đề xuất cảnh báo/hành động phải được người có vai trò `officer`/`admin` phê duyệt mới có hiệu lực.

## Yêu cầu hệ thống

- Python 3.10+
- Node.js 18+ (chỉ cần nếu muốn build lại frontend; bản `frontend/dist` đã build sẵn có trong ZIP)

## Cách chạy trên Windows

1. Giải nén file ZIP vào một thư mục, ví dụ `C:\vectorwatch-ai`.
2. Mở **Command Prompt** (hoặc PowerShell), `cd` vào thư mục đó.
3. Chạy:
   ```
   run.bat
   ```
   Script sẽ tự động:
   - Copy `.env.example` → `.env` nếu chưa có
   - Tạo virtual environment Python (`.venv` ở thư mục gốc) nếu chưa có
   - Cài các package trong `backend\requirements.txt`
   - Khởi động server tại `http://127.0.0.1:8000`
4. Mở trình duyệt vào `http://127.0.0.1:8000` — server đã mount sẵn `frontend/dist` nên **không cần cài Node.js** để chạy demo.
5. Đăng nhập bằng 1 trong 4 tài khoản demo (email hiển thị ở trang đăng nhập, mật khẩu chung **`VW-demo-2026!`** — giá trị `VW_DEMO_PASSWORD` trong file `.env`):
   - `admin@vectorwatch.local`
   - `analyst@vectorwatch.local`
   - `officer@vectorwatch.local` (có quyền phê duyệt cảnh báo)
   - `viewer@vectorwatch.local`

> Nếu double-click `run.bat` bị chặn bởi Windows SmartScreen, chọn "More info" → "Run anyway", hoặc chạy từ Command Prompt như trên.

## Cách chạy trên Linux/macOS

```bash
chmod +x run.sh
./run.sh
```
rồi mở `http://127.0.0.1:8000`.

## Build lại frontend (tuỳ chọn, cần Node.js)

Bản `frontend/dist` đã có sẵn trong ZIP nên bước này **không bắt buộc**. Nếu muốn chỉnh sửa giao diện và build lại:

```bash
cd frontend
npm install
npm run build
```
Sau khi build xong, khởi động lại backend (`run.sh`/`run.bat`) để phục vụ bản mới từ `frontend/dist`.

## Chạy test backend

```bash
cd backend
# kích hoạt venv trước (..\.venv\Scripts\activate trên Windows, hoặc source ../.venv/bin/activate)
python -m pytest -q tests
```
Kỳ vọng: 62 test pass (bộ 6 test case TC01–TC06 theo đặc tả, test trợ lý/chính sách công cụ/xác minh, test LLM thật bằng máy chủ giả cục bộ, và các unit/integration test khác).

Có thể xem và chạy lại 6 test case (TC01–TC06) ngay trên giao diện: trang **Báo cáo và đánh giá → tab Đánh giá**.

## Đưa lên mạng bằng Render (cách bản online đang chạy)

Bản online được triển khai trên [Render](https://render.com), gói Free, khu vực Singapore, tự cập nhật mỗi khi đẩy code lên nhánh `main` của GitHub. Để triển khai lại ở tài khoản khác:

1. Đưa mã nguồn lên GitHub (không có `.env`, `node_modules`, `.venv`).
2. Đăng nhập Render bằng GitHub. Render **yêu cầu thêm thẻ Visa/Mastercard** đã bật thanh toán quốc tế để xác minh (giữ tạm 1 USD rồi hoàn lại), kể cả với gói Free.
3. **New → Web Service** → chọn repository, rồi điền:

| Mục | Giá trị |
|---|---|
| Language | Python 3 |
| Branch | `main` |
| Region | Singapore |
| Root Directory | để trống |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Compute | $0 / month (Free) |
| Health Check Path | `/api/health` |

4. Environment Variables:

| KEY | VALUE |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `VW_DEMO_PASSWORD` | `VW-demo-2026!` |
| `VW_SECRET_KEY` | bấm **Generate** |
| `VW_STEP_DELAY` | `0.9` |

5. Bấm **Deploy web service**, chờ trạng thái **Live** (khoảng 3–5 phút), link nằm ở đầu trang của service.

Cách khác: **New → Blueprint** dùng file `render.yaml` có sẵn trong dự án (Render sẽ hỏi giá trị `VW_DEMO_PASSWORD`).

Đổi mật khẩu bản online: Render → service → **Environment** → sửa `VW_DEMO_PASSWORD` → **Save, rebuild and deploy**. Vì dữ liệu được tạo lại mỗi lần khởi động, mật khẩu mới có hiệu lực ngay sau khi triển khai xong.

## Bật LLM thật (tùy chọn)

Sửa file `.env` ở thư mục gốc (không phải `.env.example`), rồi khởi động lại `run.bat`:

```
VW_LLM_PROVIDER=openai_compatible
VW_LLM_BASE_URL=https://api.openai.com/v1
VW_LLM_MODEL=gpt-4o-mini
VW_LLM_API_KEY=<khóa của bạn>
```

Dùng được với mọi dịch vụ có endpoint `/chat/completions` kiểu OpenAI (Groq, OpenRouter, Ollama chạy cục bộ `http://localhost:11434/v1` không cần khóa…). Cơ chế an toàn:

- LLM chỉ được chọn ý định trong danh sách cho phép; mã khu vực/số ngày nó trả về được đối chiếu với danh mục, giá trị lạ bị bỏ.
- Câu trả lời do LLM diễn đạt bị **kiểm tra đối chiếu**: có con số hoặc mã khu vực không nằm trong dữ kiện đã tính, hoặc có nội dung về ca bệnh/dịch → bị loại, dùng mẫu câu xác định.
- Câu hỏi của người dùng được bọc như dữ liệu (chống prompt injection); LLM không có công cụ, không thấy khóa.
- LLM lỗi/timeout/sai cấu hình → tự lùi về luật, hệ thống vẫn chạy. Mỗi lần gọi LLM được ghi siêu dữ liệu (không lưu khóa, không lưu prompt) vào bảng `llm_calls`.

## Dữ liệu mẫu để demo luồng nhập liệu

Thư mục `sample_data/` chứa 4 file CSV dùng để demo trang **Quản lý dữ liệu**:

- `thoi_tiet_hop_le.csv` — dữ liệu thời tiết hợp lệ
- `thoi_tiet_co_loi.csv` — có lỗi cố ý (mã khu vực sai, ngày sai định dạng, giá trị ngoài khoảng, thiếu trường bắt buộc) để demo khả năng báo lỗi theo dòng
- `diem_nuoc_dong_co_loi.csv` — điểm nước đọng có lỗi (thiếu mã, toạ độ bị đảo lat/lng, toạ độ ngoài vùng khảo sát, trạng thái không hợp lệ)
- `khao_sat_hop_le.csv` — dữ liệu khảo sát hợp lệ

Vào **Quản lý dữ liệu → Nhập dữ liệu → Tải file lên**, chọn 1 trong các file trên để xem luồng xem trước (preview) → báo lỗi theo dòng kèm gợi ý sửa → xác nhận ghi.

## Cấu hình (.env)

Xem `.env.example`. Các biến chính:

- `VW_DEMO_PASSWORD` — mật khẩu chung cho 4 tài khoản demo (mặc định `VW-demo-2026!`; nếu xoá dòng này, hệ thống tự sinh và in ra console khi tạo dữ liệu lần đầu). Đổi mật khẩu sau khi đã chạy: `cd backend && python -m app.seed --reset`
- `VW_SECRET_KEY` — khoá ký token, nên đặt giá trị riêng khi triển khai thật
- `VW_STEP_DELAY` — độ trễ giả lập giữa các bước Agent (giây), phục vụ demo trực quan
- `VW_LLM_PROVIDER` — `simulated` (mặc định) hoặc `openai_compatible` (xem mục *Bật LLM thật*)

**Không commit file `.env` thật** (đã có trong `.gitignore`); ZIP này không chứa `.env`, chỉ chứa `.env.example`.

## Phần dùng dữ liệu mẫu/mô phỏng vs phần thật

| Phần | Trạng thái |
|---|---|
| Dữ liệu thời tiết/nước đọng/khảo sát | **Mẫu/giả lập**, sinh từ `backend/app/seed.py`, gắn nhãn `SAMPLE_SOURCE_LABEL` |
| Tính điểm ESS/PIS | **Thật** — hàm Python xác định, không dùng LLM |
| Phân loại ý định, trích phạm vi, diễn đạt câu trả lời | **Mô phỏng theo luật** mặc định; **LLM thật** nếu cấu hình `.env` (có kiểm tra đầu ra + dự phòng) |
| Kế hoạch workflow và định tuyến Agent | **Thật**, do Orchestrator xác định theo ý định (LLM không thêm/bớt bước hay công cụ) |
| Trợ lý hỏi đáp, chính sách công cụ, xác minh kết quả | **Thật** |
| Giải thích kết quả phân tích (câu văn) | **Thật nhưng theo mẫu câu xác định**, không dùng LLM sinh văn bản |
| Orchestrator điều phối 4 agent, gọi tool, retry khi lỗi | **Thật** |
| Phê duyệt/từ chối cảnh báo, phân quyền | **Thật** |
| Xuất báo cáo Excel | **Thật** (openpyxl) |

## Những tích hợp còn thiếu để nối API/LLM thật

- LLM thật đã có lớp kết nối OpenAI-compatible (`backend/app/agents/llm.py`) nhưng **chưa được thử với một dịch vụ thật** trong quá trình phát triển (chỉ thử với máy chủ giả lập trong test). Nếu dùng API khác chuẩn (ví dụ Anthropic Messages API gốc) cần viết thêm một lớp tương tự `OpenAICompatLLM`.
- Workflow chưa dùng LangGraph như đặc tả đề xuất; Orchestrator là máy trạng thái tự viết (có log, retry, hủy, thử lại, khôi phục khi khởi động lại).
- Thay nguồn dữ liệu seed (`backend/app/seed.py`) bằng kết nối API/cảm biến thời tiết thật, hệ thống GIS thật cho vùng khảo sát (hiện đang dùng polygon tổng hợp + ray casting tự viết, chưa dùng thư viện GIS chuyên dụng).
- Cân nhắc dùng database production (PostgreSQL) thay SQLite nếu mở rộng quy mô nhiều người dùng đồng thời.
- Trọng số/ngưỡng trong `backend/app/services/scoring.py` cần được chuyên gia y tế công cộng/côn trùng học thẩm định trước khi dùng ngoài demo.

## Vấn đề còn tồn tại / giới hạn đã biết

- Chỉ loài Aedes được cấu hình đầy đủ trong `SPECIES_REGISTRY`; Anopheles/Culex đã có khung nhưng chưa cấu hình (trả lỗi rõ ràng khi chọn).
- Chưa có cơ chế gửi thông báo đẩy/email khi có cảnh báo mới (chỉ hiển thị trên UI).
- Xuất báo cáo PDF dùng in từ trình duyệt (không có engine PDF phía server).
- Trợ lý trả lời từng câu độc lập (không nhớ ngữ cảnh câu trước, ví dụ "còn KV-B thì sao?" cần nêu lại ý); lịch sử hội thoại vẫn được lưu và xem lại được.
- Trợ lý hỏi đáp chưa có trong bộ test case TC01–TC06 trên giao diện (đã có test tự động trong `backend/tests/test_agent.py`).
- Chưa kiểm thử tải (load testing) với số lượng dữ liệu lớn hơn nhiều so với tập mẫu.
