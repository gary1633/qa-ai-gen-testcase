---
name: banking-qa-testsuite-generator
description: Use when asked to write, generate, or design banking-grade QA test cases or a full ISTQB-style test suite from a requirement document, user story, Jira ticket text, PRD, or API/OpenAPI spec pasted into the conversation — a self-contained methodology skill, not tied to any specific repo, tool, or LLM provider.
---

# Banking QA Test Suite Generator

## Mục đích

Sinh một bộ Test Case chuẩn ISTQB, cấp độ ngân hàng, từ tài liệu yêu cầu (User Story, nội dung
Jira ticket dán tay, PRD, API/OpenAPI spec, cURL mẫu...) mà User cung cấp trực tiếp trong hội
thoại. Kỹ năng này áp dụng đồng thời **9 kỹ thuật thiết kế test** (Phân vùng Tương đương, Phân
tích Giá trị Biên, Bảng Quyết định/Pairwise, Chuyển đổi Trạng thái, Đua tranh/Idempotency, Tiêm
lỗi/Phục hồi, Độ chính xác Tính toán & Pháp chế, Bảo mật/Ký tự đặc biệt, Luồng Nghiệp vụ Đầu-cuối)
để đạt 30–50+ test case bao phủ toàn diện, trình bày theo **chuẩn 8 cột, 1 sheet duy nhất** với
tiêu đề văn phong tự nhiên bọc ngoặc kép (`Kiểm tra ... thành công khi truyền trường "..." là
"..."`).

Bảo chứng chất lượng quan trọng nhất: một **Cổng Chặn Cứng Làm Rõ (Hard-Stop Clarification Gate)**
— khi tài liệu thiếu API sample (request/response) hoặc thiếu message thành công/thất bại, kỹ năng
BẮT BUỘC dừng lại hỏi User thay vì tự bịa. Không bao giờ được bỏ qua bước này.

Kỹ năng này **không phụ thuộc vào bất kỳ repo, công cụ Python, framework, hay nhà cung cấp LLM cụ
thể nào**. Chỉ cần tài liệu yêu cầu do User dán vào hội thoại và làm theo quy trình dưới đây, dùng
`read` để mở các file tham chiếu trong thư mục `references/` của chính skill này khi tới bước
tương ứng.

## Quy trình 6 bước

### Bước 1 — Thu thập & đọc toàn bộ tài liệu nguồn
Đọc HẾT mọi nguồn User cung cấp trong hội thoại (User Story/ticket chính + mọi API spec, BRD/SRS,
đặc tả UI, ví dụ cURL, ghi chú bổ sung đi kèm) — tuyệt đối không chỉ đọc tài liệu chính rồi lướt
qua phần còn lại. Nếu có nhiều nguồn, chủ động đối chiếu chéo: một quy tắc có khi chỉ lộ diện đầy
đủ khi kết hợp ≥2 nguồn (vd: User Story chỉ nói "validate số tiền hợp lệ", một file đính kèm khác
mới nêu rõ ngưỡng min/max cụ thể).

### Bước 2 — Phân tích yêu cầu & Đánh giá rủi ro (RBT)
Đọc `references/01-requirement-analysis-and-rbt.md` và làm đúng theo đó: chuẩn hóa tên tính năng,
xác định in-scope/out-of-scope, gán mã `AC-xx` / `BR-xx.y`, phân tầng dữ kiện thành Confirmed Facts
/ Assumptions / Ambiguities, dựng ma trận rủi ro RBT (`Likelihood 1-5 x Impact 1-5`).

### Bước 3 — Cổng Chặn Cứng Làm Rõ (bắt buộc, trước khi thiết kế kịch bản)
Đọc `references/02-clarification-gate.md`. Nếu tài liệu thiếu sample API (đủ cả request lẫn
response) hoặc thiếu message cho cả luồng thành công lẫn thất bại, DỪNG LẠI và đặt câu hỏi cho
User ngay tại đây — KHÔNG tự bịa field, JSON, mã lỗi hay câu message. Chỉ sang Bước 4 khi đã đủ dữ
kiện hoặc User đã trả lời/tường minh miễn câu hỏi đó.

