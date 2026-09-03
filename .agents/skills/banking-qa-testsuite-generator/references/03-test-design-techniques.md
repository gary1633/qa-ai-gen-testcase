# 9 Kỹ thuật Thiết kế Kịch bản Kiểm thử

Áp dụng ở Bước 4 của `SKILL.md`, sau khi Cổng Chặn Cứng (`02-clarification-gate.md`) đã được xử
lý. Mục tiêu: áp dụng ĐỒNG THỜI cả 9 kỹ thuật để đạt độ bao phủ tối đa — số lượng kịch bản không
giới hạn cố định (tối thiểu ~30, có thể hơn 50 nếu tài liệu phức tạp), phải đủ để bao phủ 100% tài
liệu gốc (mọi field/AC/quy tắc nghiệp vụ thực sự có mặt). Tuyệt đối không cắt bớt kịch bản chỉ để
dừng ở một con số cố định khi tài liệu còn nghiệp vụ chưa được bao phủ, và tuyệt đối không tự chế
thêm field/luồng không có trong tài liệu.

## 1. Phân vùng Tương đương (Equivalence Partitioning — EP)
- Phân vùng hợp lệ: từng giá trị hợp lệ của enum (vd: `"flat"`, `"progressive"`, `"fixed"`).
- Phân vùng không hợp lệ: giá trị ngoài whitelist; sai kiểu dữ liệu (String vào Boolean/Int/Float,
  Object vào Array); bỏ trống/thiếu TỪNG trường bắt buộc (field-by-field, 1 test case riêng cho mỗi
  trường); payload chứa trường lạ không khai báo.

## 2. Phân tích Giá trị Biên (Boundary Value Analysis — BVA 2/3-value)
- **Số tiền/hạn mức**: `Min-1`, `Min`, `Min+1`, `Max-1`, `Max`, `Max+1`, số âm, số 0, số thập phân
  vượt precision cho phép.
- **Độ dài chuỗi**: rỗng `""`, chỉ khoảng trắng `"   "`, chạm `maxLength`, vượt `maxLength + 1`.
- **Dải bậc thang/mảng**: mảng rỗng `[]`, 1 phần tử, tối đa phần tử, `min == max`, `min > max`,
  chồng lấn dải (overlap), hở dải (gap), dải cuối bắt buộc `max = null` (test cả trường hợp vi phạm
  quy tắc này).
- **Thời gian & cut-off**: đúng mốc cắt lát giờ nghiệp vụ nêu trong tài liệu (vd: giao dịch ngân
  hàng thường có mốc EOD 18:00 VNT: `17:59:59` bình thường, `18:00:00` bắt đầu chặn).

## 3. Bảng Quyết định & Pairwise Combinatorial (Decision Table & Pairwise Testing)
Khi tính năng có nhiều chiều điều kiện, thay vì Full Cartesian quá lớn, áp dụng Pairwise để rút
gọn số bộ kết hợp (thường 16–20 combo) nhưng đảm bảo 100% cặp giá trị (2-way combination) đều được
kiểm thử. Ví dụ các chiều điển hình ngân hàng: Loại khách hàng (Cá nhân/Doanh nghiệp/VIP) x Loại
tài khoản (CASA/Tiết kiệm có kỳ hạn/Tiết kiệm bậc thang/Thấu chi) x Kênh giao dịch
(Portal/Mobile/OpenAPI/Batch) x Khung giờ & trạng thái (Trong giờ/Ngoài giờ/Nghỉ lễ/Active/Locked).
Với sản phẩm vay/thấu chi có nhiều job thu nợ trong ngày, dựng Decision Table riêng cho thứ tự ưu
tiên thu nợ (Khung giờ Job x Trạng thái Khoản vay) — chỉ khi tài liệu thật sự mô tả cơ chế này.

## 4. Kiểm thử Chuyển đổi Trạng thái (State Transition Testing — STT)
- Vòng đời hợp lệ: xác định đúng chuỗi trạng thái hợp lệ (vd: `DRAFT -> ACTIVE -> SUSPENDED ->
  CLOSED`, hoặc tài khoản `ACTIVE -> DORMANT -> FROZEN -> CLOSED`) theo tài liệu.
- Chuyển trạng thái bất hợp pháp: thử các transition bị cấm rõ ràng (vd: thao tác trên tài khoản
  đang `FROZEN`/`LOCKED`, kích hoạt lại tài khoản `CLOSED`).
- Vòng đời hooks/scheduled events: chỉ áp dụng khi tài liệu nêu rõ cơ chế lịch chạy/cron/hook tự
  động.

