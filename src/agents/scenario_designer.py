from typing import List, Optional
from pydantic import BaseModel, Field
from src.core.models import RequirementAnalysis, TestScenario
from src.core.llm import invoke_structured_llm
from src.core.prompt_loader import load_prompt
from src.utils.file_parsers import clean_jira_key_from_title


class ScenarioListResponse(BaseModel):
    scenarios: List[TestScenario] = Field(description="Danh sách từ 30 đến 50+ kịch bản kiểm thử chi tiết bao phủ toàn diện 8 kỹ thuật ISTQB")


def design_test_scenarios(
    analysis: RequirementAnalysis,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> List[TestScenario]:
    """
    Thiết kế Ma trận Kịch bản Kiểm thử Chuyên sâu (30 - 50+ Scenarios)
    kết hợp đồng thời 8 kỹ thuật ISTQB: EP, BVA, Decision Table, State Transition, Idempotency, Fault Injection, Financial Precision, Security.
    Prompt được nạp động từ file Markdown: prompts/02_scenario_designer.md.
    """
    system_prompt = load_prompt("02_scenario_designer")

    user_prompt = f"""DỰA TRÊN TÀI LIỆU YÊU CẦU & BÁO CÁO PHÂN TÍCH SAU:

1. TÍNH NĂNG: {analysis.feature_name}
2. PHÂN HỆ: {analysis.banking_domain}
3. MỤC TIÊU: {analysis.business_overview or analysis.feature_name}
4. DANH SÁCH ACCEPTANCE CRITERIA (AC):
{chr(10).join([f"- [{ac.ac_id}] {ac.title}: {ac.description} (Rules: {ac.business_rules})" for ac in analysis.acceptance_criteria])}

5. MA TRẬN RỦI RO SẢN PHẨM (RBT PRODUCT RISKS):
{chr(10).join([f"- [{getattr(r, 'risk_id', 'RSK-01')}] ({getattr(r, 'risk_level', 'Medium')} - {getattr(r, 'risk_category', 'Business Logic')}) {getattr(r, 'risk_title', '')}: {getattr(r, 'risk_description', '') or getattr(r, 'risk_title', '')} -> Focus: {getattr(r, 'mitigation_test_focus', '')}" for r in analysis.product_risks])}

6. CÁC ĐIỂM BẤT BIẾN NGÂN HÀNG (BANKING INVARIANTS):
{chr(10).join([f"- {inv}" for inv in analysis.banking_invariants])}

7. CÁC ĐIỀU KIỆN BIÊN & NGOẠI LỆ ĐÃ XÁC ĐỊNH:
{chr(10).join([f"- {ec}" for ec in analysis.edge_cases])}

================================================================================
NHIỆM VỤ THIẾT KẾ MA TRẬN KỊCH BẢN KIỂM THỬ:
================================================================================
Hãy áp dụng TOÀN BỘ 8 KỸ THUẬT ISTQB (EP, BVA 2-value/3-value, Decision Table, State Transition, Idempotency/Concurrency, Fault Injection, Financial Calculation, Security) để tạo ra bộ ma trận kiểm thử TOÀN DIỆN với SỐ LƯỢNG TỪ 30 ĐẾN 50+ KỊCH BẢN.

ĐẢM BẢO BAO PHỦ:
1. Từng trường dữ liệu trong Schema/DTO (Positive, Missing field, Wrong type, Out-of-range enum).
2. Dải giá trị và cấu trúc mảng lồng nhau (Mảng rỗng, min > max, overlap bands, gap bands, band cuối max=null).
3. Biên số tiền, số âm, số 0, precision làm tròn Banker's Rounding, năm nhuận 365 vs 366 ngày, tách thuế VAT.
4. Đua tranh (Concurrency), trùng Idempotency Key, chống trừ tiền 2 lần.
5. Vòng đời Scheduled Events, Cron ngày 01 hàng tháng, Activation Hooks khi mở tài khoản CASA.
6. Lỗi mạng Timeout 504, Rollback giao dịch khi lỗi, Payload injection và phân quyền.

YÊU CẦU:
- Đặt `scenario_title` tự nhiên, đúng ngữ cảnh nghiệp vụ ngân hàng và BỌC DẤU NGOẶC KÉP `""` CHO TẤT CẢ TÊN TRƯỜNG VÀ GIÁ TRỊ.
- Gán đúng `testing_technique`: "Equivalence Partitioning", "Boundary Value Analysis", "Decision Table", "State Transition", "Idempotency & Concurrency", "Fault Injection & Resilience", "Financial Calculation", "Security Testing".
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
