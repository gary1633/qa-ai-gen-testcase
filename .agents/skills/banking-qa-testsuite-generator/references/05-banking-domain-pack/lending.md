# MODULE: LENDING (Khoản vay, Giải ngân, Lịch trả nợ, Thu nợ, Phân loại nợ)

> Áp dụng khi yêu cầu có khởi tạo/phê duyệt khoản vay, giải ngân, lịch trả nợ, tính lãi, thu nợ, trả nợ trước hạn, quá hạn, chuyển nhóm nợ.

## Tham số cần lấy từ BRD
- Phương pháp lịch trả nợ (dư nợ giảm dần, gốc đều, niên kim...), cách xử lý kỳ lẻ và chênh lệch làm tròn.
- Lãi suất cố định/thả nổi: lãi cơ sở, biên độ, kỳ điều chỉnh, áp dụng từ kỳ nào.
- Quy tắc ngày đến hạn rơi vào ngày nghỉ hoặc ngày không tồn tại trong tháng.
- Giải ngân: số lần, thời hạn rút vốn, điều kiện mỗi lần.
- Trả nợ trước hạn: phí (theo thời gian vay?), cách tính lại lịch (giảm số tiền kỳ hay giảm số kỳ).
- Thu nợ: nguồn thu (tài khoản nào), các job/khung giờ thu nợ (nếu có), cấu phần được thu ở từng khung giờ, THỨ TỰ phân bổ theo trạng thái khoản vay, xử lý khi tiền không đủ.
- Quá hạn: cách tính số ngày quá hạn, lãi quá hạn/lãi chậm trả (mức và cơ sở tính), ngưỡng chuyển nhóm nợ và điều kiện hạ nhóm.

## Bất biến nghiệp vụ
- `Dư nợ gốc = Tổng giải ngân - Tổng gốc đã thu`; không âm; tổng giải ngân không vượt số tiền phê duyệt.
- Tổng gốc trong lịch trả nợ = số tiền giải ngân; chênh lệch làm tròn xử lý theo BRD.
- Mỗi khoản tiền thu được phân bổ ĐÚNG MỘT LẦN vào các cấu phần (phí, lãi phạt, lãi chậm trả, lãi, gốc...) theo thứ tự BRD; tổng phân bổ = số tiền thu.
- Cấu phần mà BRD quy định KHÔNG được thu ở một khung giờ/job thì không bao giờ bị thu ở khung giờ/job đó.
- Lãi chỉ tính trên dư nợ gốc thực tế; không tính lãi trên phần chưa giải ngân.

## Biên & giá trị đặc thù
- Lịch trả nợ: kỳ đầu lẻ ngày; kỳ cuối điều chỉnh làm tròn; kỳ tính lãi đi qua năm nhuận.
- Ngày đến hạn rơi vào ngày nghỉ/lễ hoặc ngày 29-31 của tháng ngắn.
- Lãi suất thả nổi: giao dịch trước, đúng và sau ngày điều chỉnh lãi suất.
- Giải ngân nhiều lần: lần cuối vừa chạm số tiền phê duyệt; vượt 1 đơn vị tiền tệ; giải ngân sau hạn rút vốn.
- Trả nợ trước hạn: một phần / toàn bộ; tại các mốc thời gian làm thay đổi phí trả trước (nếu BRD có).
- Thu nợ: tiền chỉ đủ một phần cấu phần -> phân bổ theo thứ tự, phần thiếu xử lý theo BRD (quá hạn, thu ở job sau...).
- Job thu nợ theo khung giờ (khi BRD có nhiều job): giao dịch/tiền về ngay trước và sau từng mốc job; cùng một khoản vay qua nhiều job trong ngày không bị thu trùng.
- Số ngày quá hạn tại từng ngưỡng chuyển nhóm nợ BRD nêu: ngưỡng-1, ngưỡng, ngưỡng+1.

## Máy trạng thái
- Khoản vay: dựng theo BRD (dạng điển hình: hồ sơ -> thẩm định -> phê duyệt | từ chối -> ký hợp đồng -> giải ngân -> trong hạn -> quá hạn -> cơ cấu lại -> tất toán | xử lý rủi ro).
- Quá hạn trả hết nợ -> trạng thái và nhóm nợ sau đó theo quy tắc BRD.
- Forbidden điển hình: giải ngân khi chưa phê duyệt/hợp đồng hết hiệu lực; giải ngân vượt số tiền phê duyệt; thu nợ trên khoản vay đã tất toán; tất toán khi còn dư nợ.

## Tuân thủ & pháp chế
> Chỉ áp dụng khi BRD nêu; ngưỡng/mức lấy từ BRD hoặc Compliance.
- Quy định của NHNN về phân loại nợ (nhóm nợ theo số ngày quá hạn) kết hợp chính sách nội bộ của ngân hàng.
- Quy định của NHNN về lãi suất áp dụng khi chậm trả (trần lãi quá hạn trên gốc, lãi chậm trả trên tiền lãi).

## Kỹ thuật bắt buộc nhấn mạnh
- Decision Table thứ tự phân bổ thu nợ: chỉ các chiều BRD nêu (khung giờ job x trạng thái khoản vay x cấu phần nợ x số tiền đủ/không đủ); có ca riêng xác nhận cấu phần bị loại trừ ở một job không bị thu.
- Financial calculation: lịch trả nợ từng kỳ, lãi ngày, kỳ lẻ, làm tròn, kỳ cuối — expected result ghi số cụ thể tính theo công thức BRD.
- State Transition vòng đời khoản vay + transition bị cấm.
- BVA: số tiền giải ngân, ngày đến hạn, số ngày quá hạn tại ngưỡng chuyển nhóm.
- Kiểm tra giá trị sau cùng của TỪNG cấu phần dư nợ và số dư tài khoản nguồn thu sau khi thu nợ.
