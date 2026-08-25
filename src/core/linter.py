import re
from typing import List
from src.core.models import RequirementAnalysis, TestCase, ReviewIssue

BANNED_PHRASES = [
    # English
    "verify it works", "looks right", "wait a bit", "some valid data", "some data",
    "check if ok", "see if it works", "normal flow", "proper result", "appropriate message",
    # Vietnamese (Những từ cấm gây mơ hồ trong Steps và Expected Result)
    "kiểm tra xem có hoạt động không", "thấy đúng", "chờ một chút",
    "nhập dữ liệu bất kỳ", "nhập thông tin hợp lệ", "kết quả phù hợp", "thông báo tương ứng",
    "kiểm tra ok", "thành công như mong đợi", "xử lý đúng đắn"
]

def lint_test_case(tc: TestCase) -> List[ReviewIssue]:
    """
    Kiểm tra chất lượng ngữ nghĩa và quy chuẩn của từng Test Case (Deterministic Linter).
    """
    issues: List[ReviewIssue] = []
    
    # 1. Banned phrases check chỉ trong Steps và Expected Result
    body_text = f"{tc.steps} {tc.expected_result}".lower()
    for phrase in BANNED_PHRASES:
        if phrase in body_text:
            issues.append(ReviewIssue(
                target_tc_id=tc.testcase_id,
                issue_type="Ambiguous Step",
                severity="Major",
                description=f"Test case chứa cụm từ mơ hồ bị cấm: '{phrase}'.",
                suggested_fix=f"Thay thế '{phrase}' bằng hành động hoặc kết quả đo lường cụ thể (mã HTTP, JSON response, số dư, thông báo lỗi chính xác)."
            ))

    # 2. Kiểm tra độ chi tiết của Expected Result (Non-deterministic)
    if len(tc.expected_result.strip()) < 15:
        issues.append(ReviewIssue(
            target_tc_id=tc.testcase_id,
            issue_type="Non-Deterministic Expected Result",
            severity="Critical",
            description="Kết quả mong đợi quá ngắn hoặc không có tiêu chí kiểm chứng rõ ràng.",
            suggested_fix="Mô tả cụ thể HTTP status, JSON body, mã lỗi, hoặc biến động số dư tài khoản."
        ))

    # 3. Kiểm tra Test Data cụ thể (Vague Test Data & Placeholders)
    placeholder_patterns = ["some data", "some string", "any data", "any string", "valid data", "test data", "dữ liệu bất kỳ", "nhập tùy ý", "chuỗi bất kỳ"]
    has_placeholder = any(p in (tc.test_data or "").lower() for p in placeholder_patterns)
    if not tc.test_data or len(tc.test_data.strip()) < 3 or has_placeholder:
        issues.append(ReviewIssue(
            target_tc_id=tc.testcase_id,
            issue_type="Vague Test Data",
            severity="Major",
            description="Dữ liệu kiểm thử (Test Data) bị trống, sơ sài hoặc chứa placeholder chung chung.",
            suggested_fix="Cung cấp payload JSON cụ thể theo format chuẩn traceable: 'auto_<module>_<id>_<timestamp>', số tài khoản, số tiền, hoặc tham số đầu vào thực tế."
        ))

    # 4. Kiểm tra Format các bước thực hiện (Numbered Steps)
    if not re.search(r"^\s*1[\.\)]", tc.steps, re.MULTILINE):
        issues.append(ReviewIssue(
            target_tc_id=tc.testcase_id,
            issue_type="Format Violation",
            severity="Minor",
            description="Các bước thực hiện (Steps) không được đánh số thứ tự chuẩn (1. ... 2. ...).",
            suggested_fix="Định dạng lại các bước theo cấu trúc: '1. Bước một\\n2. Bước hai\\n3. Bước ba'."
        ))

    return issues

