# MODULE: OVERDRAFT (Thấu chi / Hạn mức OD)

> Áp dụng khi yêu cầu có cấp/điều chỉnh/thu hồi hạn mức thấu chi, giao dịch sử dụng thấu chi, tính lãi/thu nợ thấu chi. Thu nợ theo khung giờ xem thêm module Lending (được ghép khi tài liệu có thu nợ).

## Tham số cần lấy từ BRD
- Vòng đời hạn mức: điều kiện cấp, ngày hiệu lực, ngày hết hạn, ai được điều chỉnh/thu hồi, có cần phê duyệt không.
- Có cho phép vượt hạn mức không; nếu có thì mức vượt và phí.
- Thứ tự sử dụng nguồn tiền khi giao dịch (số dư thực trước hay sau, phần phong tỏa xử lý thế nào).
- Cách tính lãi thấu chi: dư nợ lấy theo thời điểm nào trong ngày, cơ sở ngày, kỳ thu lãi.
- Thứ tự tự động trả nợ OD khi có tiền về (lãi, phí, gốc) và thời điểm thực hiện.
- Xử lý khi hạn mức hết hạn/bị giảm mà còn dư nợ: chuyển quá hạn, lãi quá hạn, phân loại nợ.

## Bất biến nghiệp vụ
- `Dư nợ OD = phần Số dư Thực bị âm`; `Hạn mức OD còn lại = Hạn mức OD - Dư nợ OD`, không bao giờ âm trừ khi BRD cho phép vượt hạn mức. Cách Số tiền Phong tỏa trừ vào OD theo BRD — nếu BRD không nêu, đưa vào câu hỏi làm rõ (xem bất biến Bypass Phong tỏa ở lõi).
- Giao dịch chỉ được dùng OD khi hạn mức đang hiệu lực, theo thứ tự sử dụng nguồn tiền BRD nêu.
- Tiền về tài khoản tự động trả nợ OD theo đúng thứ tự BRD nêu; tổng phân bổ = số tiền về.
- Lãi thấu chi chỉ tính trên dư nợ OD thực dùng, không tính trên hạn mức được cấp.

## Biên & giá trị đặc thù
- Giao dịch: số dư thực về đúng 0; dùng OD vừa chạm hạn mức; vượt hạn mức 1 đơn vị tiền tệ; mức vượt hạn mức cho phép (nếu có).
- Ngày hiệu lực / hết hạn hạn mức: giao dịch trước, đúng và sau ngày hết hạn; hết hạn khi còn dư nợ.
- Giảm hạn mức xuống thấp hơn dư nợ hiện tại; tăng hạn mức khi đang có dư nợ; hạn mức = 0.
- Tính lãi: dư nợ thay đổi nhiều lần trong ngày; kỳ tính lãi đi qua năm nhuận.
- Tiền về một phần: chỉ đủ cấu phần đầu tiên theo thứ tự BRD; đủ một phần cấu phần tiếp theo; trả hết và dư.

## Máy trạng thái
- Hạn mức OD: dựng theo BRD (dạng điển hình: đề xuất -> phê duyệt -> hiệu lực -> điều chỉnh -> hết hạn | thu hồi | tạm khóa).
- Dư nợ OD quá hạn -> phát sinh lãi quá hạn, chuyển nhóm nợ theo quy tắc BRD.
- Forbidden điển hình: giao dịch dùng OD khi hạn mức hết hạn/thu hồi/tạm khóa; tài khoản ở trạng thái bị chặn vẫn dùng OD.

## Tuân thủ & pháp chế
> Chỉ áp dụng khi BRD nêu; ngưỡng/mức lấy từ BRD hoặc Compliance.
- Lãi quá hạn và phân loại nợ áp dụng như khoản vay (xem module Lending).

## Kỹ thuật bắt buộc nhấn mạnh
- State Transition vòng đời hạn mức, kể cả transition bị cấm.
- BVA hạn mức còn lại và ngày hết hạn hạn mức.
- Decision Table: trạng thái hạn mức x số dư thực x số tiền giao dịch x phong tỏa x cờ bypass (chỉ các chiều BRD nêu).
- Kiểm tra giá trị sau cùng của TỪNG thành phần: số dư thực, dư nợ OD, hạn mức còn lại, số dư khả dụng, lãi dự thu.
