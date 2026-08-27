# RUBRIC DÙNG CHUNG: SEVERITY, PRIORITY & CÁCH TÍNH ĐIỂM (SHARED SEVERITY & PRIORITY RUBRIC)

Đây là định nghĩa DUY NHẤT cho mọi mức độ mà Quality Gate phụ thuộc vào. Người sinh (Scenario Designer, Test Case Generator) và người thẩm định (QA Reviewer) BẮT BUỘC dùng chung rubric này để không lệch chuẩn giữa bên tạo và bên chấm.

================================================================================
1. `ReviewIssue.severity` (Mức độ nghiêm trọng của lỗi phát hiện được):
================================================================================
- **Critical** — Bài kiểm tra nhanh: Một AC hoặc một rủi ro RBT mức Critical/High chưa được bao phủ, HOẶC Expected Result không thể kiểm chứng được, HOẶC Test Case mâu thuẫn trực tiếp với yêu cầu.
- **Major** — Bài kiểm tra nhanh: Thiếu hẳn một nhóm kỹ thuật kiểm thử (EP, BVA, Decision Table...), HOẶC có cụm từ mơ hồ bị cấm, HOẶC test_data là placeholder chung chung, HOẶC các test case trùng lặp nhau.
- **Minor** — Bài kiểm tra nhanh: Lỗi định dạng, đánh số thứ tự, hoặc câu chữ chưa chuẩn văn phong.

================================================================================
2. `TestCase.priority` / `TestScenario.priority` (Mức độ ưu tiên thực thi):
================================================================================
Priority KHÔNG được chọn tự do — PHẢI suy ra từ rủi ro liên kết:
- Nếu case gắn với một `ProductRisk` cụ thể: `risk_score = likelihood × impact` quyết định priority:
  * `risk_score >= 20` → `Critical`
  * `12 <= risk_score <= 19` → `High`
  * `6 <= risk_score <= 11` → `Medium`
  * `risk_score <= 5` → `Low`
- Nếu case không gắn với rủi ro cụ thể nào: dùng `risk_level` của AC liên quan làm priority.

================================================================================
3. `ReviewResult.score` (Cách tính điểm cuối cùng):
================================================================================
- LLM (Semantic Reviewer) CHỈ trả về `semantic_score` — điểm đánh giá chất lượng ngữ nghĩa và logic nghiệp vụ thuần túy.
- Các khoản trừ điểm tất định (deterministic deductions) do Linter phát hiện được áp dụng SAU đó, trong code, không phải bởi LLM.
- TUYỆT ĐỐI KHÔNG được tự ý trừ điểm trước (pre-deduct) cho các lỗi mà Linter tất định đã và sẽ tự phát hiện được (banned phrases, thiếu BVA/EP, thiếu Trace ID, trùng lặp test case...); chỉ chấm điểm chất lượng logic/ngữ nghĩa mà máy không tự kiểm tra được.