### Bước 4 — Thiết kế Ma trận Kịch bản (9 kỹ thuật)
Đọc `references/03-test-design-techniques.md`, áp dụng đồng thời cả 9 kỹ thuật, nhưng CHỈ trên các
field/tham số/luồng thực sự có căn cứ trong tài liệu — không suy diễn field lạ (`idempotency_key`,
`device_id`...) nếu tài liệu không nhắc tới.

### Bước 5 — Sinh Test Case theo chuẩn 8 cột
Đọc phần "Định dạng 8 cột" trong `references/04-test-case-format-and-review.md`. Mỗi kịch bản ở
Bước 4 sinh ra đúng 1 (hoặc nhiều, nếu tài liệu liệt kê nhiều giá trị/mã lỗi cùng nhóm) test case,
tiêu đề văn phong tự nhiên bọc ngoặc kép, nhúng thẳng JSON body vào cột Các bước thực hiện.

### Bước 6 — Tự rà soát trước khi trình bày cho User (Self-Review / QA Gate)
Đọc phần "Tự rà soát" trong cùng file `references/04-test-case-format-and-review.md`. Tự chấm điểm
0–100 theo 4 tiêu chí (Traceability, Scope Drift & Field/Message Hallucination, Bao phủ rủi ro RBT,
Tính xác định). Nếu điểm <95 hoặc còn lỗi Critical/Major, tự sửa lại trước khi trả lời — không nộp
bản nháp còn lỗi cho User.

## Định dạng đầu ra

Mặc định trình bày kết quả dưới dạng **một bảng Markdown 8 cột duy nhất** ngay trong hội thoại —
không tách bảng/sheet theo tính năng, không tách bảng/sheet riêng cho câu hỏi
`PENDING CLARIFICATION` (thông tin đó nằm ngay trong ô Kết quả mong đợi của dòng test case liên
quan, xem `references/04-test-case-format-and-review.md`). Gom nhóm bằng banner ROW
`group_feature` (banner lớn) rồi `group_functional` (banner con) chèn trực tiếp trong cùng bảng đó
— không dùng nhiều bảng/sheet để gom nhóm. Kỹ năng này hoàn chỉnh và dùng được ngay ở dạng
Markdown — không cần Excel, `openpyxl`, hay bất kỳ template nào để hoàn thành nhiệm vụ.

Trường hợp riêng: nếu agent đang chạy ngay trong repo mã nguồn `qa-agentic-workflow` (nơi các file
prompt gốc của skill này được trích ra) và có sẵn Python + `openpyxl` + file template
`EF_TestCases.xlsx`, agent CÓ THỂ tùy chọn dùng thêm `src/utils/excel_exporter.py` của repo đó để
xuất ra một file `.xlsx` đẹp hơn thay cho bảng Markdown. Đây thuần túy là một lựa chọn hoàn thiện
thêm khi có sẵn công cụ đó trong tay — không phải yêu cầu bắt buộc, và skill này vẫn hoàn chỉnh
100% không cần tới nó. Lưu ý: công cụ Python đó theo mặc định xuất ra NHIỀU sheet (sheet test case
riêng + sheet tổng hợp + có thể có sheet "Cần làm rõ (Pending)" riêng) — nếu dùng, agent phải tự
cấu hình/chỉnh lại để gộp về đúng 1 sheet duy nhất theo yêu cầu của skill này; hành vi nhiều-sheet
mặc định của công cụ đó KHÔNG được chấp nhận là kết quả hợp lệ của skill.

## Khi User trả lời câu hỏi làm rõ

Gộp câu trả lời của User vào một khối "THÔNG TIN BỔ SUNG / LÀM RÕ TỪ USER" — khối này có **hiệu lực
cao nhất**, dùng để lấp khoảng trống hoặc ghi đè chi tiết chưa rõ trong tài liệu gốc. Sau đó quay
lại Bước 2 và phân tích lại toàn bộ với dữ kiện đầy đủ. User không cần trả lời đúng khuôn mẫu —
một câu tự nhiên như "tính năng này chưa có API nào cả" hoặc "Message lỗi: N/A" là đủ để miễn câu
hỏi đó (xem chi tiết cơ chế miễn trong `references/02-clarification-gate.md`).
