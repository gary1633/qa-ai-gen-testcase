# Cổng Chặn Cứng Làm Rõ (Hard-Stop Clarification Gate)

Đây là bảo chứng chất lượng quan trọng nhất của skill này. Áp dụng ở Bước 3 của `SKILL.md`, TRƯỚC
khi thiết kế bất kỳ kịch bản nào ở Bước 4. Nguyên tắc cốt lõi: **KHÔNG BAO GIỜ tự bịa đặt** field
name, cấu trúc JSON, mã lỗi, hay câu message không có căn cứ trong tài liệu — nếu thiếu, phải hỏi
User thay vì suy đoán.

## Khi nào phải dừng lại và hỏi

### 1. Thiếu API sample (chỉ áp dụng cho tính năng liên quan API)
Mặc định: **giả định tính năng có liên quan API** (backend/API-first), trừ khi tài liệu rõ ràng
thuần UI và không hề nhắc tới việc gọi API/endpoint nào. Khi tính năng được coi là có API, bắt buộc
phải có ĐỦ CẢ hai phía:
- **Request mẫu**: method, endpoint, request body/payload.
- **Response mẫu**: response body, HTTP status.

Thiếu 1 trong 2 phía vẫn tính là CHƯA ĐỦ — chỉ hỏi lại đúng phía còn thiếu, không hỏi lại phía đã
có. Một lệnh **cURL thật** mà User dán vào (`curl -X POST https://host/path -H "..." -d '{...}'`)
ĐÃ LÀ một request mẫu hợp lệ và đầy đủ (method + endpoint + header + body) — không được coi cURL là
"chưa rõ" rồi hỏi lại phía request; chỉ hỏi phía response nếu tài liệu thực sự chưa có response mẫu
đi kèm.

### 2. Thiếu message (áp dụng cho MỌI loại tính năng, kể cả thuần UI)
Bắt buộc phải rõ ĐỦ CẢ:
- Message/mã cho luồng **THÀNH CÔNG**.
- Message/mã cho luồng **THẤT BẠI/LỖI**.

Thiếu 1 trong 2 luồng vẫn tính là CHƯA ĐỦ — chỉ hỏi lại đúng luồng còn thiếu.

### 3. Tài liệu mơ hồ, mâu thuẫn, hoặc thiếu thông tin quan trọng khác
Ví dụ: thiếu logic xử lý chính, mâu thuẫn giữa các AC, thiếu tham số cốt lõi, hoặc tính năng phụ
thuộc/tương tác với một cơ chế nghiệp vụ khác (số dư, hạn mức, phong tỏa, quyền...) nhưng tài liệu
KHÔNG nêu rõ quy tắc tương tác giữa chúng và không thể suy đoán an toàn.

### 4. Quy tắc tương tác liên tính năng chưa rõ (Cross-Feature Interaction)
Khi một kịch bản đòi hỏi biết rõ CÁCH hai thành phần/tính năng liên quan tương tác với nhau (vd:
"tính năng A có tự động dùng tiếp hạn mức của tính năng B hay không", "tính năng X có ghi đè/phụ
thuộc tính năng Y hay không") mà tài liệu và câu trả lời trước đó của User đều CHƯA nêu rõ: tuyệt
đối không tự suy đoán kết quả tương tác. Vẫn giữ lại kịch bản đó trong scope, nhưng: (a) chỉ viết
các bước/assertion đã có căn cứ rõ ràng, không kết luận phần chưa rõ; (b) thêm câu hỏi cụ thể nêu
rõ 2 thành phần đang xung đột và tình huống cần làm rõ; (c) đánh dấu test case đó `PENDING
CLARIFICATION`.

## Việc KHÔNG được làm

- Không tự sinh API sample, không tự bịa cấu trúc JSON, không tự đặt tên trường.
- Không tự viết câu message theo ý mình và không dùng placeholder khi tài liệu chưa nêu rõ.
- Không âm thầm bỏ qua/xóa kịch bản chỉ vì thiếu dữ kiện — vẫn giữ trong test suite (cùng 1 sheet
  duy nhất), chỉ đánh dấu chờ làm rõ (xem `references/04-test-case-format-and-review.md`, mục
  "Gấp gọn Trace ID & PENDING CLARIFICATION vào 8 cột").

## Cách đặt câu hỏi & quy tắc miễn (waive) tự do

- Câu hỏi phải cụ thể, súc tích, nêu rõ đang thiếu gì (vd: "Requirement chưa nêu rõ câu message
  lỗi/mã lỗi cụ thể khi giao dịch bị từ chối trong giờ EOD là gì? Vui lòng cung cấp câu message
  mong đợi.").
- User **không cần trả lời đúng khuôn mẫu** "KHÔNG CÓ API"/"KHÔNG CÓ MESSAGE" — chỉ cần diễn đạt
  theo ý mình, hệ thống (bạn) phải tự nhận diện phủ định gần chủ đề để miễn câu hỏi đó. Ví dụ đủ để
  miễn: "tính năng này hiện chưa có API nào cả", "Message: N/A", "chưa cần message riêng".
- Khi thông tin bổ sung từ User đã làm rõ được thắc mắc, không lặp lại câu hỏi đó ở vòng phân tích
  tiếp theo.

## Quy trình khi bị chặn

1. Trình bày rõ ràng cho User: danh sách câu hỏi cần làm rõ, lý do (thiếu request/response/message
   nào), và rằng bạn tạm dừng thiết kế test case cho đến khi có câu trả lời.
2. Nếu User trả lời ngay trong lượt hội thoại đó: gộp câu trả lời làm khối "THÔNG TIN BỔ SUNG /
   LÀM RÕ TỪ USER" và quay lại Bước 2 (`references/01-requirement-analysis-and-rbt.md`) để phân
   tích lại với dữ kiện đầy đủ.
3. Nếu bối cảnh yêu cầu bạn vẫn phải trả về một bản test suite ngay (không thể chờ User trả lời
   trong lượt này): vẫn được phép sinh test suite, nhưng CHỈ giữ lại các assertion đã có căn cứ
   (HTTP status, error_code đã xác nhận, schema structure), đánh dấu mọi test case bị ảnh hưởng với
   tiền tố `[PENDING CLARIFICATION]` ở đầu ô **Kết quả mong đợi** (không phải một cột riêng — vẫn
   nằm trong cùng 1 bảng/1 sheet duy nhất với mọi test case khác, không tách sheet riêng), và liệt
   kê toàn bộ câu hỏi còn mở ở một mục riêng cuối câu trả lời — không bao giờ được lặng lẽ tự bịa
   để lấp đầy chỗ trống thay vì đánh dấu nó.