def lint_test_suite_coverage(analysis: RequirementAnalysis, test_cases: List[TestCase]) -> List[ReviewIssue]:
    """
    Kiểm tra độ bao phủ yêu cầu (Traceability & RBT Coverage) và tiêu chuẩn Banking Chuyên sâu.
    """
    issues: List[ReviewIssue] = []
    
    # 1. Kiểm tra 100% AC có Test Case tương ứng
    ac_ids_in_analysis = {ac.ac_id for ac in analysis.acceptance_criteria}
    ac_ids_covered = set()
    
    for tc in test_cases:
        content_to_check = f"{tc.title} {tc.group_feature} {tc.note}"
        for ac_id in ac_ids_in_analysis:
            if ac_id in content_to_check:
                ac_ids_covered.add(ac_id)
                
    missing_acs = ac_ids_in_analysis - ac_ids_covered
    if missing_acs:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Traceability Gap",
            severity="Critical",
            description=f"Thiếu test case bao phủ các Acceptance Criteria sau: {', '.join(sorted(missing_acs))}",
            suggested_fix="Bổ sung ít nhất 1-2 test cases (Positive và Negative) cho các AC còn thiếu."
        ))

    # 2. Kiểm tra RBT Risk Coverage: Rủi ro Critical / High bắt buộc phải có test case
    high_critical_risks = [r for r in analysis.product_risks if r.risk_level in ["Critical", "High"]]
    for risk in high_critical_risks:
        risk_covered = any(
            risk.risk_id in f"{tc.title} {tc.note} {tc.group_feature}" or 
            risk.linked_ac_id in f"{tc.title} {tc.note} {tc.group_feature}"
            for tc in test_cases
        )
        if not risk_covered:
            issues.append(ReviewIssue(
                target_tc_id=None,
                issue_type="RBT Under-Coverage Violation",
                severity="Critical",
                description=f"Rủi ro mức {risk.risk_level} [{risk.risk_id}]: '{risk.risk_title}' (Category: {risk.risk_category}) chưa được bao phủ bởi kịch bản kiểm thử.",
                suggested_fix=f"Bổ sung kịch bản kiểm thử trực diện để triệt tiêu rủi ro này: {risk.mitigation_test_focus}"
            ))

    # 3. BANKING DOMAIN LINTER: Kiểm tra các quy tắc Banking đặc thù
    all_tc_text = " ".join([f"{tc.title} {tc.steps} {tc.expected_result} {tc.test_data}" for tc in test_cases]).lower()
    
    # 3.1. Nếu là Payment & Transfers hoặc Chuyển tiền / Trừ tiền: Bắt buộc có kịch bản Đua tranh / Concurrency / Xử lý gửi trùng lặp
    is_payment_transfer = (
        ("payment" in analysis.banking_domain.lower() or "transfer" in analysis.banking_domain.lower() or "chuyển tiền" in analysis.feature_name.lower() or "napas" in analysis.feature_name.lower())
        and any(("chuyển" in f"{ac.description} {ac.title}".lower() or "thanh toán" in f"{ac.description} {ac.title}".lower() or "transfer" in f"{ac.description} {ac.title}".lower() or "napas" in f"{ac.description} {ac.title}".lower()) for ac in analysis.acceptance_criteria)
    )
    if is_payment_transfer:
        has_concurrency = "trùng" in all_tc_text or "đồng thời" in all_tc_text or "concurrency" in all_tc_text or "race" in all_tc_text or "idempotency" in all_tc_text
        if not has_concurrency:
            issues.append(ReviewIssue(
                target_tc_id=None,
                issue_type="Missing Concurrency/Duplicate Case",
                severity="Major",
                description="Tính năng Thanh toán / Chuyển tiền thiếu kịch bản kiểm thử gửi trùng request hoặc xử lý giao dịch đồng thời.",
                suggested_fix="Bổ sung test case gửi 2 giao dịch đồng thời hoặc lặp request để kiểm tra khả năng xử lý an toàn."
            ))
        has_timeout = "timeout" in all_tc_text or "504" in all_tc_text or "đối soát" in all_tc_text or "pending" in all_tc_text or "reconciliation" in all_tc_text
        if not has_timeout:
            issues.append(ReviewIssue(
                target_tc_id=None,
                issue_type="Missing Idempotency/Timeout Case",
                severity="Major",
                description="Tính năng Chuyển tiền thiếu kịch bản xử lý Gateway Timeout (HTTP 504 / Socket timeout) và đối soát giao dịch treo.",
                suggested_fix="Bổ sung test case giả lập Napas timeout để kiểm tra trạng thái PENDING_RECONCILIATION và phong tỏa tạm thời."
            ))
        # Kiểm tra Sinh trắc học / QĐ 2345: CHỈ áp dụng khi tài liệu yêu cầu có nêu rõ điều kiện Sinh trắc học / Biometric / QĐ 2345 (Không áp dụng cho API thuần túy)
        is_api_only = "api" in analysis.feature_name.lower() or "endpoint" in (analysis.business_overview or "").lower()
        requires_biometrics = any(
            ("sinh trắc" in f"{ac.description} {ac.title}".lower() or "biometric" in f"{ac.description} {ac.title}".lower() or "2345" in f"{ac.description} {ac.title}")
            for ac in analysis.acceptance_criteria
        )
        if not is_api_only and requires_biometrics:
            has_biometric = "sinh trắc" in all_tc_text or "biometric" in all_tc_text or "face" in all_tc_text or "2345" in all_tc_text
            if not has_biometric:
                issues.append(ReviewIssue(
                    target_tc_id=None,
                    issue_type="Banking Compliance Violation (QĐ 2345)",
                    severity="Major",
                    description="Yêu cầu có đề cập đến xác thực Sinh trắc học / QĐ 2345 nhưng bộ test case chưa bao phủ kịch bản này.",
                    suggested_fix="Bổ sung test case kiểm tra xác thực Sinh trắc học theo đúng mô tả của yêu cầu."
                ))
    # 3.2. Nếu là Tiết kiệm có tính lãi / Lãi suất (Interest Accrual): Bắt buộc có kịch bản Làm tròn / Độ chính xác số học & Tất toán trước hạn
    is_interest_accrual = (
        any(("lãi" in f"{ac.description} {ac.title}".lower() or "interest" in f"{ac.description} {ac.title}".lower() or "accrual" in f"{ac.description} {ac.title}".lower()) for ac in analysis.acceptance_criteria)
        or ("interest" in analysis.feature_name.lower() or "tính lãi" in analysis.feature_name.lower() or "lãi suất" in analysis.feature_name.lower())
    )
    if is_interest_accrual:
        has_rounding = "làm tròn" in all_tc_text or "rounding" in all_tc_text or "thập phân" in all_tc_text or "precision" in all_tc_text or "365" in all_tc_text or "366" in all_tc_text
        if not has_rounding:
            issues.append(ReviewIssue(
                target_tc_id=None,
                issue_type="Missing Boundary Case",
                severity="Major",
                description="Tính năng Tiết kiệm / Lãi suất thiếu kịch bản kiểm thử độ chính xác tính toán (Accrual precision) và quy tắc làm tròn (Banker's Rounding).",
                suggested_fix="Bổ sung test case kiểm tra tính lãi theo quy ước ngày (365 vs 366 ngày năm nhuận) và làm tròn 2 chữ số thập phân khi chi trả."
            ))

    # 4. MULTI-TECHNIQUE DIVERSITY CHECK: Đảm bảo bộ test suite có tính đa dạng kỹ thuật (Không chỉ có Happy path)
    has_bva = any(k in all_tc_text for k in ["biên", "boundary", "min", "max", "tối đa", "tối thiểu", "vượt", "0", "null"])
    if not has_bva:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Technique Under-Coverage (BVA)",
            severity="Major",
            description="Bộ Test Suite thiếu các kịch bản Phân tích Giá trị Biên (BVA: Min-1, Min, Max, Max+1, rỗng, null).",
            suggested_fix="Bổ sung kịch bản kiểm tra giá trị biên cận dưới, cận trên và trường hợp vượt giới hạn."
        ))

    has_negative_ep = any(k in all_tc_text for k in ["không thành công", "thiếu trường", "sai kiểu", "mã lỗi", "invalid", "từ chối"])
    if not has_negative_ep:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Technique Under-Coverage (Negative EP)",
            severity="Critical",
            description="Bộ Test Suite thiếu kịch bản Phân vùng Tương đương Tiêu cực (Negative Equivalence Partitioning) để kiểm tra bắt lỗi hệ thống.",
            suggested_fix="Bổ sung các test case kiểm tra thiếu trường bắt buộc, truyền sai kiểu dữ liệu, hoặc giá trị không nằm trong whitelist enum."
        ))
    return issues
