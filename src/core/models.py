from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ComplianceRule(BaseModel):
    rule_code: str = Field(default="GENERAL_COMPLIANCE", description="Mã quy định / chuẩn tuân thủ (vd: QD_2345_NHNN, GDPR, HIPAA, PCI_DSS, ISO_27001)")
    rule_name: str = Field(default="Quy định tuân thủ tiêu chuẩn", description="Tên quy định / Tiêu chuẩn nghiệp vụ chuyên ngành")
    verification_target: str = Field(default="", description="Yêu cầu kiểm thử tuân thủ bắt buộc")

BankingComplianceRule = ComplianceRule


class ProductRisk(BaseModel):
    risk_id: str = Field(default="RSK-01", description="Mã rủi ro, ví dụ: RSK-01, RSK-02")
    risk_title: str = Field(default="", description="Tiêu đề rủi ro ngắn gọn")
    risk_description: str = Field(default="", description="Mô tả chi tiết rủi ro tiềm ẩn")
    risk_category: str = Field(
        default="Business Logic Risk", 
        description="Phân loại rủi ro theo chuẩn ISTQB & Domain (Data Integrity, Security, Concurrency, Performance, Integration, Compliance, Business Logic)"
    )
    likelihood: int = Field(default=3, ge=1, le=5, description="Khả năng xảy ra rủi ro (1: Rất thấp -> 5: Rất cao)")
    impact: int = Field(default=3, ge=1, le=5, description="Mức độ thiệt hại (1: Không đáng kể -> 5: Thảm họa)")
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
    feature_name: str = Field(default="Tính năng cần kiểm thử", description="Tên tính năng hoặc User Story")
    app_name: str = Field(default="Ứng dụng cần kiểm thử", description="Tên ứng dụng kiểm tra")
    version: str = Field(default="0.0.1", description="Phiên bản kiểm tra")
    jira_or_doc_link: str = Field(default="", description="Link tài liệu hoặc Jira Ticket")
    business_overview: str = Field(default="", description="Tóm tắt nghiệp vụ và mục tiêu tính năng")

    @property
    def business_objective(self) -> str:
        return self.business_overview
    banking_domain: str = Field(
        default="General Software & API Service", 
        description="Phân hệ / Lĩnh vực nghiệp vụ (E-Commerce, FinTech & Banking, Logistics & Delivery, Healthcare, SaaS & Enterprise, EdTech, Media/Social, etc.)"
    )
    banking_invariants: List[str] = Field(
        default_factory=list, 
        description="Các bất biến nghiệp vụ cốt lõi của domain cần bảo toàn tuyệt đối"
    )

    @property
    def business_domain(self) -> str:
        return self.banking_domain

    @property
    def domain_invariants(self) -> List[str]:
        return self.banking_invariants

    acceptance_criteria: List[AcceptanceCriterion] = Field(default_factory=list, description="Danh sách Acceptance Criteria bóc tách được")
    product_risks: List[ProductRisk] = Field(default_factory=list, description="Ma trận rủi ro sản phẩm (RBT)")
    compliance_rules: List[ComplianceRule] = Field(default_factory=list, description="Các quy định pháp chế / tiêu chuẩn tuân thủ cần kiểm tra")
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
    category: str = Field(
        default="Positive (Happy Path)", 
        description="Phân loại kịch bản kiểm thử (Positive, Negative, Boundary, Security, Concurrency, Exception, State Transition, Business Invariants, Business Flow / End-to-End Impact...)"
    )
    group_feature: str = Field(
        default="1. Chức năng chính (AC-01)",
        description="Tên nhóm phân cấp lớn (Row 22)"
    )
    group_functional: str = Field(
        default="1.1. Luồng xử lý thành công",
        description="Tên nhóm phân cấp con (Row 23)"
    )
    scenario_title: str = Field(default="Kịch bản kiểm thử", description="Tiêu đề kịch bản kiểm thử rõ ràng")
    testing_technique: str = Field(
        default="Equivalence Partitioning", 
        description="Kỹ thuật kiểm thử áp dụng (Equivalence Partitioning, Boundary Value Analysis, Decision Table, State Transition, Concurrency, Fault Injection, Domain Invariants, Business Flow / End-to-End Impact, etc.)"
    )
    test_intent: str = Field(default="", description="Ý đồ kiểm thử")
    priority: Literal["Critical", "High", "Medium", "Low"] = Field(default="High", description="Mức độ ưu tiên kiểm thử")

    @property
    def title(self) -> str:
        return self.scenario_title

class TestCase(BaseModel):
    testcase_id: str = Field(default="TC 01", description="Mã Testcase định dạng 'TC 01', 'TC 02', ...")
    group_feature: str = Field(default="1. Chức năng chính (AC-01)", description="Nhóm tính năng lớn tương ứng")
    group_functional: str = Field(default="1.1. Luồng xử lý thành công", description="Nhóm functional con tương ứng")
    title: str = Field(default="Test case", description="Tên testcase mô tả hành động, điều kiện và rủi ro phòng ngừa")
    preconditions: str = Field(default="Hệ thống và dữ liệu sẵn sàng.", description="Điều kiện tiên quyết trước khi thực hiện test")
    steps: str = Field(default="1. Thực hiện gửi request\n2. Kiểm tra phản hồi", description="Các bước thực hiện đánh số: '1. ...\n2. ...'")
    expected_result: str = Field(default="HTTP Status 200 OK, xử lý thành công.", description="Kết quả mong đợi chi tiết kiểm chứng được")
    actual_result: str = Field(default="", description="Kết quả thực tế (để trống)")
    test_data: str = Field(default="{}", description="Dữ liệu test cụ thể (Payload JSON, tham số, dữ liệu đầu vào thực tế)")
    creator: str = Field(default="QA Automation Specialist", description="Người tạo")
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
