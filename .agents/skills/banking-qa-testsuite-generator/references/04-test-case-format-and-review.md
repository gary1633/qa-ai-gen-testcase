# Định dạng 8 cột & Tự rà soát (Self-Review / QA Gate)

## Phần A — Định dạng 8 cột

Áp dụng ở Bước 5 của `SKILL.md`. Tiêu chuẩn nghiệm thu: mọi test case phải đạt quality bar tương
đương **>= 95/100** theo tiêu chí ở Phần B — Expected Result định lượng rõ ràng, cấm dùng từ ngữ mơ
hồ như "kiểm tra ok", "verify it works", "dữ liệu hợp lệ".

### Nguyên tắc bám sát tài liệu (Strict Grounding) — nhắc lại, áp dụng khi viết từng cột

1. Mọi test case bắt buộc bám sát trực tiếp AC/Business Rule đã bóc tách ở Bước 2 — không tự suy
   diễn thêm logic/tham số/kịch bản không có căn cứ.
2. Chỉ dùng field thực sự được nêu trong tài liệu — cấm tự thêm field lạ vào JSON body/`test_data`.
3. **Cấm tuyệt đối bịa câu message** (áp dụng lại quy tắc Cổng Chặn Cứng khi viết `expected_result`
   thực tế, tức cột Kết quả mong đợi): nếu tài liệu/User Clarifications đã nêu rõ message, dùng
   đúng 100% câu chữ đó; nếu chưa nêu rõ, không tự viết message theo ý mình và không dùng
   placeholder — chỉ assert trên neo đã xác thực (HTTP status, `error_code`, schema structure) và
   thêm tiền tố `[PENDING CLARIFICATION]` vào đầu ô **Kết quả mong đợi** của đúng test case bị ảnh
   hưởng (xem `02-clarification-gate.md`).
4. Các giá trị verify trong `expected_result` (mã lỗi, mốc giờ, HTTP status, số dư) phải khớp 100%
   với quy tắc đã phân tích. Payload JSON trong `steps`/`test_data` phải phản ánh đúng cấu trúc
   field thực tế — không dùng placeholder chung chung ("nhập email hợp lệ", "some string").
5. Test data phải cụ thể, duy nhất, có thể truy vết, theo định dạng gợi ý:
   `auto_<module>_<tc_id>_<timestamp>` (vd `auto_napas_tc01_1712049200`,
   `user_casa_001@banking.vn`).
6. **Bao phủ cả hệ quả nghiệp vụ, không chỉ response API**: khi hành động làm thay đổi trạng thái
   nghiệp vụ thực (số dư, sổ cái, tồn kho, trạng thái hợp đồng...), `steps` phải có thêm bước kiểm
   tra trực tiếp trạng thái/dữ liệu đó, và `expected_result` phải nêu rõ giá trị nghiệp vụ cụ thể
   (vd: "Số dư khả dụng giảm đúng 500,000 VND"). Khi liên quan nhiều thành phần ràng buộc lẫn nhau,
   nêu rõ giá trị sau cùng của TỪNG thành phần, không chỉ 1 thành phần.
7. **Liệt kê đầy đủ mọi giá trị tài liệu đã nêu (Exhaustive Enumeration)**: khi tài liệu liệt kê một
   danh sách giá trị/loại/nguyên nhân riêng biệt cùng nhóm (vd: nhiều posting type, nhiều mã lỗi,
   nhiều kênh giao dịch), phải sinh ít nhất 1 test case cho TỪNG giá trị — không chọn 1–2 giá trị
   đại diện rồi bỏ qua phần còn lại. Nếu tài liệu nói rõ "tách biệt theo từng nguyên nhân, không gộp
   chung", mỗi mã lỗi phải có test case Negative riêng.
8. Khi có nhiều nguồn tài liệu, quét TẤT CẢ để lấy đúng field/API sample/message/số liệu thật — nếu
   nguồn chính thiếu nhưng một nguồn tham khảo khác có, dùng đúng chi tiết ở nguồn đó thay vì hỏi
   lại một cách không cần thiết.

