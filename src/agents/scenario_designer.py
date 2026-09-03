from typing import List, Optional
from pydantic import BaseModel, Field
from src.core.models import RequirementAnalysis, TestScenario
from src.core.llm import invoke_structured_llm
from src.core.prompt_loader import load_prompt, load_domain_pack, load_composite
from src.utils.file_parsers import clean_jira_key_from_title


class ScenarioListResponse(BaseModel):
    scenarios: List[TestScenario] = Field(description="Danh sách kịch bản kiểm thử chi tiết bao phủ toàn diện 9 kỹ thuật ISTQB & Business-Flow; số lượng KHÔNG giới hạn cố định (tối thiểu 30), phải sinh đủ để bao phủ 100% tài liệu gốc và Acceptance Criteria được cung cấp")


def design_test_scenarios(
    analysis: RequirementAnalysis,
    raw_content: str = "",
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> List[TestScenario]:
    """
    Thiết kế Ma trận Kịch bản Kiểm thử Chuyên sâu (số lượng KHÔNG giới hạn cố định, tối thiểu 30, đủ để bao phủ 100% tài liệu)
    kết hợp đồng thời 9 kỹ thuật ISTQB & Business-Flow: EP, BVA, Decision Table, State Transition, Idempotency, Fault Injection, Financial Precision, Security, Business Flow / End-to-End Impact.
    Prompt được nạp động từ file Markdown: prompts/02_scenario_designer.md.
    """
    system_prompt = load_composite("02_scenario_designer", "shared/severity_priority_rubric")
    domain_pack = load_domain_pack(analysis.banking_domain, analysis.feature_name)

    user_prompt = f"""DỰA TRÊN TÀI LIỆU YÊU CẦU & BÁO CÁO PHÂN TÍCH SAU:

1. TÍNH NĂNG: {analysis.feature_name}
2. PHÂN HỆ: {analysis.banking_domain}
3. MỤC TIÊU: {analysis.business_overview or analysis.feature_name}
4. DANH SÁCH ACCEPTANCE CRITERIA (AC):
{chr(10).join([f"- [{ac.ac_id}] {ac.title}: {ac.description} (Rules: {ac.business_rules})" for ac in analysis.acceptance_criteria])}

5. MA TRẬN RỦI RO SẢN PHẨM (RBT PRODUCT RISKS):
{chr(10).join([f"- [{getattr(r, 'risk_id', 'RSK-01')}] ({getattr(r, 'risk_level', 'Medium')} - {getattr(r, 'risk_category', 'Business Logic')}) {getattr(r, 'risk_title', '')}: {getattr(r, 'risk_description', '') or getattr(r, 'risk_title', '')} -> Focus: {getattr(r, 'mitigation_test_focus', '')}" for r in analysis.product_risks])}

6. BẤT BIẾN NGHIỆP VỤ (DOMAIN INVARIANTS):
{chr(10).join([f"- {inv}" for inv in analysis.banking_invariants])}

7. CÁC ĐIỀU KIỆN BIÊN & NGOẠI LỆ ĐÃ XÁC ĐỊNH:
{chr(10).join([f"- {ec}" for ec in analysis.edge_cases])}
================================================================================
DOMAIN PACK (QUY TẮC NGHIỆP VỤ ĐẶC THÙ):
================================================================================
{domain_pack}

================================================================================
TÀI LIỆU GỐC DO USER CUNG CẤP (THAM KHẢO TRỰC TIẾP ĐỂ BÁM SÁT ĐÚNG FIELD NAME / API MẪU / SỐ LIỆU THẬT — KHÔNG CHỈ DỰA VÀO BẢN TÓM TẮT AC Ở TRÊN):
================================================================================
{raw_content or "(Không có tài liệu gốc đính kèm ngoài bản phân tích trên)"}

================================================================================
NHIỆM VỤ THIẾT KẾ MA TRẬN KỊCH BẢN KIỂM THỬ:
================================================================================
Hãy áp dụng TOÀN BỘ 9 KỸ THUẬT ISTQB & BUSINESS-FLOW (EP, BVA 2-value/3-value, Decision Table, State Transition, Idempotency/Concurrency, Fault Injection, Financial Calculation, Security, Business Flow / End-to-End Impact) để tạo ra bộ ma trận kiểm thử TOÀN DIỆN. SỐ LƯỢNG KỊCH BẢN KHÔNG GIỚI HẠN CỐ ĐỊNH (tối thiểu 30) — PHẢI sinh đủ số lượng cần thiết để bao phủ 100% các trường/luồng/quy tắc nghiệp vụ thực sự có trong TÀI LIỆU GỐC và Acceptance Criteria bên trên; TUYỆT ĐỐI KHÔNG dừng lại ở một con số cố định (vd: đúng 30) nếu tài liệu còn field/AC/quy tắc chưa được bao phủ.

ĐẢM BẢO BAO PHỦ:
1. Từng trường dữ liệu trong Schema/DTO (Positive, Missing field, Wrong type, Out-of-range enum).
2. Dải giá trị và cấu trúc mảng lồng nhau (Mảng rỗng, min > max, overlap bands, gap bands, band cuối max=null).
3. Các mốc biên và bất biến nghiệp vụ được nêu tại mục "## Biên & giá trị đặc thù" và "## Bất biến nghiệp vụ" của DOMAIN PACK bên trên.
4. Đua tranh (Concurrency), trùng Idempotency Key (chỉ khi API/tài liệu có định nghĩa cơ chế này), chống xử lý trùng request.
5. Vòng đời trạng thái (State Transition) theo đúng "## Máy trạng thái" của DOMAIN PACK, và các Hooks/Scheduled Events chỉ khi tài liệu có nêu rõ.
6. Lỗi mạng Timeout 504, Rollback giao dịch khi lỗi, Payload injection và phân quyền.
7. TÁC ĐỘNG NGHIỆP VỤ THỰC TẾ SAU KHI HÀNH ĐỘNG HOÀN TẤT (không chỉ dừng ở response API/màn hình): trạng thái/số liệu nghiệp vụ cuối cùng (số dư, sổ cái, tồn kho, vòng đời đối tượng) khớp đúng "MỤC TIÊU" và "BẤT BIẾN NGHIỆP VỤ" nêu trên; và hệ quả tới các góc nhìn liên quan thực sự có căn cứ trong tài liệu (khách hàng, dữ liệu/sổ sách, tích hợp hạ tầng, pháp chế) — không suy diễn góc nhìn không có căn cứ.
8. LIỆT KÊ TƯỜNG MINH (EXHAUSTIVE ENUMERATION): Khi tài liệu/AC nêu MỘT DANH SÁCH các giá trị/loại/mã riêng biệt cùng nhóm (vd: các posting type, các mã lỗi CV_xxx, các kênh giao dịch, các trạng thái workflow) — PHẢI thiết kế ÍT NHẤT 1 kịch bản CHO TỪNG giá trị được liệt kê, TUYỆT ĐỐI KHÔNG chỉ chọn một vài giá trị đại diện rồi bỏ qua phần còn lại của danh sách.
9. ĐỐI CHIẾU ĐA NGUỒN TÀI LIỆU THAM KHẢO: Nếu TÀI LIỆU GỐC bên trên có nhiều khối `## [Tài liệu N - ...]` (US + file BRD/SRS/Figma/API Spec/Bug Dashboard đính kèm), PHẢI đọc và khai thác chi tiết ở TẤT CẢ các khối đó, thiết kế cả các kịch bản CHỈ phát sinh khi KẾT HỢP chi tiết từ ≥2 tài liệu khác nhau — không chỉ dựa vào tài liệu US/ticket chính.

YÊU CẦU:
- Đặt `scenario_title` tự nhiên, đúng ngữ cảnh nghiệp vụ của domain đang kiểm thử và BỌC DẤU NGOẶC KÉP `""` CHO TẤT CẢ TÊN TRƯỜNG VÀ GIÁ TRỊ.
- Gán đúng `testing_technique`: "Equivalence Partitioning", "Boundary Value Analysis", "Decision Table", "State Transition", "Idempotency & Concurrency", "Fault Injection & Resilience", "Financial Calculation", "Security Testing", "Business Flow / End-to-End Impact".
"""

    result: ScenarioListResponse = invoke_structured_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=ScenarioListResponse,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1
    )

    for sc in result.scenarios:
        sc.scenario_title = clean_jira_key_from_title(sc.scenario_title)

    return result.scenarios
