from typing import List, Optional
from pydantic import BaseModel, Field
from src.core.models import RequirementAnalysis, TestCase, TestScenario, ReviewResult, ReviewIssue, TraceabilityItem
from src.core.linter import lint_test_case, lint_test_suite_coverage, lint_scenarios
from src.core.llm import invoke_structured_llm, load_qa_rules
from src.core.prompt_loader import load_composite, load_domain_pack


class SemanticReviewPayload(BaseModel):
    semantic_score: int = Field(description="Điểm đánh giá chất lượng ngữ nghĩa và logic nghiệp vụ Banking (0-100)")
    traceability_matrix: List[TraceabilityItem] = Field(default_factory=list, description="Ma trận truy vết 2 chiều giữa từng AC và các Test Cases bao phủ")
    semantic_issues: List[ReviewIssue] = Field(default_factory=list, description="Các lỗi logic hoặc thiếu sót kịch bản nghiệp vụ phát hiện được")
    feedback_summary: str = Field(description="Tóm tắt nhận xét và hướng dẫn hoàn thiện cho Banking QA kèm báo cáo Traceability")


def review_and_lint_test_suite(
    analysis: RequirementAnalysis,
    test_cases: List[TestCase],
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    *,
    scenarios: Optional[List[TestScenario]] = None,
    raw_content: str = ""
) -> ReviewResult:
    """
    Kết hợp Rule-based Linter và LLM Semantic Review để đánh giá toàn diện chất lượng Test Suite.
    Thực hiện kiểm tra Bidirectional Traceability (Truy vết 2 chiều) và Requirement Drift Detection.
    Prompt được nạp động từ file Markdown: prompts/04_qa_reviewer.md + prompts/shared/severity_priority_rubric.md.
    """
    system_prompt = load_composite("04_qa_reviewer", "shared/severity_priority_rubric")
    domain_pack = load_domain_pack(analysis.banking_domain, analysis.feature_name)

    # 1. Chạy Deterministic Linter (Test Case level + Scenario level)
    static_issues: List[ReviewIssue] = []
    for tc in test_cases:
        static_issues.extend(lint_test_case(tc))
    static_issues.extend(lint_test_suite_coverage(analysis, test_cases, raw_content=raw_content))
    static_issues.extend(lint_scenarios(analysis, scenarios or []))

    # 2. Chuẩn bị prompt cho Semantic Reviewer
    user_prompt = f"""TÍNH NĂNG: {analysis.feature_name}
PHÂN HỆ: {analysis.banking_domain}
BẤT BIẾN NGHIỆP VỤ: {analysis.banking_invariants}

================================================================================
DOMAIN PACK (QUY TẮC NGHIỆP VỤ ĐẶC THÙ - DÙNG ĐỂ ĐÁNH GIÁ ĐỘ BAO PHỦ):
================================================================================
{domain_pack}

DANH SÁCH TIÊU CHÍ CHẤP NHẬN (AC) & BUSINESS RULES:
"""
    for ac in analysis.acceptance_criteria:
        user_prompt += f"- [{ac.ac_id}] {ac.title} (Risk: {ac.risk_level}): {ac.description} (Rules: {ac.business_rules})\n"

    user_prompt += f"\nMA TRẬN RỦI RO RBT ({len(analysis.product_risks)} risks):\n"
    for rsk in analysis.product_risks:
        user_prompt += f"- [{rsk.risk_id}] (Score: {rsk.risk_score} - {rsk.risk_level}) {rsk.risk_title} -> Trọng tâm test: {rsk.mitigation_test_focus}\n"

    user_prompt += f"\nDANH SÁCH TEST CASE HIỆN TẠI ({len(test_cases)} cases):\n"
    for tc in test_cases:
        user_prompt += f"""
---
[{tc.testcase_id}] {tc.title}
- Priority: {tc.priority} | Note / Trace: {tc.note}
- Preconditions: {tc.preconditions}
- Steps: {tc.steps}
- Expected: {tc.expected_result}
- Test Data: {tc.test_data}
"""

    semantic_response: SemanticReviewPayload = invoke_structured_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=SemanticReviewPayload,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1
    )
    
    # Tổng hợp và loại bỏ trùng lặp issues
    all_issues: List[ReviewIssue] = list(static_issues)
    seen_descs = {f"{i.target_tc_id}_{i.issue_type}" for i in static_issues}
    for s_iss in semantic_response.semantic_issues:
        key = f"{s_iss.target_tc_id}_{s_iss.issue_type}"
        if key not in seen_descs:
            all_issues.append(s_iss)
            seen_descs.add(key)

    # Tính điểm chuẩn hóa (Không phạt điểm kép, tính theo tỷ lệ bao phủ thực tế)
    suite_issues = [i for i in static_issues if not i.target_tc_id]
    tc_issues = [i for i in static_issues if i.target_tc_id]
    
    # Lỗi cấp độ toàn bộ Suite (ví dụ: thiếu hẳn 1 AC lớn, thiếu negative EP)
    suite_deduction = sum(15 if i.severity == "Critical" else (8 if i.severity == "Major" else 2) for i in suite_issues)
    
    # Lỗi cấp độ từng Test Case (chuẩn hóa theo số lượng test case để tránh bộ test nhiều case bị phạt oan)
    if test_cases:
        tc_weight = sum(1.0 if i.severity == "Critical" else (0.5 if i.severity == "Major" else 0.1) for i in tc_issues)
        tc_ratio = tc_weight / len(test_cases)
        tc_deduction = min(20, int(tc_ratio * 20))
    else:
        tc_deduction = 0

    total_deduction = suite_deduction + tc_deduction
    final_score = max(0, min(100, semantic_response.semantic_score - total_deduction))
    
    has_critical = any(issue.severity == "Critical" for issue in all_issues)
    has_major = any(issue.severity == "Major" for issue in all_issues)
    
    # Quality Gate: Pass nếu score >= min_review_score (config.yaml qa_rules) và KHÔNG có Critical / Major issues
    min_score = load_qa_rules()["min_review_score"]
    is_passed = (final_score >= min_score) and (not has_critical) and (not has_major)
    return ReviewResult(
        total_cases_reviewed=len(test_cases),
        passed=is_passed,
        score=final_score,
        traceability_matrix=semantic_response.traceability_matrix,
        issues=all_issues,
        feedback_summary=semantic_response.feedback_summary
    )


def gate_failure_reasons(review_result: ReviewResult) -> List[str]:
    """Liệt kê ĐÚNG (các) lý do CHƯA ĐẠT Quality Gate, khớp chính xác điều kiện gate ở trên:
    score >= min_review_score (config.yaml) VÀ KHÔNG có issue Critical/Major. Điểm số đạt ngưỡng
    không đồng nghĩa với PASSED nếu vẫn còn issue Critical/Major chưa xử lý — hàm này tránh hiển thị
    lý do sai (vd: báo "Score 96 < 95" trong khi 96 >= 95 và lý do thật là còn issue Critical)."""
    min_score = load_qa_rules()["min_review_score"]
    reasons: List[str] = []
    if review_result.score < min_score:
        reasons.append(f"Score {review_result.score}/100 chưa đạt ngưỡng {min_score}/100")
    if any(issue.severity == "Critical" for issue in review_result.issues):
        reasons.append("còn issue mức Critical chưa xử lý")
    if any(issue.severity == "Major" for issue in review_result.issues):
        reasons.append("còn issue mức Major chưa xử lý")
    return reasons