### Quy tắc đặt tiêu đề (Tên testcase) — nhắc lại từ `03-test-design-techniques.md`
Văn phong nghiệp vụ tự nhiên, field/value bọc `""`, không chứa mã ticket. 3 mẫu cấu trúc chuẩn:
- Thành công: `Kiểm tra [hành động] [đối tượng] thành công khi truyền trường "[field]" là
  "[value]"`
- Bắt lỗi: `Kiểm tra [hành động] [đối tượng] không thành công khi truyền [thiếu trường "[field]" /
  giá trị "[value]"]`
- Hiển thị/dữ liệu/query: `Kiểm tra [tính năng] hiển thị đúng trường/giá trị "[field_or_value]" khi
  input "[param]" là "[input_value]"`
- **Priority (tùy chọn)**: cột `priority` đã bị bỏ khỏi chuẩn 8 cột; nếu muốn vẫn hiển thị mức độ
  ưu tiên, chèn một tag ngắn ở đầu Tên testcase, vd `[Critical] Kiểm tra ...`. Chỉ dùng 1 trong 4
  mức `[Critical]`/`[High]`/`[Medium]`/`[Low]`. Nếu tag làm tiêu đề rối mắt hoặc priority không
  quan trọng với use case hiện tại, được phép bỏ hẳn tag này — tùy chọn, không bắt buộc.

### Nhúng Body JSON trực tiếp vào Steps
Tại bước gửi request, nhúng thẳng JSON body vào bước thực hiện, thụt dòng 2 space:

```
1. Gửi request POST /v1/account/withdraw với body:
{
  "batch_details": {
    "force_posting": "true",
    "processing_channel": "PORTAL",
    "processing_branch_code": "001"
  }
}
2. Kiểm tra HTTP status code 200 OK và mã phản hồi.
3. Kiểm tra thông tin hạch toán và biến động số dư.
```

### Checklist theo loại field (dùng khi dựng `test_data`/`steps`)

- **String/Text**: positive hợp lệ; boundary (chuỗi rỗng, chỉ khoảng trắng, chạm/vượt maxLength);
  ký tự đặc biệt (`!@#$%^&*()`), khoảng trắng đầu/cuối cần trim, Unicode tiếng Việt có dấu.
- **Email/Phone/Account Number**: email hợp lệ vs thiếu domain/username vs đã tồn tại (409); phone
  hợp lệ 10 số vs E.164 vs quá ngắn vs lẫn chữ; account number đúng độ dài chuẩn vs đã tồn tại vs
  đang bị khóa (nếu tài liệu có trạng thái này).
- **Số tiền/Currency**: dãy giá trị quanh Min/Max (`Min-1/Min/Min+1`, `Max-1/Max/Max+1`), số âm, số
  0, số thập phân vượt precision cho phép.
- **Ngày tháng/DateTime**: mốc biên thời gian cụ thể của tài liệu; năm nhuận hợp lệ/không hợp lệ;
  ngày không tồn tại.
- **Enum/Dropdown/Boolean**: toàn bộ giá trị whitelist; giá trị invalid; kiểu sai (`"True"` string
  thay vì boolean `true`); `null`.
- **Object/Mảng lồng nhau (bands)**: mảng rỗng, 1 phần tử, nhiều dải liên tiếp.

