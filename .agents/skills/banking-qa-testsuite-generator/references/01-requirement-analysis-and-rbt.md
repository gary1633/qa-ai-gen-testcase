# Phân tích Yêu cầu & Đánh giá Rủi ro (RBT)

Áp dụng ở Bước 2 của `SKILL.md`. Vai trò giả định: Principal QA Business Analyst am hiểu nghiệp vụ
ngân hàng/tài chính (CASA, tiết kiệm, chuyển tiền liên ngân hàng, thẻ, vay/thấu chi, biểu phí...).

## Nguyên tắc bất khả xâm phạm: Zero Scope Drift

1. Chỉ phân tích chính xác tính năng được mô tả trong tài liệu được gửi vào. Tuyệt đối cấm suy
   diễn, tự tiện mở rộng sang các tính năng/module không liên quan (vd: yêu cầu là "chặn rút tiền
   trong giờ EOD" thì không được tự vẽ thêm kịch bản "chuyển tiền Napas", "sinh trắc học",
   "tính lãi tiết kiệm"... nếu tài liệu không đề cập).
2. Xác định rõ **In-Scope** và **Out-of-Scope / Non-Goals** — liệt kê rõ các luồng KHÔNG thuộc
   phạm vi xử lý hiện tại để các bước sau không sinh test case thừa.

## 8 kỹ năng phân tích bắt buộc

### 1. Chuẩn hóa tên tính năng (Semantic Feature Distillation)
Đọc kỹ mô tả, endpoint, payload, user story để hiểu đúng bản chất nghiệp vụ. `feature_name` phải
là tên tiếng Việt chuẩn nghiệp vụ (vd: "Chặn rút tiền và tất toán trong thời gian EOD") — tuyệt đối
không sao chép nguyên văn tiêu đề kỹ thuật thô hay mã ticket (`VWCBT-3230`) vào tên tính năng; mã
ticket chỉ lưu riêng như một link tham chiếu.

### 2. Bám sát tài liệu gốc — chống tự tiện thêm field (Strict Field Grounding)
Bóc tách rạch ròi 3 tầng thông tin cho mọi chi tiết nghiệp vụ:

- **Confirmed Facts & Explicit Fields**: CHỈ ghi nhận field, tham số, header, endpoint thực sự
  được nêu rõ trong tài liệu/schema. Tuyệt đối cấm bịa hoặc nhét thêm field không liên quan (ví dụ
  điển hình hay bị tự chế thêm: `idempotency_key`, `device_id`, `client_ip`, `vat_mode`,
  `tiering_method`) nếu tài liệu gốc không hề có.
- **Assumptions** (`[GIẢ ĐỊNH]`): khi thiếu một chi tiết nhỏ mang tính chuẩn mực ngân hàng, đánh
  dấu rõ kèm lý do đưa ra giả định.
- **Ambiguities & Gaps**: chỉ rõ điểm chưa rõ ràng, thiếu mã lỗi, thiếu điều kiện dừng, hoặc mâu
  thuẫn giữa các tiêu chí — đây là nguồn nuôi câu hỏi cho Cổng Chặn Cứng
  (`references/02-clarification-gate.md`).

### 3. Bóc tách điều kiện biên & ngoại lệ 360 độ
Danh mục biên bắt buộc rà soát cho mọi tính năng phù hợp:

- **Số tiền/hạn mức**: `Min-1`, `Min`, `Max`, `Max+1`, số 0, số âm, số thập phân vượt precision.
- **Dải bậc thang (bands/tiering)**: mảng rỗng `[]`, `min > max`, chồng lấn (overlap), hở dải
  (gap), dải cuối cùng bắt buộc `max = null`.
- **Chuỗi**: chuỗi rỗng `""`, chỉ khoảng trắng, chạm `maxLength`, vượt `maxLength + 1`.
- **Thời gian**: năm nhuận (29/2), tháng 30 vs 31 ngày, ngày/giờ không tồn tại (`31/02`, `31/04`).
- **Trạng thái**: chuyển trạng thái hợp lệ/bất hợp pháp giữa các state trong vòng đời đối tượng.

Anchor tham khảo cho domain ngân hàng (dùng làm ví dụ cụ thể, luôn ưu tiên số liệu/mốc giờ thật của
tài liệu nếu có nêu, chỉ dùng anchor này khi tài liệu không tự nêu):
- Redzone EOD (End of Day) mặc định **18:00 giờ Việt Nam (VNT/GMT+7)**: `17:59:59` giao dịch bình
  thường, `18:00:00` bắt đầu chặn, sau sự kiện `EOD-DONE` mở lại.
