# DOMAIN PACK: FINTECH & BANKING — LÕI CHUNG

> Pack gồm LÕI CHUNG (file này, áp dụng mọi tính năng ngân hàng) + các MODULE SẢN PHẨM (Payments, Overdraft, Lending, Cards, Deposits) được ghép kèm khi nội dung yêu cầu có nhắc tới sản phẩm đó.
> Quy tắc dùng pack:
> - Pack ở mức TỔNG QUÁT, không chứa giá trị riêng của bất kỳ ngân hàng nào. Mọi tham số nghiệp vụ (giờ cut-off, hạn mức, ngưỡng, số lần thử, thứ tự ưu tiên, phí, lãi suất, cơ sở tính lãi, tên trạng thái, mã lỗi, message) PHẢI lấy từ BRD/tài liệu yêu cầu hoặc câu trả lời làm rõ của User.
> - Pack là CHECKLIST tìm khoảng trống: CHỈ áp dụng mục mà tài liệu yêu cầu thực sự liên quan. Không gán ép kỹ thuật/quy định của module này sang tính năng khác.
> - Tài liệu có nhắc khái niệm nhưng KHÔNG nêu giá trị -> đưa vào Ambiguities + câu hỏi làm rõ; test case liên quan chỉ assert phần đã có căn cứ và đánh dấu `PENDING CLARIFICATION`. TUYỆT ĐỐI không tự điền giá trị "thông lệ".
> - Mục "Tuân thủ & pháp chế" chỉ là danh mục gợi ý để hỏi BA/Compliance; ngưỡng/mức áp dụng lấy từ BRD (mỗi ngân hàng có chính sách nội bộ khác nhau và văn bản pháp luật có thể thay đổi).

## Bất biến nghiệp vụ
- `Số dư Khả dụng = Số dư Thực - Số tiền Phong tỏa + Hạn mức Thấu chi còn lại` (thành phần OD chỉ tồn tại khi tài khoản có hạn mức thấu chi; công thức chi tiết theo BRD nếu khác).
- `Bypass Phong tỏa (Blockade Override)` chỉ tạm thời bỏ qua bước CHẶN giao dịch do phong tỏa gây ra — KHÔNG làm thay đổi công thức Số dư Khả dụng ở trên: giao dịch vượt Số dư Thực (sau khi trừ phần đang phong tỏa) khi đang bypass vẫn phải tuân theo đúng quy tắc sử dụng Hạn mức Thấu chi (OD) như giao dịch bình thường, trừ khi tài liệu nêu rõ ngoại lệ khác.
- `Tổng phát sinh Nợ GL = Tổng phát sinh Có GL` (Cân bằng hạch toán kép - Double-Entry Debit/Credit). Giao dịch thất bại sau khi đã hạch toán phải được đảo theo đúng cơ chế BRD nêu, không làm mất dấu bút toán gốc.
- `Zero Double-Debit`: Không bao giờ trừ tiền 2 lần cho cùng một giao dịch. Cơ chế chống trùng dùng đúng cơ chế tài liệu nêu (`idempotency_key`, mã tham chiếu giao dịch, mã yêu cầu của kênh); KHÔNG tự thêm trường `idempotency_key` khi tài liệu không có.
- `Tổng biến động số dư = Tổng giao dịch đã hạch toán` trong cùng kỳ (sao kê/lịch sử giao dịch khớp sổ cái).
- `Auditability`: Mọi thay đổi cấu hình tham số, hạn mức hoặc trạng thái tài khoản đều có Audit Log (người thực hiện, thời điểm, giá trị cũ/mới, kênh) — trường audit cụ thể theo BRD.
- Maker-Checker (khi BRD nêu): thao tác cần phê duyệt không được để chính người tạo tự duyệt; chưa duyệt thì chưa có hiệu lực.

