# MODULE: DEPOSITS (Tiền gửi có kỳ hạn, Tiết kiệm)

> Áp dụng khi yêu cầu có mở sổ/hợp đồng tiền gửi, tính lãi, đáo hạn, tái tục, rút một phần, tất toán (đúng hạn/trước hạn).

## Tham số cần lấy từ BRD
- Số tiền gửi tối thiểu, bậc lãi suất theo số tiền/kỳ hạn, danh sách kỳ hạn.
- Phương thức trả lãi (cuối kỳ, định kỳ, trả trước) và công thức tương ứng, cơ sở ngày tính lãi.
- Rút/tất toán trước hạn: có cho phép không, lãi suất áp dụng, có cho rút một phần không, số dư tối thiểu còn lại.
- Đáo hạn: ngày đáo hạn rơi vào ngày nghỉ/ngày không tồn tại xử lý thế nào; tái tục gốc hay gốc + lãi; lãi suất tái tục lấy tại thời điểm nào; hạn chót thay đổi chỉ thị.
- Thay đổi biểu lãi suất có áp dụng cho sổ đang trong kỳ không.

## Bất biến nghiệp vụ
- Tiền gốc chuyển từ tài khoản nguồn sang tài khoản tiền gửi đúng số tiền; GL cân bằng; tất toán trả đúng gốc + lãi về tài khoản nhận.
- Lãi tính theo lãi suất có hiệu lực theo quy tắc BRD (tại ngày gửi/ngày tái tục); thay đổi biểu lãi suất chỉ áp dụng theo đúng phạm vi BRD nêu.
- Rút một phần (nếu BRD cho phép): phần rút và phần còn lại được tính lãi theo đúng quy tắc BRD.

## Biên & giá trị đặc thù
- Số tiền gửi tối thiểu (Min-1, Min); ngưỡng chuyển bậc lãi suất (ngưỡng-1, ngưỡng, ngưỡng+1).
- Ngày đáo hạn: trước/đúng/sau; rơi vào ngày nghỉ/lễ hoặc ngày 29-31 của tháng ngắn.
- Rút/tất toán trước hạn: 1 ngày trước đáo hạn vs đúng ngày đáo hạn.
- Rút một phần: số dư còn lại vừa chạm và thấp hơn mức tối thiểu.
- Kỳ tính lãi đi qua năm nhuận.
- Thay đổi chỉ thị tái tục ngay trước và sau hạn chót.

## Máy trạng thái
- Sổ tiền gửi: dựng theo BRD (dạng điển hình: mở -> hiệu lực -> rút một phần -> đáo hạn -> tái tục | tất toán); phong tỏa/cầm cố chặn rút và tất toán.
- Forbidden điển hình: rút/tất toán sổ đang phong tỏa/cầm cố; rút một phần làm số dư dưới mức tối thiểu; tất toán sổ đã tất toán.

## Tuân thủ & pháp chế
> Chỉ áp dụng khi BRD nêu; yêu cầu cụ thể lấy từ BRD hoặc Compliance.
- Quy định của NHNN về tiền gửi tiết kiệm và tiền gửi có kỳ hạn (rút trước hạn, lãi suất áp dụng).

## Kỹ thuật bắt buộc nhấn mạnh
- Financial calculation: tiền lãi từng phương thức trả lãi, rút trước hạn, rút một phần, tái tục — expected result ghi số cụ thể tính theo công thức BRD.
- BVA: số tiền tối thiểu, ngưỡng bậc lãi suất, ngày đáo hạn.
- State Transition vòng đời sổ, kể cả thao tác trên sổ phong tỏa/cầm cố.
- Concurrency: tất toán đồng thời từ 2 kênh trên cùng một sổ.
