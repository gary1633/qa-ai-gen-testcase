# DOMAIN PACK: FINTECH & BANKING

## Bất biến nghiệp vụ
- `Số dư Khả dụng = Số dư Thực - Số tiền Phong tỏa + Hạn mức Thấu chi`.
- `Tổng phát sinh Nợ GL = Tổng phát sinh Có GL` (Cân bằng hạch toán kép - Double-Entry Debit/Credit).
- `Zero Double-Debit`: Không bao giờ trừ tiền 2 lần cho cùng một giao dịch chuyển tiền/thanh toán (chỉ áp dụng khi tài liệu/API có cơ chế `idempotency_key`).
- `Auditability`: Mọi thay đổi cấu hình tham số hoặc trạng thái tài khoản đều phải có bản ghi Audit Log (Ai sửa, lúc nào, giá trị cũ/mới).

## Biên & giá trị đặc thù
- Redzone EOD (End of Day): Mốc chuẩn **18:00 (18h) giờ Việt Nam (VNT / GMT+7)**.
  - `17:59:59 VNT` (Trước EOD) -> Giao dịch thành công bình thường.
  - `18:00:00 VNT` (Bắt đầu EOD / Redzone) -> Chặn giao dịch, trả lỗi từ chối trong giờ EOD.
  - `18:00:01 VNT` đến trước `tdEodEndTime` (Trong giờ EOD) -> Bị chặn giao dịch.
  - Sau khi nhận Kafka event `EOD-DONE` hoặc vượt quá `tdEodEndTime` -> Hệ thống mở lại, giao dịch thành công.
- Quy tắc làm tròn: Banker's Rounding (Round-half-even) vs Round-half-up.
- Số ngày tính lãi: 365 ngày vs 366 ngày (Năm nhuận - Leap Year boundary).
- Tách bạch Thuế VAT: tiền gốc, phí NET, thuế VAT (8%, 10%), tổng trừ tiền trên tài khoản.
- Hạn mức giao dịch: Min-1, Min, Max-1, Max, Max+1.
- Sản phẩm Vay/Thấu chi (Loan/Overdraft) thường có NHIỀU Job vận hành chạy theo giờ trong ngày, KHÔNG CHỈ riêng mốc EOD 18h. *Chỉ áp dụng bảng dưới đây khi tài liệu yêu cầu có mô tả rõ các Job này; không tự suy diễn nếu tài liệu chỉ nhắc EOD chung chung.*
  - Job 12h (giữa trưa): CHỈ thu các loại dư nợ LÃI (lãi phạt, lãi trả chậm, lãi đến hạn) và tất toán sớm (Hold for overdraft). **Tuyệt đối KHÔNG thu nợ GỐC** ở job này dù khoản vay ở trạng thái nào.
  - Job 17h: Thu CẢ nợ gốc và các loại dư nợ lãi; thứ tự ưu tiên phụ thuộc Trạng thái Khoản vay (Trong hạn / Quá hạn).
  - Job 18h (trùng mốc EOD): Giải ngân tiền từ tài khoản thanh toán (CASA), tính lãi hàng ngày (Daily) và thực hiện tất toán sớm.
  - Thứ tự ưu tiên thu nợ (Debt Collection Priority) theo Khung giờ Job x Trạng thái Khoản vay:
    * Job 12h, mọi trạng thái: `Lãi phạt > Lãi trả chậm > Lãi đến hạn` (không có Gốc).
    * Job 17h, khoản vay Trong hạn: `Lãi phạt > Lãi trả chậm > Lãi đến hạn > Gốc đến hạn/Gốc trong hạn`.
    * Job 17h, khoản vay Quá hạn: `Gốc quá hạn > Lãi phạt > Lãi trả chậm > Lãi đến hạn` (Gốc quá hạn lên đầu, đảo thứ tự so với khoản vay Trong hạn).
  - Bất biến: Không Job nào được thu Gốc trước khi thu hết Lãi phạt/Lãi trả chậm cùng khung giờ, TRỪ khoản vay Quá hạn tại Job 17h (Gốc quá hạn ưu tiên cao nhất).

## Máy trạng thái
- Tài khoản CASA: `ACTIVE -> DORMANT -> FROZEN -> CLOSED`.
- Forbidden: giao dịch trên tài khoản đang `FROZEN`/`BLOCKED`; kích hoạt lại tài khoản `CLOSED`.
- Vòng đời Scheduled Events: Hook tạo lịch chạy khi mở tài khoản -> Sự kiện định kỳ kích hoạt vào ngày 01 hàng tháng (Cron) -> Hook tất toán tài khoản hủy lịch chạy (Activation Hooks khi mở tài khoản CASA).
- Gateway timeout: Napas 504 -> chuyển trạng thái `PENDING_RECONCILIATION` an toàn, không làm thất thoát tiền.

## Tuân thủ & pháp chế
- Quyết định 2345/QĐ-NHNN về Sinh trắc học — *chỉ áp dụng khi tài liệu yêu cầu có nêu rõ luồng xác thực sinh trắc học hoặc thanh toán trên App*. Không áp dụng cho API backend thuần túy.
- PCI-DSS — *chỉ áp dụng khi tài liệu có nêu việc lưu trữ dữ liệu thẻ*.

## Kỹ thuật bắt buộc nhấn mạnh
- Concurrency / Race Condition trên số dư (2 giao dịch rút cùng lúc khi số dư chỉ đủ 1 giao dịch).
- Idempotency Key (chỉ khi API có định nghĩa trường/header này).
- Boundary Value Analysis trên hạn mức và mốc thời gian EOD.
- Financial Calculation & Rounding (Banker's Rounding, VAT split, 365/366 ngày).
- Decision Table cho Thứ tự Ưu tiên Thu nợ (khi sản phẩm là Vay/Thấu chi có nhiều Job giờ trong ngày): Dimensions = Khung giờ Job x Trạng thái Khoản vay -> Thứ tự thu đúng theo bảng "Biên & giá trị đặc thù"; test riêng case Job 12h không được lẫn Gốc vào danh sách thu.
