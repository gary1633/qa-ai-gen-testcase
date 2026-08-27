# DOMAIN PACK: SAAS B2B & ENTERPRISE

## Bất biến nghiệp vụ
- Tenant A không bao giờ đọc được dữ liệu (row) của Tenant B (cross-tenant isolation).
- Số lượng seat sử dụng không bao giờ vượt quá seat được cấp theo plan.
- Quota được reset đúng vào mốc chu kỳ billing (billing boundary).

## Biên & giá trị đặc thù
- Seats/quota: `limit - 1 / = limit / limit + 1`.
- Thời điểm hết hạn dùng thử (trial expiry moment): trước/đúng/sau mốc hết hạn.
- Downgrade plan khi usage hiện tại đã vượt cap của plan mới.

## Máy trạng thái
- `TRIAL -> ACTIVE -> PAST_DUE -> SUSPENDED -> CANCELLED`.
- Forbidden: truy cập tính năng trả phí khi ở trạng thái `SUSPENDED` hoặc `CANCELLED`.

## Tuân thủ & pháp chế
- SOC 2 / ISO 27001 — *chỉ áp dụng khi tài liệu yêu cầu có nêu rõ phạm vi tuân thủ này*.

## Kỹ thuật bắt buộc nhấn mạnh
- Cross-tenant isolation negatives: cố truy cập tài nguyên của tenant khác -> `403`.
- RBAC matrix theo vai trò (owner, admin, member, viewer).
- Pairwise testing trên tổ hợp plan × role × feature-flag.
