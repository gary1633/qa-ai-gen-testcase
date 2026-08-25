from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class BankingComplianceRule(BaseModel):
    rule_code: str = Field(default="QD_2345_NHNN", description="Mã quy định, ví dụ: QD_2345_NHNN, TT_39_NHNN, AML_RULE")
    rule_name: str = Field(default="Quy định Ngân hàng Nhà nước", description="Tên quy định / Thông tư nghiệp vụ Ngân hàng")
    verification_target: str = Field(default="", description="Yêu cầu kiểm thử tuân thủ bắt buộc")


class ProductRisk(BaseModel):
    risk_id: str = Field(default="RSK-01", description="Mã rủi ro, ví dụ: RSK-01, RSK-02")
    risk_title: str = Field(default="", description="Tiêu đề rủi ro ngắn gọn")
    risk_description: str = Field(default="", description="Mô tả chi tiết rủi ro tiềm ẩn")
    risk_category: Literal[
        "Financial & Ledger Risk",
        "Security & Authentication Risk",
        "Regulatory & Compliance Risk (QĐ 2345)",
        "Integration & Timeout Risk",
        "Data Integrity & Rounding Risk",
        "Account Lifecycle & Blockade Risk",
        "Business Logic Risk"
    ] = Field(default="Business Logic Risk", description="Phân loại rủi ro theo chuẩn Banking & ISTQB")
    likelihood: int = Field(default=3, ge=1, le=5, description="Khả năng xảy ra rủi ro (1: Rất thấp -> 5: Rất cao)")
    impact: int = Field(default=3, ge=1, le=5, description="Mức độ thiệt hại (1: Không đáng kể -> 5: Thảm họa tài chính / Vi phạm pháp luật)")
    risk_score: int = Field(default=9, ge=1, le=25, description="Điểm rủi ro = Likelihood x Impact (1 - 25)")
    risk_level: Literal["Critical", "High", "Medium", "Low"] = Field(default="Medium", description="Mức độ rủi ro")
    linked_ac_id: str = Field(default="AC-01", description="Mã AC hoặc tính năng bị ảnh hưởng (vd: AC-01)")
    mitigation_test_focus: str = Field(default="", description="Trọng tâm kiểm thử bắt buộc để triệt tiêu rủi ro")


class AcceptanceCriterion(BaseModel):
    ac_id: str = Field(default="AC-01", description="Mã AC, ví dụ: AC-01, AC-02")
    title: str = Field(default="", description="Tiêu đề tiêu chí nghiệm thu")
    description: str = Field(default="", description="Mô tả chi tiết tiêu chí nghiệm thu")
    business_rules: List[str] = Field(default_factory=list, description="Danh sách các quy tắc nghiệp vụ liên quan")
    risk_level: Literal["Critical", "High", "Medium", "Low"] = Field(default="Medium", description="Mức độ rủi ro")


