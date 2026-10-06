# MODULE: PAYMENTS & FUND TRANSFERS (Chuyển tiền, Thanh toán, QR, Thu hộ/Chi hộ)

> Áp dụng khi yêu cầu có chuyển tiền nội bộ/liên ngân hàng, thanh toán QR/hóa đơn, thu hộ/chi hộ, hoàn tiền/đảo giao dịch.

## Tham số cần lấy từ BRD
- Hạn mức: tối thiểu/giao dịch, tối đa/giao dịch, lũy kế ngày/tháng; phân theo phân khúc khách hàng, kênh, phương thức xác thực; thời điểm reset hạn mức lũy kế.
- Biểu phí: loại giao dịch, kênh, bên chịu phí, thuế trên phí; có hoàn phí khi giao dịch thất bại hay không.
- Phương thức xác thực theo ngưỡng (OTP, Smart OTP, sinh trắc...) và ngưỡng áp dụng.
- Cơ chế chống trùng (idempotency key, mã tham chiếu, quy tắc phát hiện trùng) — nếu có.
- Hành vi khi đối tác timeout: trạng thái giao dịch, tiền có bị giữ không, cơ chế và chu kỳ đối soát, ai xử lý giao dịch lệch.
- Quy tắc nội dung chuyển khoản (độ dài, ký tự cho phép), truy vấn tên người thụ hưởng.
- Tập trạng thái giao dịch, mã lỗi và message cho từng nguyên nhân từ chối.

## Bất biến nghiệp vụ
- Tài khoản nguồn giảm đúng `số tiền + phí + thuế` (theo bên chịu phí BRD nêu); tài khoản đích tăng đúng số tiền thực nhận; GL cân bằng.
- Một yêu cầu chuyển tiền chỉ tạo ĐÚNG 1 giao dịch ghi nợ dù client gửi lặp (retry, double-click, mạng chập chờn) — theo cơ chế chống trùng BRD nêu.
- Giao dịch thất bại/bị từ chối sau khi đã ghi nợ phải được hoàn về tài khoản nguồn theo đúng cơ chế BRD (kể cả phí nếu BRD quy định hoàn phí).
- Giao dịch chưa xác định kết quả (đối tác timeout) KHÔNG được tự coi là thất bại để hoàn tiền, cũng KHÔNG được coi là thành công — xử lý theo luồng đối soát BRD nêu.
- Hạn mức lũy kế chỉ tính các giao dịch theo đúng quy tắc BRD (thành công / đang xử lý / đã hoàn).

## Biên & giá trị đặc thù
- Từng tầng hạn mức BRD nêu: vừa chạm, vượt 1 đơn vị tiền tệ, giao dịch thứ N làm lũy kế vượt.
- Thời điểm reset hạn mức lũy kế: giao dịch ngay trước và ngay sau mốc reset.
- Ngưỡng chuyển phương thức xác thực: dưới ngưỡng, đúng ngưỡng, vượt ngưỡng; lũy kế trong ngày vượt ngưỡng (nếu BRD tính theo lũy kế).
- Truy vấn tên người thụ hưởng: tài khoản đích không tồn tại, đã đóng, sai ngân hàng, tên không khớp.
- Giao dịch hẹn ngày / định kỳ: ngày thực hiện rơi vào ngày nghỉ, số dư không đủ tại thời điểm chạy, hủy lệnh trước giờ chạy.
- Nội dung chuyển khoản: chạm/vượt độ dài tối đa, tiếng Việt có dấu, ký tự đặc biệt.
- Phát hiện trùng khi không có idempotency (khi BRD nêu quy tắc): trong và ngoài cửa sổ thời gian phát hiện trùng.

## Máy trạng thái
- Giao dịch: dựng theo tập trạng thái BRD (dạng điển hình: khởi tạo -> xác thực -> đang xử lý -> thành công | thất bại | chờ đối soát -> thành công | đã đảo).
- Đối tác timeout: chuyển sang trạng thái chờ đối soát an toàn, không thất thoát tiền, không trừ 2 lần.
- Đối soát: kết quả đối tác = thành công -> chốt; = thất bại -> hoàn tiền + đảo bút toán; lệch số liệu -> xử lý theo BRD.
- Hoàn tiền/Refund: chỉ trên giao dịch đã thành công; tổng tiền hoàn không vượt số tiền gốc; hoàn một phần nhiều lần (nếu BRD cho phép).
- Forbidden điển hình: xác thực sau khi mã xác thực hết hạn; thực hiện lại giao dịch đã thành công; hoàn tiền giao dịch thất bại.

## Tuân thủ & pháp chế
> Chỉ áp dụng khi BRD nêu; ngưỡng/mức lấy từ BRD hoặc Compliance.
- Quy định của NHNN về xác thực giao dịch thanh toán trực tuyến (vd yêu cầu xác thực sinh trắc học theo ngưỡng giá trị) — chỉ với luồng App/Internet Banking mà BRD nêu, không áp dụng cho API backend thuần túy.

## Kỹ thuật bắt buộc nhấn mạnh
- Concurrency & chống trùng: gửi đồng thời/lặp cùng một lệnh; 2 lệnh khác nhau cùng lúc khi số dư chỉ đủ 1.
- Fault injection đối tác: timeout, trả lỗi, trả kết quả muộn sau khi đã timeout, trả kết quả trùng.
- BVA đa tầng hạn mức + mốc reset hạn mức + ngưỡng xác thực.
- End-to-end số liệu: số dư nguồn/đích, phí, thuế, bút toán Nợ/Có, lịch sử giao dịch, thông báo biến động số dư.
- Decision Table phí: chỉ các chiều BRD nêu (loại giao dịch x kênh x bên chịu phí x phân khúc).