- Số dư khả dụng = Số dư thực − Số tiền phong tỏa + Hạn mức thấu chi (OD).
- Làm tròn: Banker's Rounding (round-half-even) vs round-half-up; số ngày tính lãi 365 vs 366.
- Tách bạch thuế VAT (8%/10%) khỏi phí gốc.
- Với sản phẩm vay/thấu chi có nhiều job thu nợ trong ngày (vd job 12h/17h/18h): thứ tự ưu tiên thu
  nợ (lãi phạt > lãi trả chậm > lãi đến hạn > gốc) thường khác nhau theo khung giờ và theo khoản
  vay đang Trong hạn hay Quá hạn — CHỈ áp dụng nếu tài liệu thật sự mô tả các job này.

### 4. Phân tích đa góc nhìn (Multi-Stakeholder Perspective)
- **Khách hàng (End-User)**: luồng giao dịch, message dễ hiểu, tốc độ phản hồi, giao diện.
- **Dữ liệu & Sổ sách**: toàn vẹn dữ liệu, cân bằng hạch toán, đối soát định kỳ.
- **Tích hợp & Hạ tầng**: timeout, chống trùng lặp (chỉ khi có `idempotency_key`), concurrency,
  rollback khi lỗi.
- **Pháp chế & Tuân thủ**: chỉ nhận diện khi tài liệu nêu rõ phạm vi áp dụng (vd: xác thực sinh
  trắc học theo quy định ngân hàng chỉ áp dụng cho luồng App/UI có nêu rõ, không tự gán ép cho API
  backend thuần túy).

### 5. Xác định bất biến nghiệp vụ (Business Invariants)
Tìm nguyên tắc bất khả xâm phạm hệ thống không bao giờ được vi phạm. Mỗi bất biến phải có căn cứ
từ tài liệu gốc hoặc kiến thức chuẩn ngành; nếu không có căn cứ rõ ràng, đánh dấu `[GIẢ ĐỊNH]` kèm
lý do. Ví dụ bất biến điển hình ngành ngân hàng: cân bằng hạch toán kép (`Tổng Nợ GL = Tổng Có
GL`), không trừ tiền 2 lần cho cùng một giao dịch (Zero Double-Debit, khi có `idempotency_key`),
mọi thay đổi cấu hình/trạng thái tài khoản đều có audit log.

### 6. Đánh giá khả năng kiểm thử & tiền điều kiện
Yêu cầu có kiểm thử độc lập được không? Cần mock hệ thống nào (mock đối tác thanh toán, mock core
banking)? Cần dữ liệu khởi tạo cụ thể ra sao (vd: tài khoản CASA nguồn số dư 10 triệu)?

### 7. Ma trận rủi ro sản phẩm & truy vết 100% (RBT & Traceability)
- Đánh giá theo chuẩn ISTQB: `Likelihood (1-5) x Impact (1-5) = Risk Score (1-25)`.
- Gán mã định danh cho từng Acceptance Criterion (`AC-01`, `AC-02`...) và từng Business Rule
  (`BR-01.1`, `BR-01.2`...).
- Mọi kịch bản kiểm thử ở các bước sau bắt buộc gắn Trace ID khớp 100% với các mã này.

### 8. Tổng hợp & đối chiếu đa nguồn tài liệu
Khi có nhiều nguồn (US chính + BRD/SRS, đặc tả UI/UX, API Spec/Swagger, cURL...): đọc và trích xuất
từ TỪNG nguồn, không chỉ dựa vào tài liệu chính. Với mỗi AC/BR đang bóc tách, chủ động map xem các
nguồn khác có làm rõ, ràng buộc thêm, hay bổ sung số liệu cụ thể không. Nếu một quy tắc chỉ xác
định được khi kết hợp ≥2 nguồn, ghi rõ ràng buộc kết hợp đó (vd: "[Kết hợp nguồn 1 + nguồn 3]") để
các bước sau không bỏ sót.

## Ưu tiên tuyệt đối cho thông tin bổ sung từ User

Khi có khối "THÔNG TIN BỔ SUNG / LÀM RÕ TỪ USER": khối này có hiệu lực cao nhất, dùng để lấp
khoảng trống, bổ sung tham số, hoặc ghi đè chi tiết chưa rõ trong tài liệu gốc. Nếu đã làm rõ được
mọi thắc mắc trước đó, hoàn thành bài phân tích theo đúng ý User đã chốt và không hỏi lại điểm đó.
