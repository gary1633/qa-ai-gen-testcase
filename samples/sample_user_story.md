# User Story: VWCBT-4102 - Chức năng Chuyển tiền nhanh Napas 24/7 và Kiểm tra Hạn mức Giao dịch

## 1. Thông tin chung
- **Ứng dụng**: Branch Portal / Mobile Banking
- **Phiên bản**: UAT 3.1.0
- **Jira Ticket**: https://galaxyfinx.atlassian.net/browse/VWCBT-4102
- **Người tạo yêu cầu**: PO Nguyễn Văn A

---

## 2. Mô tả nghiệp vụ (Business Overview)
Hệ thống cần cung cấp API và giao diện cho phép khách hàng cá nhân thực hiện chuyển tiền nhanh liên ngân hàng qua kênh Napas 24/7 (bằng Số tài khoản hoặc Số thẻ) với các quy tắc xác thực hạn mức giao dịch trong ngày và xác thực OTP/Sinh trắc học.

---

## 3. Danh sách Acceptance Criteria (Tiêu chí nghiệm thu)

### AC-01: Chuyển tiền Napas 24/7 qua Số tài khoản (Happy Path)
- **Điều kiện**:
  - Tài khoản nguồn đang hoạt động (Active), đủ số dư khả dụng (Số tiền chuyển + Phí giao dịch).
  - Ngân hàng thụ hưởng nằm trong danh sách hỗ trợ Napas 24/7.
  - Số tiền chuyển nằm trong hạn mức: Tối thiểu 10,000 VND, tối đa 500,000,000 VND / giao dịch.
- **Kết quả mong đợi**:
  - Giao dịch thành công, tiền được trừ ngay lập tức từ tài khoản nguồn và ghi có tài khoản đích.
  - Hệ thống trả về mã giao dịch `napas_trace_no`, HTTP Status `200 OK`.
  - Phí giao dịch: Miễn phí với giao dịch dưới 1,000,000 VND; 2,200 VND đối với giao dịch từ 1,000,000 VND trở lên.

### AC-02: Kiểm tra Hạn mức Giao dịch (Transaction Limits)
- **Hạn mức theo lần (Per-transaction limit)**:
  - Dưới 10,000 VND: Báo lỗi `ERR_MIN_AMOUNT` - "Số tiền chuyển tối thiểu là 10,000 VND".
  - Trên 500,000,000 VND: Báo lỗi `ERR_MAX_PER_TXN` - "Số tiền vượt quá hạn mức tối đa 500,000,000 VND / lần".
- **Hạn mức tích lũy trong ngày (Daily Cumulative Limit)**:
  - Hạn mức tối đa ngày: 1,500,000,000 VND / ngày.
  - Nếu tổng tiền chuyển trong ngày vượt quá 1.5 tỷ VND: Báo lỗi `ERR_DAILY_LIMIT_EXCEEDED` - "Quý khách đã vượt quá hạn mức chuyển tiền trong ngày".

### AC-03: Xác thực Sinh trắc học (Biometric Authentication - QĐ 2345/QĐ-NHNN)
- Giao dịch trên 10,000,000 VND / lần: Bắt buộc xác thực khuôn mặt (Face matching với dữ liệu CCCD gắn chip).
- Tổng giá trị giao dịch trong ngày tích lũy từ 20,000,000 VND trở lên: Bắt buộc xác thực khuôn mặt cho các giao dịch tiếp theo.
- Nếu xác thực sinh trắc học thất bại quá 3 lần: Khóa tính năng chuyển tiền trong 60 phút, trả về HTTP Status `403 Forbidden`.

### AC-04: Xử lý ngoại lệ và Timeout Napas (Exception & Edge Cases)
- Khi Napas Gateway trả về Timeout (HTTP 504 / Socket timeout):
  - Hệ thống chuyển trạng thái giao dịch sang `PENDING_RECONCILIATION`.
  - Không tự động trừ tiền hai lần (Đảm bảo Idempotency với `idempotency_key`).
  - Gửi thông báo cho khách hàng: "Giao dịch đang được xử lý đối soát, vui lòng không chuyển lại".
