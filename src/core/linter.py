import re
from typing import Callable, Dict, List, NamedTuple
from src.core.models import RequirementAnalysis, ReviewIssue, TestCase, TestScenario
from src.core.llm import load_qa_rules
from src.core.prompt_loader import resolve_domain_pack

_QA_RULES = load_qa_rules()

_HARDCODED_BANNED_PHRASES = (
    # English
    "verify it works", "looks right", "wait a bit", "some valid data", "some data",
    "check if ok", "see if it works", "normal flow", "proper result", "appropriate message",
    # Vietnamese (Những từ cấm gây mơ hồ trong Steps và Expected Result)
    "kiểm tra xem có hoạt động không", "thấy đúng", "chờ một chút",
    "nhập dữ liệu bất kỳ", "nhập thông tin hợp lệ", "kết quả phù hợp", "thông báo tương ứng",
    "kiểm tra ok", "thành công như mong đợi", "xử lý đúng đắn",
)

BANNED_PHRASES = sorted({p.lower() for p in set(_HARDCODED_BANNED_PHRASES) | set(_QA_RULES["banned_vague_words"])})

BOUNDARY_REGEX = re.compile(
    r"(\bmin\b|\bmax\b|\bbiên\b|\bboundary\b|\bnull\b|\brỗng\b|\bempty\b|"
    r"tối đa|tối thiểu|\bvượt\b|quá giới hạn|max\s*[+\-]\s*1|min\s*[+\-]\s*1|"
    r"maxlength|precision|\bâm\b|\bnegative\b)",
    re.IGNORECASE,
)

ASSERTION_REGEX = re.compile(
    r"(\b[1-5]\d{2}\b|\bhttp\b|status|mã lỗi|error[_ ]?code|\b[A-Z]{2,}_\d+\b|"
    r"\bschema\b|\{|\d[\d.,]*\s*(vnd|đ|usd|%)|\bstate\b|trạng thái)",
    re.IGNORECASE,
)

QUOTED_TEXT_REGEX = re.compile(r"[\"“]([^\"”\n]{12,200})[\"”]")
MESSAGE_CUE_REGEX = re.compile(r"(message|msg|thông\s+báo|nội\s+dung\s+thông\s+báo)\W{0,20}$", re.IGNORECASE)

TECHNIQUE_NAME_PATTERNS = ("bva", "boundary value analysis", "equivalence partitioning", "ep", "decision table", "state transition", "pairwise", "business flow", "end-to-end impact")

AC_ID_REGEX = re.compile(r"\bAC-\d+\b", re.IGNORECASE)

