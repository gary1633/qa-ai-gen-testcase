# DOMAIN PACK: HEALTHCARE

## Bất biến nghiệp vụ
- Không bao giờ để PHI (Protected Health Information) tiếp cận một bác sĩ/nhân viên ngoài mối quan hệ chăm sóc (care relationship) với bệnh nhân đó.
- Mọi lượt đọc PHI đều bắt buộc phải có bản ghi Audit Log.
- Quy tắc dị ứng / tương tác thuốc (allergy/interaction rule) không bao giờ được bỏ qua.

## Biên & giá trị đặc thù
- Độ tuổi bệnh nhân: `0` (sơ sinh), `neonate`, `paediatric`, `adult` — mỗi dải tuổi có ngưỡng liều lượng (dosing band) riêng.
- Ngưỡng chỉ số sinh tồn (vital-sign limits): chạm biên trên/dưới của khoảng an toàn.
- Ngày lưu trữ hồ sơ (record-retention dates): đúng hạn / quá hạn lưu trữ.

## Máy trạng thái
- Hồ sơ điều trị: `ADMITTED -> IN_TREATMENT -> DISCHARGED`.
- Consent (sự đồng ý của bệnh nhân): `GRANTED / WITHDRAWN / EXPIRED`.
- Forbidden: đọc hồ sơ PHI sau khi consent đã `WITHDRAWN` hoặc `EXPIRED`.

## Tuân thủ & pháp chế
- HIPAA / GDPR Art. 9 (dữ liệu sức khỏe là dữ liệu nhạy cảm) — *chỉ áp dụng khi tài liệu yêu cầu có nêu rõ phạm vi tuân thủ này*.

## Kỹ thuật bắt buộc nhấn mạnh
- RBAC matrix theo từng vai trò (bác sĩ, y tá, admin, bệnh nhân).
- Negative authorization: cố truy cập hồ sơ ngoài quyền hạn -> `403`.
- Audit-trail assertions: mỗi lượt đọc/ghi PHI phải sinh ra bản ghi audit kiểm chứng được.