## 5. Đua tranh, Trùng lặp & Concurrency (Idempotency & Race Condition)
- **Idempotency Key**: CHỈ áp dụng khi tài liệu/API spec có định nghĩa trường/header
  `idempotency_key` (hoặc cơ chế tương đương). Gửi 2 request cùng key liên tiếp → request thứ 2
  không bị trừ tiền/thực hiện lần 2, trả về kết quả an toàn.
- **Concurrency / Race Condition** (áp dụng chung, không cần idempotency key): 2 giao dịch
  rút/tất toán cùng 1 tài khoản cùng lúc khi số dư chỉ đủ cho 1 giao dịch → 1 thành công, 1 bị từ
  chối do không đủ số dư.
- Không gán ép `idempotency_key` vào API GET, cấu hình tham số, hay luồng không có cơ chế này.

## 6. Đoán lỗi, Tiêm lỗi & Khả năng Phục hồi (Error Guessing & Fault Injection)
- Gateway/network timeout: giả lập đối tác thứ 3 trả `504 Gateway Timeout` → hệ thống chuyển sang
  trạng thái an toàn (retry/pending/đối soát), không làm thất thoát dữ liệu/tiền.
- Rollback: khi một bước xử lý phụ (hook, tính phí, ghi log) lỗi giữa chừng, toàn bộ giao dịch
  chính phải rollback hoàn toàn.
- Malformed JSON: gửi chuỗi JSON thiếu ngoặc, escape sai, payload rỗng `{}`.