## Biên & giá trị đặc thù
> Mọi ngưỡng dưới đây là DẠNG BIÊN cần dựng; giá trị cụ thể lấy từ BRD.
- Cut-off (EOD, giờ chốt sổ, giờ ngừng nhận lệnh): `cut-off - 1 giây`, `đúng cut-off`, trong cửa sổ xử lý, đúng thời điểm kết thúc (theo giờ hoặc sự kiện báo hoàn tất mà BRD nêu), sau khi kết thúc. Múi giờ áp dụng theo BRD.
- Ngày làm việc: giao dịch/sự kiện rơi vào cuối tuần, ngày lễ, ngày làm bù — quy tắc chuyển ngày (lùi/tiến) theo BRD.
- Ngày hiệu lực vs ngày giao dịch (value date / posting date) khi giao dịch phát sinh sau cut-off.
- Làm tròn: quy tắc (round-half-even / round-half-up / truncate) và đơn vị làm tròn theo BRD; kiểm tra tại giá trị .5 và tiền tệ không có phần thập phân.
- Cơ sở ngày tính lãi (Actual/365, Actual/366, 30/360...) theo BRD; luôn có ca qua năm nhuận khi kỳ tính lãi đi qua 29/02.
- Tách bạch thuế/phí: tiền gốc, phí, thuế (mức theo BRD), tổng trừ trên tài khoản.
- Hạn mức/số tiền: Min-1, Min, Max-1, Max, Max+1; 0, âm, vượt độ dài, sai định dạng.

## Máy trạng thái
- Tài khoản thanh toán (CASA): dựng vòng đời theo đúng tập trạng thái BRD nêu (ví dụ minh họa dạng: hoạt động -> ngủ đông -> đóng băng -> đóng); kiểm tra cả transition hợp lệ lẫn bị cấm.
- Forbidden điển hình cần hỏi/kiểm tra: giao dịch ghi nợ trên tài khoản ở trạng thái bị chặn; kích hoạt lại tài khoản đã đóng.
- Phong tỏa (Blockade): tạo -> đang hiệu lực -> giải tỏa một phần -> giải tỏa toàn phần / hết hạn; số tiền phong tỏa không âm, không giải tỏa vượt số đã phong tỏa.
- Scheduled Events / batch job (khi BRD nêu): lịch tạo khi phát sinh đối tượng -> chạy theo lịch BRD -> hủy khi đối tượng kết thúc; chạy lại/deploy lại không tạo lịch trùng; job lỗi giữa chừng chạy lại không xử lý trùng.

## Tuân thủ & pháp chế
> Danh mục gợi ý — chỉ áp dụng khi BRD nêu; ngưỡng/mức cụ thể lấy từ BRD hoặc xác nhận của Compliance.
- Bảo vệ dữ liệu cá nhân (che/ẩn thông tin định danh khách hàng trên UI, log, file xuất).
- Phòng chống rửa tiền (báo cáo giao dịch giá trị lớn/đáng ngờ).
- Quy định riêng của từng sản phẩm nằm trong module tương ứng.

## Kỹ thuật bắt buộc nhấn mạnh
- Kiểm tra trạng thái nghiệp vụ sau thao tác: số dư thực, số dư khả dụng, số tiền phong tỏa, bút toán Nợ/Có, lịch sử giao dịch, audit log — không chỉ HTTP status.
- Concurrency / Race Condition khi tính năng làm biến động số dư: 2 giao dịch ghi nợ cùng lúc khi số dư chỉ đủ 1.
- Boundary Value Analysis trên hạn mức, số tiền và mốc cut-off do BRD quy định.
- Financial Calculation & Rounding (làm tròn, cơ sở ngày tính lãi, tách thuế/phí) khi BRD có công thức — expected result ghi số cụ thể tính từ công thức BRD.
- Kiểm thử tương tác Phong tỏa (Blockade) x Số dư Thực (CASA) x Hạn mức Thấu chi (OD) x Cờ Bypass (chỉ khi tài liệu có đề cập đồng thời các thành phần này): PHẢI kiểm tra tổ hợp (1) giao dịch vượt Số dư Thực nhưng còn Hạn mức OD trong lúc bypass đang bật — có được tự động dùng tiếp OD hay không; (2) giao dịch vượt cả Số dư Thực lẫn Hạn mức OD trong lúc bypass đang bật — có bị từ chối đúng quy tắc hay không; (3) Số tiền Phong tỏa được tính trừ vào phần OD hay chỉ trừ vào Số dư Thực gốc.
