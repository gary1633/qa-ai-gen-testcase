# 📁 Thư Mục Lưu Trữ Tài Liệu Yêu Cầu (Requirements & Specs)

Thư mục này dùng để lưu trữ các tài liệu đầu vào phục vụ cho **QA Agentic Workflow** tự động phân tích và sinh Test Suite.

---

### 📄 Các định dạng file được hỗ trợ:
1. **Microsoft Word (`.docx`):** PRD, SRS, Business Requirement Document, Spec kỹ thuật. *(AI tự động bóc tách Headings, Bullet points và Bảng biểu)*.
2. **PDF Document (`.pdf`):** Tài liệu tài chính, quy chuẩn pháp lý (vd: QĐ 2345/QĐ-NHNN), báo cáo kiến trúc.
3. **Markdown (`.md`, `.markdown`):** User Stories, Release Notes, Acceptance Criteria.
4. **Text / JSON / YAML (`.txt`, `.json`, `.yaml`, `.yml`):** OpenAPI / Swagger spec, Payload mẫu, Data Dictionary, DB Schema.

---

### 🚀 Cách chạy Test Suite với các file trong thư mục `docs/`:

```bash
# 1. Chạy với 1 file trong docs:
python run.py "docs/PRD_Chuyen_Tien_Napas.docx"

# 2. Kết hợp file trong docs với 1 Ticket Jira:
python run.py VWCBT-3800 "docs/API_Spec.docx"

# 3. Kết hợp nhiều file cùng lúc:
python run.py "docs/PRD_Savings.docx" "docs/Data_Schema.pdf" "docs/OpenAPI.yaml"
```
