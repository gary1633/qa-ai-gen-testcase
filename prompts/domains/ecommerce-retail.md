# DOMAIN PACK: E-COMMERCE & RETAIL

## Bất biến nghiệp vụ
- `Oversell = 0`: tồn kho không bao giờ âm.
- Tổng đơn hàng = `Σ(line items) - discount + shipping + tax`.
- Một voucher chỉ được redeem tối đa theo đúng usage rule của nó (per-user / per-order / global cap).

## Biên & giá trị đặc thù
- Tồn kho: `0` (hết hàng), `1` (đơn vị cuối cùng), đúng số lượng tồn kho hiện có (exact-last-unit).
- Giá trị đơn hàng tại mốc điều kiện áp voucher: `min_order - 1` / `= min_order` / `min_order + 1`.
- Mức giảm giá tối đa (discount cap): đúng bằng giới hạn cấu hình.
- Độ chính xác giá (price precision): số lẻ vượt quá số chữ số cho phép.

## Máy trạng thái
- `CART -> PENDING_PAYMENT -> PAID -> FULFILLED -> RETURNED / CANCELLED`.
- Forbidden: hoàn tiền (refund) một đơn đang ở trạng thái `CART`; hủy (cancel) một đơn đã `FULFILLED`.

## Tuân thủ & pháp chế
- PCI-DSS — *chỉ áp dụng khi tài liệu có nêu việc lưu trữ dữ liệu thẻ thanh toán*.

## Kỹ thuật bắt buộc nhấn mạnh
- Concurrency: nhiều người mua cùng tranh sản phẩm còn đúng 1 đơn vị tồn kho.
- Decision Table: voucher stacking (nhiều mã giảm giá áp dụng đồng thời).
- Boundary Value Analysis trên mốc điều kiện áp voucher và tồn kho.
