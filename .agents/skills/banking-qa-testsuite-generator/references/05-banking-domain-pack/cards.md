# MODULE: CARDS (Thẻ ghi nợ, Thẻ tín dụng, Thẻ trả trước)

> Áp dụng khi yêu cầu có phát hành/kích hoạt/khóa thẻ, PIN, giao dịch thẻ (POS, ATM, e-commerce), cấp phép/quyết toán, hoàn tiền/tra soát, sao kê và thanh toán dư nợ thẻ tín dụng.

## Tham số cần lấy từ BRD
- Vòng đời thẻ: tập trạng thái, ai được khóa/mở khóa, thẻ báo mất có được mở lại không, thay thẻ giữ hay đổi số thẻ.
- PIN: số lần nhập sai tối đa, phạm vi đếm (liên tiếp/trong ngày), cách mở khóa, quy tắc đặt PIN.
- Định dạng che số thẻ trên từng bề mặt (UI, log, response, sao kê, thông báo).
- Hạn mức: hạn mức thẻ, hạn mức rút tiền mặt, hạn mức theo kênh/giao dịch/ngày; có cho phép vượt hạn mức không.
- Cấp phép: thời hạn giữ tiền theo loại giao dịch, quy tắc quyết toán khác số tiền cấp phép, tỷ giá áp dụng cho giao dịch ngoại tệ, phí chuyển đổi ngoại tệ.
- Thẻ tín dụng: ngày sao kê, ngày đến hạn, thời gian miễn lãi, mức thanh toán tối thiểu, lãi/phí rút tiền mặt, phí chậm thanh toán.
- Bật/tắt kênh giao dịch, danh sách MCC bị chặn, phương thức xác thực giao dịch trực tuyến.

## Bất biến nghiệp vụ
- Số thẻ chỉ hiển thị dạng che theo định dạng BRD trên mọi bề mặt; CVV/CVC và PIN KHÔNG bao giờ được lưu hay hiển thị.
- Cấp phép tạm giữ số tiền: `Hạn mức/Số dư khả dụng = Hạn mức (hoặc Số dư) - Tổng đang tạm giữ - Dư nợ đã quyết toán` (công thức chi tiết theo BRD).
- Quyết toán chuyển số tiền tạm giữ thành ghi nợ thật; số tạm giữ tương ứng được giải tỏa — không trừ 2 lần.
- Tổng tiền hoàn cho một giao dịch không vượt số tiền đã quyết toán.
- Thẻ tín dụng: `Dư nợ cuối kỳ sao kê = Dư nợ đầu kỳ + Giao dịch + Phí + Lãi - Thanh toán - Hoàn tiền`.

## Biên & giá trị đặc thù
- PIN: nhập sai N-1 lần (chưa khóa), N lần (khóa), nhập đúng sau khi khóa (vẫn từ chối); bộ đếm reset khi nhập đúng (nếu BRD quy định) — N theo BRD.
- Hạn mức: vừa chạm; vượt 1 đơn vị tiền tệ; mức vượt hạn mức cho phép (nếu có); hạn mức rút tiền mặt riêng.
- Cấp phép: quyết toán ngay trước/sau khi hết thời hạn giữ tiền; quyết toán khác số tiền cấp phép (một phần, cao hơn, tỷ giá).
- Thẻ tín dụng: thanh toán trước/đúng/sau ngày đến hạn; thanh toán đủ / đúng mức tối thiểu / dưới mức tối thiểu; giao dịch ngay trước/sau ngày sao kê.
- Ngày hết hạn thẻ: giao dịch trong tháng hết hạn vs tháng kế tiếp.

## Máy trạng thái
- Thẻ: dựng theo BRD (dạng điển hình: phát hành -> chờ kích hoạt -> hoạt động -> tạm khóa -> mở khóa | báo mất -> thay thế | hết hạn -> gia hạn | đóng).
- Giao dịch thẻ: cấp phép -> (điều chỉnh) -> quyết toán | hủy cấp phép (reversal) | hết hạn cấp phép -> hoàn tiền -> tra soát / chargeback (theo các bước BRD có).
- Forbidden điển hình: giao dịch trên thẻ chưa kích hoạt / tạm khóa / báo mất / hết hạn / đã đóng; mở khóa thẻ đã báo mất; dùng lại thẻ cũ sau khi đã thay thế.
- Bật/tắt kênh và chặn MCC: giao dịch qua kênh đang tắt hoặc MCC bị chặn phải bị từ chối.

## Tuân thủ & pháp chế
> Chỉ áp dụng khi BRD nêu; yêu cầu cụ thể lấy từ BRD hoặc Compliance.
- PCI-DSS (lưu trữ, hiển thị, truyền dữ liệu thẻ).
- Quy định của NHNN về hoạt động thẻ ngân hàng (định danh chủ thẻ, mở thẻ trực tuyến, hạn mức).
- Xác thực giao dịch thẻ trực tuyến (3-D Secure / OTP).

## Kỹ thuật bắt buộc nhấn mạnh
- State Transition vòng đời thẻ và vòng đời giao dịch thẻ, kể cả transition bị cấm.
- BVA: số lần nhập sai PIN, hạn mức, ngày hết hạn thẻ, ngày đến hạn thanh toán, thời hạn giữ tiền cấp phép.
- Decision Table: trạng thái thẻ x kênh x MCC x cờ bật/tắt kênh x hạn mức (chỉ các chiều BRD nêu).
- Concurrency: 2 cấp phép cùng lúc khi hạn mức chỉ đủ 1; quyết toán và reversal đến cùng lúc.
- Kiểm tra che dữ liệu thẻ trên mọi bề mặt BRD nêu.
