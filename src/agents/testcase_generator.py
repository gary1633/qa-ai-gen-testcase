import time
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from src.core.models import RequirementAnalysis, TestScenario, TestCase, ReviewResult, ReviewIssue
from src.core.llm import invoke_structured_llm
from src.core.prompt_loader import load_prompt, load_domain_pack, load_composite
from src.utils.file_parsers import clean_jira_key_from_title
from src.core.clarification import PENDING_CLARIFICATION_MARKER

class BatchTestSuiteResponse(BaseModel):
    test_cases: List[TestCase] = Field(description="Danh sách test cases chi tiết cho các kịch bản trong lô này")
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="Các câu hỏi BẮT BUỘC phải hỏi lại User khi thiếu API sample, thiếu schema/payload hoặc thiếu câu message/mã lỗi cụ thể. TUYỆT ĐỐI KHÔNG tự bịa giá trị thay cho việc hỏi."
    )


class TestCaseGenerationResult(BaseModel):
    test_cases: List[TestCase] = Field(default_factory=list)
    clarification_questions: List[str] = Field(default_factory=list)


def _generate_single_batch(
    analysis: RequirementAnalysis,
    scenario_batch: List[TestScenario],
    start_tc_num: int,
    today_str: str,
    feedback_prompt: str = "",
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> BatchTestSuiteResponse:
    """
    Sinh test case cho 1 lô kịch bản (8-10 scenarios).
    Prompt được nạp động từ file Markdown: prompts/03_testcase_generator.md.
    """
    system_prompt = load_composite("03_testcase_generator", "shared/severity_priority_rubric")
    domain_pack = load_domain_pack(analysis.banking_domain, analysis.feature_name)

    scenarios_text = ""
    for idx, sc in enumerate(scenario_batch, start=start_tc_num):
        scenarios_text += f"""
---
Mã đề xuất: TC {idx:02d}
Mã Scenario: {sc.scenario_id} | Trace: {sc.trace_ac_id} | Risk: {sc.trace_risk_id or 'N/A'} | Priority: {sc.priority}
Nhóm lớn: {sc.group_feature}
Nhóm con: {sc.group_functional}
Tiêu đề kịch bản: {sc.scenario_title}
Kỹ thuật: {sc.testing_technique}
Ý đồ test: {sc.test_intent}
"""
    ac_text = "\n".join([
        f"- [{ac.ac_id}] {ac.title}: {ac.description} (Rules: {', '.join(ac.business_rules) if ac.business_rules else 'N/A'})"
        for ac in analysis.acceptance_criteria
    ])

    user_prompt = f"""TÍNH NĂNG: {analysis.feature_name}
PHÂN HỆ: {analysis.banking_domain}
MỤC TIÊU NGHIỆP VỤ: {analysis.business_overview or analysis.business_objective}
BẤT BIẾN: {analysis.banking_invariants}
NGÀY: {today_str}

TIÊU CHÍ NGHIỆM THU ĐÃ PHÂN TÍCH (BÁM SÁT 100% CÁC QUY TẮC NÀY):
{ac_text}

================================================================================
DOMAIN PACK (QUY TẮC NGHIỆP VỤ ĐẶC THÙ):
================================================================================
{domain_pack}

HÃY SINH TOÀN BỘ TEST CASE CHI TIẾT 14 CỘT DỮ LIỆU + 2 DÒNG BANNER PHÂN CẤP CHO {len(scenario_batch)} KỊCH BẢN SAU ĐÂY:
{scenarios_text}

{feedback_prompt}

YÊU CẦU QUAN TRỌNG ĐỂ ĐẠT QUALITY GATE >= 95/100:
1. Đặt title theo đúng chuẩn: "Kiểm tra ... thành công khi truyền ..." hoặc "Kiểm tra ... không thành công khi truyền ..." hoặc "Kiểm tra ... hiển thị đúng ... khi input ...", BỌC DẤU NGOẶC KÉP `""` CHO MỌI TÊN TRƯỜNG VÀ GIÁ TRỊ.
2. Trong cột steps, nhúng trực tiếp Body JSON gửi API vào ngay bước 1 với format thụt dòng đẹp.
3. Gán testcase_id tuần tự từ "TC {start_tc_num:02d}" đến "TC {start_tc_num + len(scenario_batch) - 1:02d}".
4. Expected Result BẮT BUỘC định lượng rõ ràng: HTTP Status (vd: 200, 400, 403, 409, 504), Response JSON, mã lỗi nghiệp vụ chính xác (vd: CV_043), số dư tài khoản. Tuyệt đối cấm từ ngữ mơ hồ ("kiểm tra ok", "thành công", "chờ một chút").
5. BẢO TOÀN NGUYÊN VẸN `group_feature` VÀ `group_functional` từ Scenario tương ứng. TUYỆT ĐỐI KHÔNG ĐƯA TÊN KỸ THUẬT HÀN LÂM (như Boundary Value Analysis, BVA, EP...) VÀO TIÊU ĐỀ `group_functional` hay `title`.
6. Cột `note` BẮT BUỘC ghi trace theo đúng định dạng "Trace: AC-xx | RSK-yy | <jira>"; nếu test case triệt tiêu một rủi ro RBT thì PHẢI ghi đúng mã RSK-yy của rủi ro đó.
7. NẾU CÓ FEEDBACK TỪ QA REVIEWER: BẮT BUỘC sửa triệt để 100% các lỗi được chỉ ra để đảm bảo bộ test case đạt điểm tối đa >= 95/100!
8. Thiếu API sample / message -> nêu câu hỏi vào clarification_questions và ghi " | PENDING CLARIFICATION" vào note; TUYỆT ĐỐI KHÔNG tự bịa sample hay câu chữ.
"""
    result: BatchTestSuiteResponse = invoke_structured_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=BatchTestSuiteResponse,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1
    )
    return result