# Mã lỗi nghiệp vụ dạng "CV_051", "ERR_2345" (chữ hoa + underscore + số) đi kèm cue "Mã lỗi"/"Error code"
# ngay trước đó trong tài liệu gốc -> đây là các nguyên nhân từ chối RIÊNG BIỆT bắt buộc mỗi mã phải có
# ít nhất 1 Test Case Negative assert tới, KHÔNG được gộp chung/bỏ sót khi tài liệu liệt kê tường minh.
ERROR_CODE_REGEX = re.compile(r"\b[A-Z]{2,6}_\d{3,6}\b")
ERROR_CODE_CUE_REGEX = re.compile(r"(mã\s*lỗi|error\s*code|error\s*:)", re.IGNORECASE)


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

    # 2. Kiểm tra độ chi tiết & tính kiểm chứng được của Expected Result (Non-deterministic)
    expected_result = tc.expected_result.strip()
    if len(expected_result) < 15:
        issues.append(ReviewIssue(
            target_tc_id=tc.testcase_id,
            issue_type="Non-Deterministic Expected Result",
            severity="Critical",
            description="Kết quả mong đợi quá ngắn hoặc không có tiêu chí kiểm chứng rõ ràng.",
            suggested_fix="Mô tả cụ thể HTTP status, JSON body, mã lỗi, hoặc biến động số dư tài khoản."
        ))
    elif _QA_RULES["strict_assertion_required"] and not ASSERTION_REGEX.search(expected_result):
        issues.append(ReviewIssue(
            target_tc_id=tc.testcase_id,
            issue_type="Non-Deterministic Expected Result",
            severity="Major",
            description="Kết quả mong đợi không chứa tiêu chí kiểm chứng định lượng (HTTP status, mã lỗi, schema, số tiền, trạng thái).",
            suggested_fix="Bổ sung mã HTTP status, mã lỗi nghiệp vụ, cấu trúc JSON response hoặc số liệu cụ thể có thể kiểm chứng."
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


def _duplicate_test_case_issues(test_cases: List[TestCase]) -> List[ReviewIssue]:
    """4d. Phát hiện các Test Case trùng lặp về tiêu đề và test data (suite-level check)."""
    groups: Dict[str, List[str]] = {}
    for tc in test_cases:
        key = re.sub(r"\W+", " ", f"{tc.title} {tc.test_data}".lower()).strip()
        groups.setdefault(key, []).append(tc.testcase_id)

    issues: List[ReviewIssue] = []
    for ids in groups.values():
        if len(ids) > 1:
            issues.append(ReviewIssue(
                target_tc_id=None,
                issue_type="Duplicate Test Case",
                severity="Major",
                description=f"Các test case sau trùng lặp về tiêu đề và test data: {', '.join(ids)}",
                suggested_fix="Hợp nhất hoặc thay đổi rõ tiêu chí kiểm thử để mỗi test case bao phủ một trường hợp riêng biệt."
            ))
    return issues


class GatedRule(NamedTuple):
    """Quy tắc domain chỉ kích hoạt khi nội dung in-scope của yêu cầu khớp `trigger`; đạt khi test suite khớp `evidence`."""
    issue_type: str
    trigger: "re.Pattern[str]"
    evidence: "re.Pattern[str]"
    description: str
    suggested_fix: str
    severity: str = "Major"


def _rx(pattern: str) -> "re.Pattern[str]":
    return re.compile(pattern, re.IGNORECASE)


# Mỗi rule gắn với một module sản phẩm (prompts/domains/banking/<module>.md) và CHỈ áp dụng khi
# feature/tổng quan/AC có nhắc tới chủ đề đó — không gán ép kỹ thuật cho tính năng không liên quan.
BANKING_RULES: List[GatedRule] = [
    GatedRule(
        "Missing Concurrency/Duplicate Case",
        _rx(r"chuyển tiền|chuyển khoản|thanh toán|rút tiền|trừ tiền|ghi nợ tài khoản|giải ngân|thu nợ|trả nợ|tất toán"
            r"|hoàn tiền|\brefund|\btransfer|\bwithdraw|\bpayment|\bdisburse|phong tỏa|phong toả|tạm giữ"),
        _rx(r"trùng(?!\s*khớp)|(gửi|thực hiện|xử lý|phát sinh)\s+(\S+\s+){0,4}đồng thời|đồng thời\s+\d|cùng (một |1 )?thời điểm"
            r"|song song|concurren|race condition|\brace\b|idempotency|duplicate"),
        "Tính năng làm biến động số dư/dư nợ thiếu kịch bản gửi trùng request hoặc 2 giao dịch đồng thời trên cùng tài khoản.",
        "Bổ sung test case gửi 2 giao dịch đồng thời khi số dư chỉ đủ cho 1 (hoặc gửi lặp request) và kiểm tra số dư/sổ cái không bị trừ 2 lần.",
    ),
    GatedRule(
        "Missing Gateway Timeout/Reconciliation Case",
        _rx(r"napas|citad|swift|vietqr|gateway|cổng thanh toán|đối tác|\bpartner|bên thứ (3|ba)|third[- ]party"
            r"|tổ chức thẻ|\bvisa\b|mastercard|\bjcb\b|liên ngân hàng"),
        _rx(r"timeout|time-out|\b504\b|đối soát|reconciliation|\bpending(?!\s+clarification)|treo|hết thời gian chờ"),
        "Tính năng có gọi hệ thống đối tác/gateway nhưng thiếu kịch bản đối tác timeout (HTTP 504/socket timeout) và đối soát giao dịch treo.",
        "Bổ sung test case giả lập đối tác timeout để kiểm tra trạng thái chờ đối soát (vd PENDING_RECONCILIATION), không trừ tiền 2 lần và không mất tiền.",
    ),
    GatedRule(
        "Banking Compliance Violation (QĐ 2345)",
        _rx(r"sinh trắc|biometric|2345"),
        _rx(r"sinh trắc|biometric|khuôn mặt|\bface\b|2345"),
        "Yêu cầu có đề cập đến xác thực Sinh trắc học / QĐ 2345 nhưng bộ test case chưa bao phủ kịch bản này.",
        "Bổ sung test case kiểm tra xác thực Sinh trắc học theo đúng ngưỡng/điều kiện của yêu cầu (dưới ngưỡng, chạm ngưỡng, vượt ngưỡng, xác thực thất bại).",
    ),
    GatedRule(
        "Missing Transaction Limit Boundary Case",
        _rx(r"hạn mức giao dịch|hạn mức ngày|hạn mức tháng|hạn mức chuyển|daily limit|transaction limit|hạn mức lũy kế|hạn mức luỹ kế"),
        _rx(r"vượt hạn mức|chạm hạn mức|vừa đủ hạn mức|hạn mức còn lại|lũy kế|luỹ kế|exceed|max\s*[+\-]\s*1|tối đa"),
        "Yêu cầu có hạn mức giao dịch nhưng bộ test case thiếu kịch bản biên hạn mức (vừa chạm, vượt 1 đơn vị, lũy kế trong ngày).",
        "Bổ sung test case giao dịch đúng bằng hạn mức, vượt hạn mức 1 VND và giao dịch thứ N làm lũy kế vượt hạn mức ngày.",
    ),
    GatedRule(
        "Missing Ledger Posting Verification",
        _rx(r"hạch toán|bút toán|sổ cái|\bledger|\bgl\b|posting"),
        _rx(r"nợ\s*/\s*có|ghi nợ[^.\n]{0,80}ghi có|\bdebit\b[^.\n]{0,80}\bcredit\b|cân bằng|balanced|tài khoản gl|gl account"),
        "Yêu cầu có hạch toán/bút toán nhưng không test case nào kiểm tra cặp bút toán Nợ/Có cân bằng.",
        "Bổ sung bước kiểm tra bút toán Nợ/Có (tài khoản, số tiền) cân bằng sau giao dịch và bút toán đảo khi giao dịch thất bại.",
    ),
    GatedRule(
        "Missing Repayment Allocation Case",
        _rx(r"thu nợ|trả nợ|thu hồi nợ|debt collection|repayment"),
        _rx(r"không đủ|một phần|partial|insufficient|thiếu số dư"),
        "Yêu cầu có thu nợ/trả nợ nhưng thiếu kịch bản số tiền thu được không đủ để phân bổ hết các cấu phần (phí, lãi phạt, lãi, gốc).",
        "Bổ sung bảng quyết định thứ tự phân bổ thu nợ theo tài liệu và test case số dư chỉ đủ một phần cấu phần; ghi rõ số còn lại của từng cấu phần.",
    ),
    GatedRule(
        "Missing Overdue/Debt-Group Boundary Case",
        _rx(r"nhóm nợ|chuyển nhóm|phân loại nợ|debt group|\bdpd\b|days past due"),
        _rx(r"nhóm\s*[1-5]|\bdpd\b|ngày quá hạn|\d+\s*ngày"),
        "Yêu cầu có phân loại/chuyển nhóm nợ nhưng thiếu kịch bản biên số ngày quá hạn tại các ngưỡng chuyển nhóm.",
        "Bổ sung test case tại ngưỡng-1, ngưỡng, ngưỡng+1 số ngày quá hạn cho từng lần chuyển nhóm nợ nêu trong tài liệu.",
    ),
    GatedRule(
        "Missing Overdraft Limit Boundary Case",
        _rx(r"thấu chi|overdraft|\bod\b"),
        _rx(r"vượt hạn mức|hết hạn mức|over[- ]?limit|hạn mức còn lại|hạn mức (đã )?(dùng|sử dụng)|giảm hạn mức|hết hiệu lực|hết hạn"),
        "Yêu cầu liên quan tới thấu chi nhưng thiếu kịch bản biên hạn mức OD (dùng hết hạn mức, vượt hạn mức, hạn mức hết hiệu lực).",
        "Bổ sung test case giao dịch dùng vừa hết hạn mức OD, vượt hạn mức 1 VND và giao dịch sau khi hạn mức hết hiệu lực/bị giảm.",
    ),
    GatedRule(
        "Missing PIN Retry/Lock Case",
        _rx(r"\bpin\b"),
        _rx(r"sai pin|pin sai|nhập sai|wrong pin|incorrect pin|khóa|khoá|\block"),
        "Yêu cầu có xác thực PIN nhưng thiếu kịch bản nhập sai PIN liên tiếp tới ngưỡng khóa.",
        "Bổ sung test case nhập sai PIN N-1 lần (chưa khóa), N lần (khóa) và nhập đúng sau khi đã khóa (vẫn bị từ chối), với N theo tài liệu.",
    ),
    GatedRule(
        "Missing Card Data Masking Case",
        _rx(r"số thẻ|card number|\bpan\b|\bcvv|\bcvc"),
        _rx(r"\bche\b|\bmask|\*{4}|x{4}|4 số cuối|6 số đầu|first 6|last 4"),
        "Yêu cầu có hiển thị/xử lý số thẻ nhưng thiếu kịch bản kiểm tra che (mask) PAN và không lưu/hiển thị CVV.",
        "Bổ sung test case kiểm tra PAN chỉ hiển thị theo định dạng che mà tài liệu quy định trên UI/log/response và CVV không xuất hiện ở bất kỳ đâu.",
        "Critical",
    ),
    GatedRule(
        "Missing Authorization Reversal/Expiry Case",
        _rx(r"cấp phép|authori[sz]ation|pre-auth|tạm giữ|\bhold\b"),
        _rx(r"reversal|hủy cấp phép|huỷ cấp phép|release|giải tỏa|giải toả|hết hạn cấp phép|tự động giải|\bđảo\b"),
        "Yêu cầu có cấp phép/tạm giữ tiền nhưng thiếu kịch bản hủy cấp phép (reversal) hoặc cấp phép hết hạn được giải tỏa.",
        "Bổ sung test case reversal toàn phần/một phần và cấp phép quá hạn không được quyết toán thì số tiền tạm giữ được giải tỏa đúng.",
    ),
    GatedRule(
        "Missing Early-Withdrawal Interest Case",
        _rx(r"rút trước hạn|tất toán trước hạn|early withdrawal|premature"),
        _rx(r"không kỳ hạn|demand rate|lãi suất (rút )?trước hạn"),
        "Yêu cầu có rút/tất toán trước hạn nhưng thiếu kịch bản kiểm tra lãi suất áp dụng khi rút trước hạn.",
        "Bổ sung test case tất toán trước hạn và kiểm tra số tiền lãi theo đúng lãi suất trước hạn/không kỳ hạn mà tài liệu quy định.",
    ),
    GatedRule(
        "Missing Maturity Date Boundary Case",
        _rx(r"đáo hạn|tái tục|rollover|maturity"),
        _rx(r"(trước|đúng|sau) ngày đáo hạn|ngày nghỉ|ngày lễ|holiday|cuối tuần"),
        "Yêu cầu có đáo hạn/tái tục nhưng thiếu kịch bản biên ngày đáo hạn (trước/đúng/sau ngày đáo hạn, đáo hạn rơi vào ngày nghỉ).",
        "Bổ sung test case giao dịch trước, đúng và sau ngày đáo hạn; và trường hợp ngày đáo hạn rơi vào ngày nghỉ/lễ nếu tài liệu có quy tắc.",
    ),
]


def _gated_rule_issues(rules: List[GatedRule], scope_text: str, all_tc_text: str) -> List[ReviewIssue]:
    return [
        ReviewIssue(target_tc_id=None, issue_type=rule.issue_type, severity=rule.severity,
                    description=rule.description, suggested_fix=rule.suggested_fix)
        for rule in rules
        if rule.trigger.search(scope_text) and not rule.evidence.search(all_tc_text)
    ]


def _fintech_banking_rules(analysis: RequirementAnalysis, all_tc_text: str) -> List[ReviewIssue]:
    return _gated_rule_issues(BANKING_RULES, analysis.scope_text, all_tc_text)


def _ecommerce_retail_rules(analysis: RequirementAnalysis, all_tc_text: str) -> List[ReviewIssue]:
    issues: List[ReviewIssue] = []
    has_inventory_check = any(k in all_tc_text for k in ["tồn kho", "hết hàng", "out of stock", "inventory", "số lượng", "quantity", "flash sale", "đồng thời"])
    if not has_inventory_check and any("tồn kho" in f"{ac.description} {ac.title}".lower() or "đặt hàng" in f"{ac.description} {ac.title}".lower() for ac in analysis.acceptance_criteria):
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Missing Inventory/Stock Boundary Case",
            severity="Major",
            description="Tính năng E-Commerce/Bán hàng thiếu kịch bản kiểm thử giới hạn tồn kho (cháy hàng, đặt vượt số lượng tồn kho).",
            suggested_fix="Bổ sung test case kiểm tra đặt hàng khi tồn kho = 0 hoặc nhiều người cùng tranh mua sản phẩm cuối cùng."
        ))
    return issues