class RequirementAnalysis(BaseModel):
    feature_name: str = Field(default="Tính năng Ngân hàng", description="Tên tính năng hoặc User Story")
    app_name: str = Field(default="Core TM", description="Tên ứng dụng kiểm tra")
    version: str = Field(default="0.0.1", description="Phiên bản kiểm tra")
    jira_or_doc_link: str = Field(default="", description="Link tài liệu hoặc Jira Ticket")
    business_overview: str = Field(default="", description="Tóm tắt nghiệp vụ và mục tiêu tính năng")

    @property
    def business_objective(self) -> str:
        return self.business_overview
    banking_domain: Literal[
        "Payments & Fund Transfers (Napas, VietQR, Swift)",
        "Savings & Term Deposits (Interest, Maturity, Accrual)",
        "Lending & Loan Amortization (Schedules, Repayments)",
        "Account Lifecycle & Blockade (Lien, Freeze, Dormant)",
        "Cards, Limits & ATM/POS",
        "Fees, Charges & VAT Invoicing",
        "Regulatory Compliance & Biometrics (QĐ 2345/QĐ-NHNN)",
        "General Core Banking Service"
    ] = Field(default="General Core Banking Service", description="Phân hệ nghiệp vụ Ngân hàng / Tài chính chuyên biệt")
    banking_invariants: List[str] = Field(
        default_factory=list, 
        description="Các bất biến kế toán/nghiệp vụ ngân hàng cần bảo toàn"
    )
    acceptance_criteria: List[AcceptanceCriterion] = Field(default_factory=list, description="Danh sách Acceptance Criteria bóc tách được")
    product_risks: List[ProductRisk] = Field(default_factory=list, description="Ma trận rủi ro sản phẩm (RBT)")
    compliance_rules: List[BankingComplianceRule] = Field(default_factory=list, description="Các quy định pháp chế và thông tư NHNN cần tuân thủ")
    needs_user_clarification: bool = Field(
        default=False, 
        description="Đánh dấu True nếu yêu cầu có những điểm mơ hồ, mâu thuẫn, thiếu thông tin quan trọng hoặc không thể hiểu rõ nghiệp vụ mà BẮT BUỘC phải hỏi lại User trước khi viết test case."
    )
    clarification_questions: List[str] = Field(
        default_factory=list, 
        description="Danh sách các câu hỏi cụ thể, rõ ràng cần User/PO/BA làm rõ trước khi tiến hành viết test case."
    )
    ambiguities_and_gaps: List[str] = Field(default_factory=list, description="Các điểm mơ hồ hoặc chưa rõ ràng trong yêu cầu")
    assumptions: List[str] = Field(default_factory=list, description="Các giả định QA đưa ra")
    edge_cases: List[str] = Field(default_factory=list, description="Các trường hợp biên hoặc ngoại lệ tiềm ẩn")
    questions_to_resolve: List[str] = Field(default_factory=list, description="Câu hỏi cần làm rõ với PO/BA/Dev")

class TestScenario(BaseModel):
    scenario_id: str = Field(default="SC_01", description="Mã kịch bản, ví dụ: SC_01, SC_02")
    trace_ac_id: str = Field(default="AC-01", description="Mã AC hoặc Requirement truy vết, ví dụ: AC-01")
    trace_risk_id: Optional[str] = Field(default=None, description="Mã rủi ro RBT gắn với kịch bản này (vd: RSK-01)")
    category: Literal[
        "Positive (Happy Path)",
        "Negative (Validation Error)",
        "Boundary (BVA)",
        "Security & Authentication (Biometric)",
        "Concurrency & Idempotency",
        "Exception & Timeout Reconciliation",
        "Accounting Invariant & Ledger Balancing",
        "Rounding & Precision Drift",
        "Lifecycle & Account State Collision"
    ] = Field(default="Positive (Happy Path)", description="Phân loại kịch bản kiểm thử Banking chuyên sâu")
    group_feature: str = Field(
        default="1. Chuyển tiền Napas 24/7 (AC-01 - Risk: High)",
        description="Tên nhóm phân cấp lớn (Row 22)"
    )
    group_functional: str = Field(
        default="1.1. Luồng giao dịch & Hạch toán",
        description="Tên nhóm phân cấp con (Row 23)"
    )
    scenario_title: str = Field(default="Kịch bản kiểm thử", description="Tiêu đề kịch bản kiểm thử rõ ràng")
    testing_technique: Literal[
        "Equivalence Partitioning", 
        "Boundary Value Analysis (BVA)", 
        "Decision Table Matrix", 
        "State Transition Testing", 
        "Error Guessing & Fault Injection",
        "Double-Entry Ledger Balancing",
        "Banker's Rounding & Precision Test",
        "Race Condition & Idempotency Testing",
        "Regulatory Compliance Audit (QĐ 2345)"
    ] = Field(default="Equivalence Partitioning", description="Kỹ thuật kiểm thử áp dụng theo chuẩn Banking ISTQB")
    test_intent: str = Field(default="", description="Ý đồ kiểm thử")
    priority: Literal["Critical", "High", "Medium", "Low"] = Field(default="High", description="Mức độ ưu tiên kiểm thử")

    @property
    def title(self) -> str:
        return self.scenario_title

