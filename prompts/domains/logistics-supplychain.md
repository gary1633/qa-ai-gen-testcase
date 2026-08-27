# DOMAIN PACK: LOGISTICS & SUPPLY CHAIN

## Bất biến nghiệp vụ
- Trạng thái đơn hàng/kiện hàng (parcel state) không bao giờ được lùi lại (never moves backwards).
- `COD thu được = COD khai báo` (số tiền thu hộ phải khớp chính xác).
- Một mã tracking chỉ map với đúng một kiện hàng (1-1).

## Biên & giá trị đặc thù
- Cân nặng / thể tích quy đổi (volumetric weight) tại đúng biên bảng giá cước (tariff band): `-1 / = / +1`.
- Hạn SLA giao hàng: `-1 giây / = / +1 giây` so với deadline.
- Số lần cố gắng giao hàng (delivery-attempt count) tại đúng giới hạn tối đa.

## Máy trạng thái
- `CREATED -> PICKED_UP -> IN_TRANSIT -> OUT_FOR_DELIVERY -> DELIVERED / RETURNED`.
- Forbidden: chuyển ngược từ `DELIVERED` về `IN_TRANSIT`.

## Tuân thủ & pháp chế
- Quy định vận chuyển hàng hóa đặc biệt / nguy hiểm — *chỉ áp dụng khi tài liệu yêu cầu có nêu rõ*.

## Kỹ thuật bắt buộc nhấn mạnh
- State Transition Testing trên vòng đời kiện hàng, đặc biệt các transition bị cấm.
- Boundary Value Analysis trên các mốc bảng giá cước (tariff band).
- Idempotent scan events: quét trùng cùng một mã tracking không được tạo bản ghi trạng thái trùng lặp.