def _healthcare_rules(analysis: RequirementAnalysis, all_tc_text: str) -> List[ReviewIssue]:
    issues: List[ReviewIssue] = []
    phi_trigger = _rx(r"bệnh án|patient|\bphi\b|hồ sơ|bệnh nhân")
    ac_mentions_phi = any(phi_trigger.search(f"{ac.description} {ac.title}") for ac in analysis.acceptance_criteria)
    has_access_control = any(k in all_tc_text for k in ["phân quyền", "rbac", "403", "consent", "audit"])
    if ac_mentions_phi and not has_access_control:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Missing PHI Access-Control Case",
            severity="Critical",
            description="Yêu cầu liên quan đến hồ sơ bệnh án / dữ liệu bệnh nhân (PHI) nhưng bộ test case chưa bao phủ kịch bản phân quyền/audit truy cập.",
            suggested_fix="Bổ sung test case kiểm tra phân quyền RBAC, từ chối 403 khi ngoài mối quan hệ chăm sóc, và ghi Audit Log khi truy cập PHI."
        ))
    return issues


def _logistics_supplychain_rules(analysis: RequirementAnalysis, all_tc_text: str) -> List[ReviewIssue]:
    issues: List[ReviewIssue] = []
    ac_mentions_status = any(
        any(k in f"{ac.description} {ac.title}".lower() for k in ["trạng thái", "status", "tracking"])
        for ac in analysis.acceptance_criteria
    )
    has_invalid_transition = any(k in all_tc_text for k in ["không hợp lệ", "invalid", "lùi trạng thái", "backward", "sai thứ tự"])
    if ac_mentions_status and not has_invalid_transition:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Missing State Transition Case",
            severity="Major",
            description="Tính năng theo dõi trạng thái vận chuyển thiếu kịch bản kiểm thử chuyển trạng thái bất hợp lệ / lùi trạng thái.",
            suggested_fix="Bổ sung test case thử chuyển trạng thái ngược (vd: DELIVERED -> IN_TRANSIT) để xác nhận hệ thống từ chối."
        ))
    return issues