class TestCase(BaseModel):
    testcase_id: str = Field(default="TC 01", description="Mã Testcase định dạng 'TC 01', 'TC 02', ...")
    group_feature: str = Field(default="1. Chuyển tiền Napas 24/7 (AC-01 - Risk: High)", description="Nhóm tính năng lớn tương ứng")
    group_functional: str = Field(default="1.1. Luồng giao dịch & Hạch toán", description="Nhóm functional con tương ứng")
    title: str = Field(default="Test case", description="Tên testcase mô tả hành động, điều kiện và rủi ro phòng ngừa")
    preconditions: str = Field(default="Tài khoản hoạt động bình thường, số dư khả dụng hợp lệ.", description="Điều kiện tiên quyết trước khi thực hiện test")
    steps: str = Field(default="1. Thực hiện gửi request\\n2. Kiểm tra phản hồi", description="Các bước thực hiện đánh số: '1. ...\\n2. ...'")
    expected_result: str = Field(default="HTTP Status 200 OK, giao dịch thành công.", description="Kết quả mong đợi chi tiết kiểm chứng được")
    actual_result: str = Field(default="", description="Kết quả thực tế (để trống)")
    test_data: str = Field(default="{}", description="Dữ liệu test cụ thể (Payload JSON, tham số, số tiền, tài khoản, idempotency_key)")
    creator: str = Field(default="QA Banking Specialist", description="Người tạo")
    test_date: str = Field(default_factory=lambda: datetime.now().strftime("%d/%m/%Y"), description="Ngày tạo/test định dạng DD/MM/YYYY")
    test_status: Literal["Not Test", "Passed", "Failed", "Blocked", "Not Executed"] = Field(
        default="Not Test", description="Trạng thái test ban đầu"
    )
    priority: Literal["Critical", "High", "Medium", "Low"] = Field(default="High", description="Mức độ ưu tiên")
    plan_execution: str = Field(default="Sprint Release", description="Kế hoạch thực thi")
    executed_date: str = Field(default="", description="Ngày thực thi (để trống)")
    note: str = Field(default="", description="Ghi chú, Trace ID, Risk ID, Jira Link")

    @property
    def scenario_title(self) -> str:
        return self.title

class ReviewIssue(BaseModel):
    target_tc_id: Optional[str] = Field(default=None, description="Mã test case bị lỗi (nếu có)")
    issue_type: str = Field(default="Format Violation", description="Loại lỗi phát hiện (Ambiguous Step, Missing Boundary Case, Missing Negative Case, RBT Under-Coverage Violation, etc.)")
    severity: Literal["Critical", "Major", "Minor"] = Field(default="Minor", description="Mức độ nghiêm trọng")
    description: str = Field(default="", description="Mô tả cụ thể lỗi phát hiện")
    suggested_fix: str = Field(default="", description="Hướng dẫn sửa lỗi cụ thể cho Generator Agent")

class TraceabilityItem(BaseModel):
    ac_id: str = Field(default="AC-01", description="Mã Acceptance Criterion")
    ac_title: str = Field(default="", description="Tiêu đề tiêu chí chấp nhận")
    risk_level: str = Field(default="High", description="Mức độ rủi ro (Critical, High, Medium, Low)")
    covered_test_cases: List[str] = Field(default_factory=list, description="Danh sách các mã Test Case bao phủ (TC 01, TC 02...)")
    coverage_status: Literal["COVERED", "PARTIAL", "MISSING"] = Field(default="COVERED", description="Trạng thái bao phủ")
    coverage_notes: str = Field(default="", description="Ghi chú chi tiết góc độ đã kiểm thử (Positive, Negative, Boundary, Idempotency...)")


class ReviewResult(BaseModel):
    passed: bool = Field(default=True, description="Đạt hay không đạt ngưỡng QA Quality Gate")
    score: int = Field(default=90, description="Điểm chất lượng từ 0 - 100")
    total_cases_reviewed: int = Field(default=0, description="Tổng số test case được review")
    traceability_matrix: List[TraceabilityItem] = Field(default_factory=list, description="Ma trận truy vết 2 chiều giữa ACs và Test Cases")
    issues: List[ReviewIssue] = Field(default_factory=list, description="Danh sách các lỗi cần khắc phục")
    feedback_summary: str = Field(default="Bộ test case đạt chuẩn chất lượng.", description="Nhận xét tổng quan và báo cáo Traceability Matrix")