## 7. Độ chính xác Tính toán & Pháp chế (Calculation Precision & Compliance)
Chỉ áp dụng khi tài liệu nêu rõ công thức/quy tắc liên quan. Khi có áp dụng: kiểm tra công thức
tổng tiền/phí, quy tắc làm tròn (Banker's Rounding/round-half-even vs round-half-up), số ngày tính
lãi (365 vs 366 ngày năm nhuận), tách bạch thuế VAT khỏi phí gốc. Tuân thủ pháp chế (xác thực sinh
trắc học, PCI-DSS...) CHỈ áp dụng khi tài liệu có đề cập rõ ràng luồng liên quan — không tự gán ép
cho API backend thuần túy không liên quan.

## 8. Bảo mật & Ma trận API/RBAC (Security & API Functional Matrix)
- Happy path (200/201 đúng schema).
- Negative validation (thiếu field bắt buộc, sai kiểu, vượt maxLength, số âm).
- Negative auth/RBAC (không token → 401, token hết hạn → 401, role thấp gọi API admin → 403, chữ
  ký token bị sửa → 401 — chỉ khi API có cơ chế xác thực này).
- Boundary & data extremes (min/max, precision làm tròn, chuỗi rỗng).
- Formatting & data integrity: ký tự đặc biệt, chuỗi khoảng trắng thừa cần trim, Unicode tiếng
  Việt có dấu, rate limit 429 (nếu có cấu hình).
- Pagination/filtering & method semantics: GET phân trang `page`/`limit`, `PUT` ghi đè toàn bộ vs
  `PATCH` chỉ cập nhật field.
- Không cần tạo test case tấn công mạng/SQL Injection trừ khi tài liệu có yêu cầu bảo mật chuyên
  biệt.

## 9. Luồng Nghiệp vụ Đầu-cuối & Tác động Đa bên (End-to-End Business Flow)
Đây là kỹ thuật khác biệt so với Decision Table/API Matrix ở trên: không dừng ở validate 1 lệnh gọi
API/1 màn hình riêng lẻ, mà kiểm tra TRẠNG THÁI/KẾT QUẢ NGHIỆP VỤ THỰC TẾ sau khi hành động hoàn
tất — lấy đúng số liệu/quy tắc đã có căn cứ trong tài liệu, không tự suy diễn số liệu.

- Với mỗi góc nhìn đa bên đã có căn cứ (Khách hàng / Dữ liệu & Sổ sách / Tích hợp & Hạ tầng / Pháp
  chế — xem `01-requirement-analysis-and-rbt.md`), thiết kế ít nhất 1 kịch bản kiểm tra đúng hệ quả
  ở góc nhìn đó (vd: khách hàng nhận đúng thông báo kết quả; dữ liệu ghi nhận nhất quán phục vụ đối
  soát; hệ thống downstream nhận đúng sự kiện).
- Kiểm tra tính nhất quán liên-thực-thể: nếu tài liệu nêu hành động này còn tác động tới đối
  tượng/kênh khác (lịch sử giao dịch, nhật ký audit, thông báo kênh khác), phải có kịch bản xác
  nhận tác động đó — chỉ khi tài liệu thực sự nêu.
- **Tương tác giữa các thành phần trạng thái/số liệu dùng chung**: nếu tính năng thao tác trên các
  thành phần có công thức/quan hệ ràng buộc lẫn nhau đã nêu rõ (vd: Số dư Thực, Số tiền Phong tỏa,
  Hạn mức Thấu chi), thiết kế kịch bản tổ hợp trạng thái của các thành phần đó để xác nhận đúng
  hành vi theo công thức/bất biến đã định nghĩa — không chỉ kiểm tra từng thành phần riêng lẻ. Ví
  dụ: tính năng "bypass phong tỏa" phải có kịch bản kiểm tra khi giao dịch vượt số dư thực (sau khi
  trừ phần phong tỏa) trong lúc bypass đang bật — hệ thống có tự động dùng tiếp hạn mức thấu chi
  (OD) hay từ chối; và kịch bản ngược lại khi hạn mức OD đã dùng hết.
- Nếu tài liệu nhắc tới các thành phần liên quan NHƯNG chưa nêu rõ quy tắc tương tác cụ thể: vẫn
  phải thiết kế kịch bản kiểm tra tương tác đó (đừng bỏ qua vì thiếu thông tin) — đây chính là
  trường hợp cần đánh dấu `PENDING CLARIFICATION` theo `02-clarification-gate.md`, không phải lý
  do để xóa bỏ kịch bản.

## Quy tắc đặt tiêu đề kịch bản (áp dụng ngay từ bước thiết kế)

Mọi tiêu đề phải viết tự nhiên, mạch lạc, đúng bản chất nghiệp vụ — KHÔNG đưa mã ticket vào tiêu
đề (mã ticket/Trace AC-RSK chỉ lưu ở tiền tố cột Điều kiện tiên quyết, xem
`04-test-case-format-and-review.md`), và mọi tên field/giá trị kiểm thử phải bọc trong dấu ngoặc
kép `""`:

1. **Thành công** (Positive EP/Boundary Valid):
   `Kiểm tra [hành động] [đối tượng nghiệp vụ] thành công khi truyền trường "[field]" là "[value]"`
   — vd: `Kiểm tra thực thi giao dịch chuyển tiền Napas 24/7 thành công khi truyền "amount" vừa
   chạm hạn mức tối đa "499,999,999" VND`.
2. **Thất bại/bắt lỗi** (Negative EP/Boundary Invalid/Error Guessing):
   `Kiểm tra [hành động] [đối tượng] không thành công khi truyền thiếu trường "[field]"` — vd:
   `Kiểm tra cập nhật tham số cấu hình phí không thành công khi truyền thiếu trường bắt buộc
   "tiering_method"`.
3. **Trạng thái/Đua tranh/Quyết định**: vd `Kiểm tra hệ thống từ chối giao dịch rút tiền khi tài
   khoản đang ở trạng thái "LOCKED"`, `Kiểm tra chống trừ tiền 2 lần khi gửi đồng thời 2 request
   rút tiền cùng mã "idempotency_key"`.
4. **Nghiệp vụ đầu-cuối/tác động đa bên**: vd `Kiểm tra số dư khả dụng tài khoản nguồn giảm đúng
   "500,000" VND và tài khoản đích tăng đúng số tiền tương ứng sau khi giao dịch chuyển tiền hoàn
   tất`.

## Quy tắc gom nhóm (group_feature / group_functional)

- `group_feature` (banner cấp 1, gắn với 1 AC): `<số>. <tên chức năng nghiệp vụ> (<mã AC>)` — vd
  `1. Chặn rút tiền và tất toán trong thời gian EOD (AC-01)`.
- `group_functional` (banner cấp 2, dùng văn phong nghiệp vụ thuần túy — **tuyệt đối không đưa tên
  kỹ thuật hàn lâm** như "BVA", "Equivalence Partitioning", "Decision Table" vào tiêu đề nhóm): vd
  `1.1. Luồng thực thi giao dịch thành công`, `1.2. Kiểm tra điều kiện chặn giao dịch trong khung
  giờ EOD`, `1.3. Kiểm tra ràng buộc dữ liệu đầu vào và hạn mức`, `1.4. Kiểm tra xử lý đồng thời và
  gửi trùng lệnh`, `1.5. Kiểm tra xử lý ngoại lệ và lỗi hệ thống`, `1.6. Kiểm tra kết quả và tác
  động nghiệp vụ thực tế sau giao dịch`.
- Mỗi kịch bản vẫn lưu kỹ thuật áp dụng vào một trường metadata nội bộ (`testing_technique`), nhưng
  tên kỹ thuật không bao giờ xuất hiện trong `group_feature`, `group_functional`, hay `title`.