def _generate_supplementary_testcases(
    analysis: RequirementAnalysis,
    coverage_issues: List[ReviewIssue],
    start_tc_num: int,
    today_str: str,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> BatchTestSuiteResponse:
    """Sinh bổ sung các Test Case đặc thù khi Reviewer phát hiện thiếu độ bao phủ hoặc thiếu kỹ thuật."""
    system_prompt = load_composite("03_testcase_generator", "shared/severity_priority_rubric")
    domain_pack = load_domain_pack(analysis.banking_domain, analysis.feature_name)
    issues_desc = "\n".join([f"- {iss.issue_type} ({iss.severity}): {iss.description} -> Yêu cầu: {iss.suggested_fix}" for iss in coverage_issues])

    user_prompt = f"""TÍNH NĂNG: {analysis.feature_name}
PHÂN HỆ: {analysis.banking_domain}
MỤC TIÊU NGHIỆP VỤ: {analysis.business_overview or analysis.business_objective}
BẤT BIẾN: {analysis.banking_invariants}
NGÀY: {today_str}

================================================================================
DOMAIN PACK (QUY TẮC NGHIỆP VỤ ĐẶC THÙ):
================================================================================
{domain_pack}

BỘ TEST SUITE HIỆN TẠI ĐANG THIẾU CÁC KỊCH BẢN KIỂM THỬ QUAN TRỌNG SAU (CẦN BỔ SUNG GẤP ĐỂ ĐẠT QUALITY GATE >= 95/100):
{issues_desc}

YÊU CẦU THỰC HIỆN:
1. Hãy sinh BỔ SUNG ĐẦY ĐỦ các test case chi tiết 14 cột dữ liệu + 2 dòng banner phân cấp tương ứng để triệt tiêu 100% các thiếu sót trên.
2. Bắt đầu từ mã: "TC {start_tc_num:02d}".
3. Đặt tiêu đề theo đúng chuẩn: "Kiểm tra ... thành công khi ..." / "Kiểm tra ... không thành công khi ...", BỌC DẤU NGOẶC KÉP `""` CHO TÊN TRƯỜNG VÀ GIÁ TRỊ.
4. Expected Result định lượng rõ ràng: HTTP Status, JSON response, mã lỗi nghiệp vụ, biến động số dư.
5. Nhúng trực tiếp Body JSON vào bước thực hiện (steps).
6. Cột `note` BẮT BUỘC ghi trace theo đúng định dạng "Trace: AC-xx | RSK-yy | <jira>"; nếu test case triệt tiêu một rủi ro RBT thì PHẢI ghi đúng mã RSK-yy của rủi ro đó.
7. Thiếu API sample / message -> nêu câu hỏi vào clarification_questions và ghi " | PENDING CLARIFICATION" vào note; TUYỆT ĐỐI KHÔNG tự bịa sample hay câu chữ.
"""
    result: BatchTestSuiteResponse = invoke_structured_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=BatchTestSuiteResponse,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1
    )
    return result