def _saas_b2b_rules(analysis: RequirementAnalysis, all_tc_text: str) -> List[ReviewIssue]:
    issues: List[ReviewIssue] = []
    ac_mentions_tenant = any(
        any(k in f"{ac.description} {ac.title}".lower() for k in ["tenant", "workspace", "subscription", "seat"])
        for ac in analysis.acceptance_criteria
    )
    has_isolation_check = any(k in all_tc_text for k in ["tenant", "cross-tenant", "403", "isolation", "cách ly"])
    if ac_mentions_tenant and not has_isolation_check:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Missing Tenant Isolation Case",
            severity="Critical",
            description="Yêu cầu liên quan đến tenant/workspace nhưng bộ test case chưa bao phủ kịch bản cách ly dữ liệu giữa các tenant.",
            suggested_fix="Bổ sung test case xác nhận Tenant A không thể đọc/ghi dữ liệu của Tenant B (trả về 403)."
        ))
    return issues


def _api_platform_rules(analysis: RequirementAnalysis, all_tc_text: str) -> List[ReviewIssue]:
    issues: List[ReviewIssue] = []
    ac_mentions_endpoint = any(
        any(k in f"{ac.description} {ac.title}".lower() for k in ["endpoint", "api", "get ", "post ", "put ", "patch ", "delete "])
        for ac in analysis.acceptance_criteria
    ) or any(k in (analysis.business_overview or "").lower() for k in ["endpoint", "api"])
    has_auth_negative = any(k in all_tc_text for k in ["401", "403", "token", "unauthorized"])
    if ac_mentions_endpoint and not has_auth_negative:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Missing Auth Negative Case",
            severity="Major",
            description="Tính năng API thiếu kịch bản kiểm thử phủ định về xác thực/phân quyền (401/403).",
            suggested_fix="Bổ sung test case gọi API không kèm token (401) và với token không đủ quyền (403)."
        ))
    return issues