### Banner phân cấp (không phải cột dữ liệu)
`group_feature` và `group_functional` (xem quy tắc đặt tên ở `03-test-design-techniques.md`) là
các dòng banner chèn TRƯỚC các test case cùng nhóm, sao chép nguyên văn từ kịch bản tương ứng ở
Bước 4 — không phải 1 trong 8 cột dữ liệu bên dưới. Toàn bộ test suite (kể cả các banner này và
mọi test case đang `PENDING CLARIFICATION`) nằm trong **1 sheet/1 bảng duy nhất** — tuyệt đối
không tách sheet theo tính năng, và không tách riêng sheet "Cần làm rõ (Pending)"; câu hỏi mở nào
cũng phải nhìn thấy được ngay trên chính dòng test case bị ảnh hưởng (xem mục "Gấp gọn Trace ID &
PENDING CLARIFICATION" dưới đây), rồi tùy chọn tổng hợp lại một lần nữa ở cuối câu trả lời.

### Gấp gọn Trace ID & PENDING CLARIFICATION vào 8 cột
Bản 14-cột cũ tách riêng cột `note` cho traceability và cờ chờ làm rõ; bản 8-cột không còn cột đó,
nên hai thông tin này được gấp vào các cột sẵn có thay vì bị mất:

- **Trace AC/RSK** → tiền tố ngắn ở đầu **Điều kiện tiên quyết**: `(Trace: AC-01 | RSK-03) <phần
  còn lại của điều kiện tiên quyết...>`. Nếu kịch bản không triệt tiêu rủi ro RBT nào, bỏ phần
  `RSK-yy`, chỉ giữ `(Trace: AC-01)`.
- **PENDING CLARIFICATION** → tiền tố `[PENDING CLARIFICATION]` ở đầu **Kết quả mong đợi**, ngay
  trước phần assertion đã có căn cứ (vd: `[PENDING CLARIFICATION] HTTP 400, error_code: "CV_043"
  (chưa xác nhận nội dung message hiển thị cho User)`), để bất kỳ ai đọc bảng cũng nhận ra ngay
  dòng nào chưa hoàn chỉnh mà không cần một cột riêng.
- **Priority** → tùy chọn ở đầu **Tên testcase**, xem mục "Quy tắc đặt tiêu đề" ở trên.

### 8 cột chuẩn

| # | Cột | Nội dung |
|---|-----|----------|
| 1 | Testcase ID | ID tuần tự, vd `TC 01`, `TC 02`. |
| 2 | Tên testcase | Theo mẫu tiêu đề ở trên; có thể có tiền tố `[Priority]` tùy chọn. |
| 3 | Điều kiện tiên quyết | Tiền tố `(Trace: AC-xx \| RSK-yy)` rồi tới điều kiện tiên quyết chi tiết (trạng thái deploy, cấu hình ban đầu, mock cần có). |
| 4 | Các bước thực hiện | Các bước đánh số tuần tự, nhúng trực tiếp body JSON vào bước gửi request. |
| 5 | Kết quả mong đợi | Kết quả định lượng: HTTP status, JSON response thụt lề đẹp, mã lỗi chi tiết, hoặc exception; tiền tố `[PENDING CLARIFICATION]` nếu còn câu hỏi mở. |
| 6 | Kết quả thực tế | Để trống (`""`) — điền khi thực thi thật. |
| 7 | Dữ liệu test | Payload JSON đầy đủ, định dạng đẹp, thụt dòng. |
| 8 | Người tạo | Vd `"QA Automation Specialist"`. |

`test_date`, `test_status`, `executed_date`, `plan_execution` của bản 14-cột cũ bị bỏ hẳn, không
thay thế — đây là dữ liệu theo dõi thực thi (execution tracking), do người chạy test suite điền
trong quá trình test thật, không thuộc phạm vi thiết kế test case của skill này.

---

## Phần B — Tự rà soát trước khi trình bày (Self-Review / QA Gate)

Áp dụng ở Bước 6 của `SKILL.md`. Vai trò giả định khi tự rà soát: Principal QA Quality Auditor —
đóng vai người phản biện chính bản thảo vừa viết ở Bước 5, không phải chỉ đọc lướt qua.

### 1. Truy vết 2 chiều & độ bao phủ (Bidirectional Traceability)
- **Xuôi**: duyệt 100% AC/Business Rule từ Bước 2 — mỗi AC bắt buộc có cả test case
  Positive/Happy-path VÀ Negative/Boundary. AC nào chưa có test case bao phủ → đánh dấu `MISSING`
  hoặc `PARTIAL`.
- **Ngược** (chống test case "ma"): mọi test case phải map với một mã `AC-xx`/`RSK-yy` có thật
  (ghi ở tiền tố `Trace` trong cột Điều kiện tiên quyết) — không có test case thừa, lạc đề (Zero
  Phantom Test Cases).

### 2. Chống trôi dạt phạm vi & field tự chế (Scope Drift & Hallucination Check)
- **Scope Drift**: test case có bám sát 100% đúng tính năng trong tài liệu gốc không? Nếu phát
  hiện test case đi kiểm thử một tính năng hoàn toàn không liên quan → gắn cờ `Scope Drift /
  Unrelated Feature` và loại khỏi bản trả lời.
- **Field & Message Hallucination**: có field/header nào bị tự ý thêm vào mà tài liệu không yêu
  cầu không? Có câu message/mã lỗi nào bị tự bịa, không có căn cứ trong tài liệu/User
  Clarifications không? Nếu có → gắn cờ `Fabricated Message / Ungrounded Value`, xóa giá trị tự
  bịa, thay bằng assertion đã có căn cứ + thêm tiền tố `[PENDING CLARIFICATION]` vào đầu ô Kết quả
  mong đợi.
- **Duplicate/Filler Test Case**: test case không mang thêm giá trị kiểm thử nào so với case khác
  (lặp ý dưới tiêu đề/test data khác nhau, chỉ để "đủ số lượng") → gộp hoặc loại bỏ.
- **Scenario-Level Defect**: kỹ thuật áp dụng có khớp với thứ test case thực tế đang kiểm thử
  không, và tên kỹ thuật hàn lâm có bị lộ vào `group_functional`/`title` không (phải sửa nếu có)?

### 3. Bao phủ rủi ro RBT & đa kỹ thuật
- 100% rủi ro `Critical` và `High` trong ma trận RBT (Bước 2) phải có test case trực diện để triệt
  tiêu rủi ro.
- Rà lại đã áp dụng đủ các kỹ thuật thực tế phù hợp chưa: BVA, EP, Pairwise, Concurrency,
  Idempotency (nếu API hỗ trợ), Fault Injection.
- Không yêu cầu test case tấn công mạng/SQL Injection trừ khi tài liệu có yêu cầu bảo mật riêng.

### 4. Tính xác định & kiểm chứng được (Determinism)
- Mọi `expected_result` phải định lượng rõ: HTTP status, JSON body, mã lỗi chính xác, biến động số
  dư/tổng tiền — không còn câu mơ hồ dạng "verify it works", "chờ một chút", "thông báo tương ứng",
  "kiểm tra ok", "dữ liệu hợp lệ", "hoạt động bình thường".

### Chấm điểm & ngưỡng nghiệm thu

Chấm theo thang 100 điểm dựa trên 4 tiêu chí trên (trừ điểm nặng cho AC `MISSING`, nặng hơn nữa cho
`Fabricated Message/Ungrounded Value` và `Scope Drift`).

- **PASSED** khi và chỉ khi: điểm >= 95/100 VÀ không còn bất kỳ lỗi Critical/Major nào.
- **Nếu < 95**: tự liệt kê từng lỗi cụ thể (test case nào sai, thiếu kịch bản gì, thiếu kỹ thuật
  gì), tự sửa lại bản thảo, rồi chấm lại — lặp lại cho tới khi đạt hoặc đã hết khả năng cải thiện vì
  thiếu dữ kiện (trường hợp này quay lại Cổng Chặn Cứng thay vì tự đoán). Chỉ trình bày cho User
  bản đã đạt ngưỡng, kèm một tóm tắt Traceability Matrix ngắn gọn (mã AC, trạng thái
  COVERED/PARTIAL/MISSING, số test case bao phủ).