def generate_test_cases(
    analysis: RequirementAnalysis,
    scenarios: List[TestScenario],
    review_feedback: Optional[ReviewResult] = None,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    batch_size: int = 10
) -> TestCaseGenerationResult:
    """
    Sinh toàn bộ test cases chi tiết theo cơ chế PACED BATCHING:
    Gộp tối ưu 8-10 kịch bản mỗi lô và thực thi tuần tự có giãn cách để KHÔNG BỊ TRÀN RATE LIMIT (429) của gói Free Tier.
    Tự động sinh bổ sung test case nếu Reviewer phát hiện thiếu độ bao phủ để đảm bảo Quality Gate >= 95/100.
    """
    today_str = datetime.now().strftime("%d/%m/%Y")
    
    feedback_prompt = ""
    if review_feedback and not review_feedback.passed:
        feedback_lines = [
            "================================================================================",
            f"YÊU CẦU BỔ SUNG & CHỈNH SỬA TỪ QA REVIEWER (BẮT BUỘC ĐẠT ĐIỂM >= 95/100):",
            f"- Nhận xét tổng quan: {review_feedback.feedback_summary}",
            f"- Điểm chất lượng hiện tại: {review_feedback.score}/100",
            "- DANH SÁCH CÁC ĐIỂM BẮT BUỘC PHẢI SỬA HOẶC BỔ SUNG CHO ĐÚNG CHUẨN:"
        ]
        for iss in review_feedback.issues:
            target = f"[{iss.target_tc_id}] " if iss.target_tc_id else ""
            feedback_lines.append(f"  * {target}{iss.issue_type} ({iss.severity}): {iss.description} -> Khắc phục: {iss.suggested_fix}")
        feedback_lines.append("================================================================================")
        feedback_prompt = "\n" + "\n".join(feedback_lines) + "\n"
    
    all_test_cases: List[TestCase] = []
    all_questions: List[str] = []
    
    total_scenarios = len(scenarios)
    chunks = [scenarios[i:i + batch_size] for i in range(0, total_scenarios, batch_size)]
    
    for chunk_idx, chunk in enumerate(chunks):
        start_tc_num = len(all_test_cases) + 1
        if chunk_idx > 0:
            time.sleep(2.5)

        batch = _generate_single_batch(
            analysis=analysis,
            scenario_batch=chunk,
            start_tc_num=start_tc_num,
            today_str=today_str,
            feedback_prompt=feedback_prompt,
            provider=provider,
            model_name=model_name,
            base_url=base_url,
            api_key=api_key
        )
        batch_cases = batch.test_cases
        # Bảo toàn chính xác group_feature, group_functional và Note Traceability từ Scenarios
        for sc, tc in zip(chunk, batch_cases):
            if not tc.group_feature or len(tc.group_feature.strip()) < 3:
                tc.group_feature = sc.group_feature
            if not tc.group_functional or len(tc.group_functional.strip()) < 5 or ("." not in tc.group_functional[:5]):
                tc.group_functional = sc.group_functional
            
            # Đồng bộ Trace ID cho Note để đảm bảo Linter và Reviewer truy vết 100%
            trace_items = []
            if sc.trace_ac_id:
                trace_items.append(sc.trace_ac_id)
            if sc.trace_risk_id:
                trace_items.append(sc.trace_risk_id)
            trace_str = " | ".join(trace_items)
            if not tc.note or (sc.trace_ac_id and sc.trace_ac_id not in tc.note):
                tc.note = trace_str

        all_test_cases.extend(batch_cases)
        all_questions.extend(q for q in batch.clarification_questions if q not in all_questions)

    # NẾU CÓ FEEDBACK THIẾU ĐỘ BAO PHỦ -> TỰ ĐỘNG SINH BỔ SUNG TEST CASES
    if review_feedback and not review_feedback.passed:
        coverage_issues = [
            iss for iss in review_feedback.issues
            if any(k in iss.issue_type for k in ["Missing", "Under-Coverage", "Traceability Gap", "Violation", "Gap"])
        ]
        if coverage_issues:
            time.sleep(2.5)
            supp = _generate_supplementary_testcases(
                analysis=analysis,
                coverage_issues=coverage_issues,
                start_tc_num=len(all_test_cases) + 1,
                today_str=today_str,
                provider=provider,
                model_name=model_name,
                base_url=base_url,
                api_key=api_key
            )
            all_test_cases.extend(supp.test_cases)
            all_questions.extend(q for q in supp.clarification_questions if q not in all_questions)

    # Đảm bảo mã testcase_id liên tục, duy nhất và title không chứa mã Jira ticket
    for idx, tc in enumerate(all_test_cases, start=1):
        tc.testcase_id = f"TC {idx:02d}"
        tc.title = clean_jira_key_from_title(tc.title)

    if any(PENDING_CLARIFICATION_MARKER in (tc.note or "") for tc in all_test_cases) and not all_questions:
        all_questions.append(
            "Có test case được đánh dấu PENDING CLARIFICATION nhưng chưa nêu câu hỏi cụ thể. "
            "Vui lòng xác nhận API sample / message chính xác cho các test case này."
        )
    return TestCaseGenerationResult(test_cases=all_test_cases, clarification_questions=all_questions)