DOMAIN_RULES: Dict[str, Callable[[RequirementAnalysis, str], List[ReviewIssue]]] = {
    "fintech-banking": _fintech_banking_rules,
    "ecommerce-retail": _ecommerce_retail_rules,
    "healthcare": _healthcare_rules,
    "logistics-supplychain": _logistics_supplychain_rules,
    "saas-b2b": _saas_b2b_rules,
    "api-platform": _api_platform_rules,
}


def _normalize_for_grounding(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").casefold().strip()


def _fabricated_message_issues(analysis: RequirementAnalysis, test_cases: List[TestCase], raw_content: str) -> List[ReviewIssue]:
    """Phát hiện câu message được assert nhưng KHÔNG hề tồn tại trong tài liệu gốc / bài phân tích."""
    if not raw_content:
        return []
    corpus_parts = [raw_content, analysis.business_overview or ""]
    for ac in analysis.acceptance_criteria:
        corpus_parts.extend([ac.title, ac.description, *ac.business_rules])
    corpus = _normalize_for_grounding(" ".join(corpus_parts))

    issues: List[ReviewIssue] = []
    for tc in test_cases:
        expected = tc.expected_result or ""
        for m in QUOTED_TEXT_REGEX.finditer(expected):
            candidate = m.group(1).strip()
            if len(candidate.split()) < 3:
                continue
            if not MESSAGE_CUE_REGEX.search(expected[:m.start()][-60:]):
                continue
            if _normalize_for_grounding(candidate) in corpus:
                continue
            issues.append(ReviewIssue(
                target_tc_id=tc.testcase_id,
                issue_type="Fabricated Message / Ungrounded Value",
                severity="Critical",
                description=f"Test Case '{tc.testcase_id}' assert câu thông báo không hề có trong tài liệu gốc hay bài phân tích: \"{candidate[:120]}\".",
                suggested_fix="Chỉ assert message/mã lỗi có thật trong tài liệu; nếu tài liệu chưa quy định, nêu câu hỏi làm rõ cho User thay vì tự bịa câu chữ."
            ))
    return issues

def _enumerated_error_code_issues(all_tc_text: str, raw_content: str) -> List[ReviewIssue]:
    """
    Phát hiện các mã lỗi nghiệp vụ được tài liệu gốc liệt kê TƯỜNG MINH (đi kèm cue "Mã lỗi"/"Error code")
    nhưng KHÔNG hề được bất kỳ Test Case nào assert tới. Đây là lỗ hổng bao phủ ở mức macro (AC đã có Test
    Case) nhưng thiếu ở mức vi mô (một trong nhiều nguyên nhân từ chối riêng biệt của chính AC đó bị bỏ sót
    khi Generator chỉ lấy mẫu một phần danh sách liệt kê thay vì sinh đủ cho TỪNG mã).
    """
    if not raw_content:
        return []
    documented_codes = set()
    for m in ERROR_CODE_REGEX.finditer(raw_content):
        cue_window = raw_content[max(0, m.start() - 60):m.start()]
        if ERROR_CODE_CUE_REGEX.search(cue_window):
            documented_codes.add(m.group(0).upper())

    missing_codes = {c for c in documented_codes if c.lower() not in all_tc_text}
    if not missing_codes:
        return []
    return [ReviewIssue(
        target_tc_id=None,
        issue_type="Enumeration Under-Coverage (Missing Error Code)",
        severity="Critical",
        description=f"Tài liệu gốc liệt kê rõ (các) mã lỗi/nguyên nhân từ chối riêng biệt sau nhưng KHÔNG có Test Case nào assert tới: {', '.join(sorted(missing_codes))}.",
        suggested_fix="Bổ sung 1 Test Case Negative RIÊNG BIỆT cho MỖI mã lỗi còn thiếu ở trên (tài liệu yêu cầu tách biệt theo từng nguyên nhân, không được gộp chung hay bỏ sót)."
    )]



def lint_test_suite_coverage(analysis: RequirementAnalysis, test_cases: List[TestCase], *, raw_content: str = "") -> List[ReviewIssue]:
    """
    Kiểm tra độ bao phủ yêu cầu (Traceability & RBT Coverage) và tiêu chuẩn chuyên sâu theo từng Domain.
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

    # 1b. Phantom AC Reference (Scope Drift Guard): Test Case trỏ tới mã AC không tồn tại trong bài phân tích
    ac_ids_upper = {a.upper() for a in ac_ids_in_analysis}
    for tc in test_cases:
        referenced_ac_ids = {m.group(0).upper() for m in AC_ID_REGEX.finditer(f"{tc.title} {tc.group_feature} {tc.note}")}
        phantom_ac_ids = referenced_ac_ids - ac_ids_upper
        if phantom_ac_ids:
            issues.append(ReviewIssue(
                target_tc_id=tc.testcase_id,
                issue_type="Scope Drift / Phantom AC Reference",
                severity="Critical",
                description=f"Test Case '{tc.testcase_id}' trỏ tới Acceptance Criteria không tồn tại trong bài phân tích: {', '.join(sorted(phantom_ac_ids))}.",
                suggested_fix="Sửa lại mã AC trong title/group_feature/note cho khớp đúng AC đã bóc tách, hoặc xóa Test Case này nếu nó thuộc tính năng ngoài phạm vi yêu cầu (Scope Drift)."
            ))

    # 2. Kiểm tra RBT Risk Coverage: Rủi ro Critical / High bắt buộc phải có test case gắn đúng mã risk_id
    high_critical_risks = [r for r in analysis.product_risks if r.risk_level in ["Critical", "High"]]
    for risk in high_critical_risks:
        risk_covered = any(risk.risk_id in f"{tc.note} {tc.title}" for tc in test_cases)
        if not risk_covered:
            issues.append(ReviewIssue(
                target_tc_id=None,
                issue_type="RBT Under-Coverage Violation",
                severity="Critical",
                description=f"Rủi ro mức {risk.risk_level} [{risk.risk_id}]: '{risk.risk_title}' (Category: {risk.risk_category}) chưa được bao phủ bởi kịch bản kiểm thử.",
                suggested_fix=f"Bổ sung kịch bản kiểm thử trực diện để triệt tiêu rủi ro này: {risk.mitigation_test_focus}"
            ))

    # 3. Duplicate Test Case (suite-level)
    issues.extend(_duplicate_test_case_issues(test_cases))
    issues.extend(_fabricated_message_issues(analysis, test_cases, raw_content))

    # 4. DOMAIN-ADAPTIVE LINTER RULES (Áp dụng đúng bộ quy tắc theo Domain Pack đã nhận diện)
    all_tc_text = " ".join([f"{tc.title} {tc.steps} {tc.expected_result} {tc.test_data}" for tc in test_cases]).lower()
    pack = resolve_domain_pack(analysis.banking_domain, analysis.feature_name)
    issues.extend(DOMAIN_RULES[pack](analysis, all_tc_text))
    issues.extend(_enumerated_error_code_issues(all_tc_text, raw_content))

    # 5. MULTI-TECHNIQUE DIVERSITY CHECK: Đảm bảo bộ test suite có tính đa dạng kỹ thuật (Không chỉ có Happy path)
    has_bva = bool(BOUNDARY_REGEX.search(all_tc_text))
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


def lint_scenarios(analysis: RequirementAnalysis, scenarios: List[TestScenario]) -> List[ReviewIssue]:
    """
    Kiểm tra chất lượng và độ bao phủ của lớp Scenario trước khi sinh Test Case (Deterministic Linter).
    """
    issues: List[ReviewIssue] = []
    if not scenarios:
        return issues

    ac_ids_in_analysis = {ac.ac_id for ac in analysis.acceptance_criteria}

    # 1. Traceability Gap: scenario trỏ tới AC không tồn tại, hoặc AC không có scenario nào bao phủ
    scenario_ac_ids = {sc.trace_ac_id for sc in scenarios if sc.trace_ac_id}
    phantom_ac_ids = scenario_ac_ids - ac_ids_in_analysis
    if phantom_ac_ids:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Traceability Gap",
            severity="Critical",
            description=f"Các kịch bản trỏ tới Acceptance Criteria không tồn tại trong bài phân tích: {', '.join(sorted(phantom_ac_ids))}",
            suggested_fix="Sửa lại trace_ac_id của các kịch bản này để khớp đúng mã AC đã được bóc tách."
        ))
    missing_ac_ids = ac_ids_in_analysis - scenario_ac_ids
    if missing_ac_ids:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Traceability Gap",
            severity="Critical",
            description=f"Các Acceptance Criteria sau chưa có kịch bản kiểm thử nào bao phủ: {', '.join(sorted(missing_ac_ids))}",
            suggested_fix="Bổ sung ít nhất 1 kịch bản Positive và 1 kịch bản Negative cho từng AC còn thiếu."
        ))

    # 2. Technique Under-Coverage: Bắt buộc phải có EP và BVA
    techniques = {sc.testing_technique for sc in scenarios if sc.testing_technique}
    technique_text = " ".join(techniques).lower()
    if "equivalence partitioning" not in technique_text:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Technique Under-Coverage",
            severity="Major",
            description="Ma trận kịch bản thiếu kỹ thuật Equivalence Partitioning bắt buộc theo prompts/02.",
            suggested_fix="Bổ sung kịch bản gán testing_technique = 'Equivalence Partitioning'."
        ))
    if "boundary value analysis" not in technique_text:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Technique Under-Coverage",
            severity="Major",
            description="Ma trận kịch bản thiếu kỹ thuật Boundary Value Analysis bắt buộc theo prompts/02.",
            suggested_fix="Bổ sung kịch bản gán testing_technique = 'Boundary Value Analysis'."
        ))
    if "business flow" not in technique_text and "end-to-end impact" not in technique_text:
        issues.append(ReviewIssue(
            target_tc_id=None,
            issue_type="Technique Under-Coverage (Business Flow)",
            severity="Major",
            description="Ma trận kịch bản chỉ dừng ở validate API/schema, thiếu kỹ thuật Business Flow / End-to-End Impact bắt buộc theo prompts/02 (kiểm tra tác động và kết quả nghiệp vụ thực tế sau hành động, không chỉ response kỹ thuật).",
            suggested_fix="Bổ sung ít nhất 1 kịch bản gán testing_technique = 'Business Flow / End-to-End Impact', kiểm tra trạng thái/số liệu nghiệp vụ thực tế (số dư, sổ cái, tồn kho, vòng đời đối tượng...) và hệ quả tới các góc nhìn liên quan có căn cứ trong tài liệu."
        ))

    # 3. Format Violation: Tên kỹ thuật hàn lâm bị lộ vào group_functional / scenario_title
    for sc in scenarios:
        leak_text = f"{sc.group_functional} {sc.scenario_title}".lower()
        if any(pat in leak_text for pat in TECHNIQUE_NAME_PATTERNS):
            issues.append(ReviewIssue(
                target_tc_id=None,
                issue_type="Format Violation",
                severity="Minor",
                description=f"Kịch bản '{sc.scenario_id}' để lộ tên kỹ thuật hàn lâm vào group_functional/scenario_title.",
                suggested_fix="Viết lại group_functional/scenario_title bằng văn phong nghiệp vụ, không nhắc tên kỹ thuật kiểm thử."
            ))

    # 4. RBT Under-Coverage Violation: Rủi ro Critical/High phải có ít nhất 1 scenario trace tới
    scenario_risk_ids = {sc.trace_risk_id for sc in scenarios if sc.trace_risk_id}
    for risk in analysis.product_risks:
        if risk.risk_level in ["Critical", "High"] and risk.risk_id not in scenario_risk_ids:
            issues.append(ReviewIssue(
                target_tc_id=None,
                issue_type="RBT Under-Coverage Violation",
                severity="Critical",
                description=f"Rủi ro mức {risk.risk_level} [{risk.risk_id}]: '{risk.risk_title}' chưa có kịch bản nào trace_risk_id trỏ tới.",
                suggested_fix=f"Bổ sung kịch bản kiểm thử trực diện để triệt tiêu rủi ro này: {risk.mitigation_test_focus}"
            ))

    return issues
