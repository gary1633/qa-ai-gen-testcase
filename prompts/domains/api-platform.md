# DOMAIN PACK: API PLATFORM (DEFAULT FALLBACK)

## Bất biến nghiệp vụ
- Mỗi outcome nghiệp vụ trả về đúng HTTP status code đã tài liệu hóa.
- Response body luôn khớp đúng schema đã khai báo.
- `GET` không bao giờ gây side effect (idempotent, không thay đổi trạng thái hệ thống).

## Biên & giá trị đặc thù
- Bỏ trống từng trường bắt buộc, mỗi lần đúng 1 trường (required-field omission one at a time).
- Sai kiểu dữ liệu (type mismatch): String vào Number, Object vào Array, v.v.
- `maxLength ± 1` cho các trường chuỗi có giới hạn độ dài.
- Mảng rỗng `[]` vs mảng có đúng 1 phần tử.
- Phân trang: `page=0 / page=1 / page=last / page=last+1`.

## Máy trạng thái
- Theo tài liệu API cụ thể; mặc định không giả định vòng đời tài nguyên nếu tài liệu không nêu rõ.

## Tuân thủ & pháp chế
- Không giả định tiêu chuẩn tuân thủ cụ thể — *chỉ áp dụng khi tài liệu yêu cầu có nêu rõ*.

## Kỹ thuật bắt buộc nhấn mạnh
- Ma trận API 7 chiều: Happy Path, Negative Validation, Negative Auth & RBAC, Boundary & Data Extremes, Concurrency & Idempotency, Formatting & Data Integrity, Pagination/Filtering & Method Semantics.
