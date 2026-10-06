import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
import tempfile
from typing import List
import openpyxl
from src.core.models import (
    RequirementAnalysis,
    AcceptanceCriterion,
    ProductRisk,
    TestScenario,
    TestCase,
    ReviewResult,
    ReviewIssue,
    TraceabilityItem
)
from src.core.linter import lint_test_case, lint_test_suite_coverage, lint_scenarios
from src.utils.file_parsers import extract_input_content
from src.utils.excel_exporter import export_test_cases_to_excel
from src.core.workflow import build_qa_agentic_graph
from src.core.llm import load_qa_rules, load_config
from src.core.prompt_loader import resolve_domain_pack, resolve_banking_modules, load_domain_pack, load_prompt


def test_file_parser():
    print("[1/4] Testing File Parsers...")
    content, file_type = extract_input_content("samples/sample_user_story.md")
    assert file_type == "md"
    assert "VWCBT-4102" in content
    assert "AC-01" in content

    # Test Multi-Source with User Clarifications / Extra Info
    from src.utils.file_parsers import merge_multiple_sources
    merged_text, f_type, meta = merge_multiple_sources([
        "samples/sample_user_story.md",
        "Lưu ý: Khung giờ EOD chuẩn là 18h VNT, phí cố định 5.000 VND"
    ])
    assert f_type == "multi_document"
    assert "THÔNG TIN BỔ SUNG / LÀM RÕ TỪ USER" in merged_text or "User Clarifications & Overrides" in merged_text
    assert "18h VNT" in merged_text
    print("  -> Parser OK! Multi-source & User Clarifications tested (Read", len(merged_text), "chars).")

def test_linter():
    print("\n[2/4] Testing Deterministic QA Linter...")
    bad_tc = TestCase(
        testcase_id="TC 99",
        group_feature="1. Feature",
        group_functional="1.1 Functional",
        title="Bad test",
        preconditions="None",
        steps="Click login and wait a bit",
        expected_result="Verify it works properly",
        test_data="valid data",
        test_status="Not Test",
        priority="High",
        note="AC-01"
    )
    issues = lint_test_case(bad_tc)
    issue_types = [i.issue_type for i in issues]
    assert "Non-Deterministic Expected Result" in issue_types or "Ambiguous Step" in issue_types
    assert any("wait a bit" in i.description for i in issues)
    assert any("verify it works" in i.description for i in issues)
    print(f"  -> Linter correctly flagged {len(issues)} issues in ambiguous testcase!")

    # Test Banking Domain Linter checks (Concurrency, Gateway Timeout & Conditional QĐ 2345)
    payment_analysis = RequirementAnalysis(
        feature_name="Chuyển tiền Napas 24/7",
        business_overview="Thanh toán chuyển tiền",
        banking_domain="Payments & Fund Transfers (Napas, VietQR, Swift)",
        acceptance_criteria=[
            AcceptanceCriterion(
                ac_id="AC-01",
                title="Chuyển tiền qua App",
                description="Chuyển tiền trên App yêu cầu xác thực sinh trắc học khuôn mặt",
                risk_level="High"
            )
        ],
        product_risks=[
            ProductRisk(
                risk_id="RSK-01",
                risk_title="Trừ tiền 2 lần do timeout",
                risk_category="Integration & Timeout Risk",
                likelihood=4, impact=5, risk_score=20,
                risk_level="Critical", linked_ac_id="AC-01",
                mitigation_test_focus="Kiểm thử Idempotency key và timeout."
            )
        ]
    )
    incomplete_tcs = [
        TestCase(
            testcase_id="TC 01", group_feature="1. Transfer", group_functional="1.1 Basic",
            title="Chuyển tiền đơn giản 100k", preconditions="Active",
            steps="1. Gửi request POST /transfer\n2. Nhận kết quả",
            expected_result="HTTP Status 200 OK thành công.",
            test_data='{"amount": 100000}',
            test_status="Not Test", priority="High", note="AC-01"
        )
    ]
    coverage_issues = lint_test_suite_coverage(payment_analysis, incomplete_tcs)
    cov_issue_types = [i.issue_type for i in coverage_issues]
    assert "Missing Concurrency/Duplicate Case" in cov_issue_types
    assert "Missing Gateway Timeout/Reconciliation Case" in cov_issue_types
    assert "Banking Compliance Violation (QĐ 2345)" in cov_issue_types
    print(f"  -> Banking Linter correctly flagged {len(coverage_issues)} banking domain issues (Concurrency, Gateway Timeout & Conditional QĐ 2345)!")
    # Test Traceability Matrix Model
    trace_item = TraceabilityItem(
        ac_id="AC-01",
        ac_title="Chuyển tiền Napas",
        risk_level="High",
        covered_test_cases=["TC 01", "TC 02"],
        coverage_status="COVERED",
        coverage_notes="Covered Positive & Negative Boundary"
    )
    assert trace_item.ac_id == "AC-01"
    assert trace_item.coverage_status == "COVERED"
    print("  -> Traceability Matrix Data Model verified!")

def test_excel_exporter():
    print("\n[3/4] Testing Excel Exporter with default template (template/Template Test Execution .xlsx)...")
    req_analysis = RequirementAnalysis(
        feature_name="VWCBT-4102: Chuyển tiền Napas 24/7",
        app_name="Branch Portal / Mobile Banking",
        version="UAT 3.1.0",
        jira_or_doc_link="https://galaxyfinx.atlassian.net/browse/VWCBT-4102",
        business_overview="Chuyển tiền nhanh liên ngân hàng 24/7",
        acceptance_criteria=[
            AcceptanceCriterion(
                ac_id="AC-01",
                title="Chuyển tiền qua STK",
                description="Chuyển tiền qua STK thành công",
                business_rules=["Tối thiểu 10k, tối đa 500tr"],
                risk_level="High"
            )
        ]
    )

    group_1 = "1. Chuyển tiền Napas 247 qua Số tài khoản (AC-01)"
    group_1_1 = "1.1. Luồng thành công (Happy Path & Phí giao dịch)"
    group_2 = "2. Kiểm tra Hạn mức Giao dịch (AC-02)"
    group_2_1 = "2.1. Hạn mức tối thiểu"
    sample_test_cases = [
        TestCase(
            testcase_id="TC 01", group_feature=group_1, group_functional=group_1_1,
            title="Chuyển tiền thành công dưới 1 triệu VND (Miễn phí giao dịch)",
            preconditions="Tài khoản nguồn Active, số dư khả dụng >= 500,000 VND.",
            steps="1. Gửi request POST /v1/transfer/napas247\n2. Kiểm tra status code và response body",
            expected_result="- HTTP Status: 200 OK\n- Response Body:\n{\n  \"status\": \"SUCCESS\",\n  \"fee\": 0\n}",
            test_data="{\"from_account\": \"1012345678\", \"amount\": 500000}",
            test_status="Not Test", priority="High", note="AC-01"
        ),
        TestCase(
            testcase_id="TC 02", group_feature=group_1, group_functional=group_1_1,
            title="Chuyển tiền thành công từ 1 triệu VND trở lên (Thu phí 2,200 VND)",
            preconditions="",
            steps="1. Gửi request POST /v1/transfer/napas247\n2. Kiểm tra trừ tiền gốc và phí",
            expected_result="- HTTP Status: 200 OK\n- Số dư tài khoản nguồn bị trừ: 2,002,200 VND",
            test_data="{\"amount\": 2000000}",
            test_status="Not Test", priority="High", note="AC-01 | PENDING CLARIFICATION"
        ),
        TestCase(
            testcase_id="TC 03", group_feature=group_2, group_functional=group_2_1,
            title="Kiểm tra chuyển số tiền dưới mức tối thiểu (9,999 VND)",
            preconditions="Tài khoản nguồn hợp lệ.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 9999",
            expected_result="- HTTP Status: 400 Bad Request\n- Error Code: ERR_MIN_AMOUNT",
            test_data="{\"amount\": 9999}",
            test_status="Not Test", priority="Medium", note="AC-02"
        )
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_file = export_test_cases_to_excel(
            analysis=req_analysis,
            test_cases=sample_test_cases,
            output_path=os.path.join(tmp_dir, "suite.xlsx"),
            target_sheet_name="VWCBT_4102_Napas_Test",
            pending_clarifications=["Cần message lỗi chính xác cho hạn mức"]
        )
        wb = openpyxl.load_workbook(out_file, data_only=False)

    # Sheet test case của template được đổi tên; sheet phụ & sheet Pending giữ đúng thứ tự
    assert wb.sheetnames == ["VWCBT_4102_Napas_Test", "DRAW_BUG", "Cần làm rõ (Pending)"]
    ws = wb["VWCBT_4102_Napas_Test"]
    assert len(ws._images) == 1, "Logo của template phải được giữ nguyên"

    # Metadata ghi cạnh nhãn của template
    assert ws["C10"].value == "VWCBT-4102"
    assert ws["C11"].value == "Branch Portal / Mobile Banking"
    assert ws["C12"].value == "UAT 3.1.0"
    assert ws["C14"].value == "VWCBT-4102: Chuyển tiền Napas 24/7"
    assert ws["C15"].value == "https://galaxyfinx.atlassian.net/browse/VWCBT-4102"
    assert all(ws[f"C{r}"].value is None for r in (16, 17, 18)), "Ngày thực hiện / Người duyệt / Ngày duyệt để trống"

    # Header dòng 26 -> banner L1 (27), banner L2 (28), TC 01..02, banner L1/L2 nhóm 2, TC 03
    assert ws["B27"].value == group_1 and ws["B28"].value == group_1_1
    # Cột ID là công thức đếm 'TC*' phía trên (bỏ qua banner) -> xóa/chèn dòng tự đánh số lại
    assert ws["A29"].value == '=IF(B29<>"","TC "&TEXT(COUNTIF(A$26:A28,"TC*")+1,"00"),"")'
    assert ws["A30"].value == '=IF(B30<>"","TC "&TEXT(COUNTIF(A$26:A29,"TC*")+1,"00"),"")'
    assert ws["B31"].value == group_2 and ws["B32"].value == group_2_1
    assert ws["A33"].value == '=IF(B33<>"","TC "&TEXT(COUNTIF(A$26:A32,"TC*")+1,"00"),"")'
    assert ws["A27"].value is None and ws["A31"].value is None, "Dòng banner không có ID"
    assert ws.max_row == 33, "Dữ liệu mẫu của template phải được xóa hết"
    assert ws["B27"].fill.fgColor.rgb == "FFD5A6BD" and ws["B28"].fill.fgColor.rgb == "FFEAD1DC"

    # Không có cột 'Điều kiện tiên quyết' -> preconditions đứng đầu cột 'Các bước thực hiện'
    assert ws["C29"].value.startswith("Điều kiện tiên quyết:\nTài khoản nguồn Active")
    assert ws["C30"].value.startswith("1. Gửi request")
    assert ws["F29"].value == "{\n  \"from_account\": \"1012345678\",\n  \"amount\": 500000\n}"
    assert (ws["J29"].value, ws["K29"].value, ws["L29"].value) == ("Not Test", "High", "AC-01")
    # Kết quả thực tế / Người tạo / Kế hoạch / Ngày thực hiện để trống nhưng vẫn giữ style dòng dữ liệu của template
    for r in (29, 30, 33):
        assert all(ws[f"{c}{r}"].value is None for c in "EGHI")
    assert ws["G29"].border.left.style == ws["F29"].border.left.style

    # Test case PENDING tô vàng toàn dòng
    assert all(ws.cell(30, c).fill.fgColor.rgb == "FFFFF2CC" for c in range(1, 13))
    assert ws["B29"].fill.fgColor.rgb != "FFFFF2CC"

    # Công thức thống kê & dropdown bám đúng vùng dữ liệu mới
    assert ws["A24"].value == '=COUNTIF(A27:A33,"TC*")'
    assert ws["B24"].value == '=COUNTIF(J27:J33,"Passed")'
    assert ws["E24"].value == '=COUNTIF(J27:J33,"Not Test")'
    assert ws["F24"].value == "=A24-SUM(B24,C24,D24,E24)"
    assert sorted(str(dv.sqref) for dv in ws.data_validations.dataValidation) == ["J27:J33", "K27:K33"]
    assert ws.auto_filter.ref == "A26:L33"
    print("  -> Excel Exporter OK! Template sheet renamed, metadata/banners/formulas populated.")


def test_graph_compilation():
    print("\n[4/4] Testing LangGraph Workflow Compilation...")
    graph = build_qa_agentic_graph()
    assert graph is not None
    print("  -> LangGraph StateGraph compiled successfully!")
    # Test RequirementAnalysis attribute compatibility
    req = RequirementAnalysis(
        feature_name="Test Feature",
        business_overview="Mục tiêu nghiệp vụ kiểm thử",
        banking_domain="Payments & Fund Transfers (Napas, VietQR, Swift)"
    )
    assert req.business_overview == "Mục tiêu nghiệp vụ kiểm thử"
    assert req.business_objective == "Mục tiêu nghiệp vụ kiểm thử"
    print("  -> RequirementAnalysis business_overview/business_objective compatibility verified!")
    # Test ProductRisk model fields
    risk = ProductRisk(
        risk_id="RSK-01",
        risk_title="Rủi ro trừ tiền 2 lần",
        risk_description="Hệ thống có thể gửi duplicate request dẫn đến trừ tiền 2 lần",
        risk_category="Financial & Ledger Risk",
        risk_level="Critical",
        mitigation_test_focus="Test Idempotency 50ms"
    )
    assert risk.risk_title == "Rủi ro trừ tiền 2 lần"
    assert risk.risk_description.startswith("Hệ thống có thể")
    print("  -> ProductRisk risk_title/risk_description verified!")
    # Test cross-property aliases for TestScenario & TestCase
    sc = TestScenario(
        scenario_id="SC_01",
        scenario_title="Kiểm tra chuyển tiền thành công",
        group_feature="Chuyển tiền",
        group_functional="Napas 24/7"
    )
    assert sc.title == "Kiểm tra chuyển tiền thành công"
    assert sc.scenario_title == "Kiểm tra chuyển tiền thành công"

    tc = TestCase(
        testcase_id="TC 01",
        title="Kiểm tra chuyển tiền thành công khi truyền đúng payload",
        steps="1. Gửi request",
        expected_result="Status 200 OK",
        test_data="{}"
    )
    assert tc.title == "Kiểm tra chuyển tiền thành công khi truyền đúng payload"
    assert tc.scenario_title == "Kiểm tra chuyển tiền thành công khi truyền đúng payload"
    print("  -> TestScenario/TestCase title & scenario_title cross-aliases verified!")
    # Test clean_jira_key_from_title
    from src.utils.file_parsers import clean_jira_key_from_title
    dirty_title = 'Kiểm tra thực thi giao dịch VWCBT-3230 thành công khi truyền trường "transaction_mode" mang giá trị hợp lệ "standard"'
    cleaned_title = clean_jira_key_from_title(dirty_title)
    assert "VWCBT-3230" not in cleaned_title
    assert cleaned_title == 'Kiểm tra thực thi giao dịch thành công khi truyền trường "transaction_mode" mang giá trị hợp lệ "standard"'
    print("  -> clean_jira_key_from_title successfully stripped embedded Jira key!")
    # Test Guardrail Validation
    from src.core.guardrail import validate_requirement_input
    assert not validate_requirement_input("alo")[0]
    assert not validate_requirement_input("hi")[0]
    assert not validate_requirement_input("test")[0]
    assert not validate_requirement_input("123")[0]
    assert not validate_requirement_input("asdfghjkl")[0]
    assert not validate_requirement_input("lam test case ho voi")[0]
    
    # Valid cases
    assert validate_requirement_input("VWCBT-3648")[0]
    assert validate_requirement_input("https://galaxyfinx.atlassian.net/browse/VWCBT-3648")[0]
    assert validate_requirement_input("Tính năng chuyển tiền Napas 24/7. AC1: Hạn mức tối thiểu 10,000 VND. AC2: Hạch toán nợ có.")[0]
    print("  -> Input Guardrail & Spam Prevention verified!")

    # Test Clarification Gate Conditional Routing
    from src.core.workflow import should_continue_after_analysis
    clarify_analysis = RequirementAnalysis(
        feature_name="Tính năng chưa rõ",
        needs_user_clarification=True,
        clarification_questions=["Hạn mức tối đa áp dụng theo ngày hay theo từng giao dịch?"]
    )
    assert should_continue_after_analysis({"requirement_analysis": clarify_analysis}) == "needs_clarification"

    clear_analysis = RequirementAnalysis(
        feature_name="Tính năng rõ ràng",
        needs_user_clarification=False
    )
    assert should_continue_after_analysis({"requirement_analysis": clear_analysis}) == "design_scenarios"
    print("  -> Interactive Clarification Gate (Human-in-the-Loop) routing verified!")
def test_agent_invocations():
    print("\n[5/5] Testing Agent LLM Invocation Signatures & Contracts...")
    from unittest.mock import patch
    from src.agents.requirement_analyst import analyze_requirements
    from src.agents.scenario_designer import design_test_scenarios, ScenarioListResponse
    from src.agents.testcase_generator import generate_test_cases, BatchTestSuiteResponse
    from src.agents.reviewer import review_and_lint_test_suite, SemanticReviewPayload
    with patch("src.agents.requirement_analyst.invoke_structured_llm") as mock_ana, \
         patch("src.agents.scenario_designer.invoke_structured_llm") as mock_sc, \
         patch("src.agents.testcase_generator.invoke_structured_llm") as mock_gen, \
         patch("src.agents.reviewer.invoke_structured_llm") as mock_rev:
        mock_ana.return_value = RequirementAnalysis(
            feature_name="Chặn rút tiền EOD",
            banking_domain="Savings & Term Deposits (Interest, Maturity, Accrual)",
            acceptance_criteria=[AcceptanceCriterion(ac_id="AC-01", title="Chặn EOD", description="Chặn lúc 18h", risk_level="High")]
        )
        analysis = analyze_requirements("Chặn rút tiền trong giờ EOD 18:00 VNT", provider="gemini")
        assert mock_ana.call_count == 1
        assert "system_prompt" in mock_ana.call_args.kwargs
        assert "user_prompt" in mock_ana.call_args.kwargs
        assert "schema" in mock_ana.call_args.kwargs

        mock_sc.return_value = ScenarioListResponse(
            scenarios=[
                TestScenario(scenario_id="SC_01", trace_ac_id="AC-01", group_feature="1. Chặn EOD", group_functional="1.1. Luồng chính", scenario_title='Kiểm tra "18:00:00"', testing_technique="Boundary Value Analysis (BVA)", priority="High")
            ]
        )
        scenarios = design_test_scenarios(analysis, provider="gemini")
        assert mock_sc.call_count == 1
        assert "system_prompt" in mock_sc.call_args.kwargs

        mock_gen.return_value = BatchTestSuiteResponse(
            test_cases=[
                TestCase(testcase_id="TC 01", group_feature="1. Chặn EOD", group_functional="1.1. Luồng chính", title='Kiểm tra "18:00:00"', preconditions="Active", steps="POST", expected_result="400 CV_043", test_data="{}", test_status="Not Test", priority="High", note="AC-01")
            ]
        )
        gen_result = generate_test_cases(analysis, scenarios, provider="gemini")
        assert mock_gen.call_count == 1
        assert "system_prompt" in mock_gen.call_args.kwargs
        test_cases = gen_result.test_cases
        assert len(test_cases) == 1

        mock_rev.return_value = SemanticReviewPayload(
            semantic_score=100,
            traceability_matrix=[],
            semantic_issues=[],
            feedback_summary="All good"
        )
        rev_res = review_and_lint_test_suite(analysis, test_cases, provider="gemini")
        assert mock_rev.call_count == 1
        assert "system_prompt" in mock_rev.call_args.kwargs
        assert isinstance(rev_res, ReviewResult)
    print("  -> All 4 Agent invoke_structured_llm signatures & kwargs verified!")
def test_multi_domain_support():
    print("\n[6/6] Testing Universal Multi-Domain Support (E-Commerce, Logistics, SaaS, FinTech)...")
    from src.core.models import RequirementAnalysis, AcceptanceCriterion, TestCase
    from src.core.linter import lint_test_suite_coverage

    # 1. Test E-Commerce Domain
    ecom_analysis = RequirementAnalysis(
        feature_name="Áp dụng Voucher giảm giá Giỏ hàng & Flash Sale",
        app_name="ShopeeClone Web / Mobile",
        version="2.0.0",
        banking_domain="E-Commerce & Retail (Cart, Checkout, Promotion, Flash Sale)",
        business_overview="Khách hàng áp mã giảm giá 20% tối đa 50k khi giỏ hàng >= 200k",
        acceptance_criteria=[
            AcceptanceCriterion(ac_id="AC-01", title="Áp voucher hợp lệ", description="Giảm 20% khi đơn >= 200k", risk_level="High"),
            AcceptanceCriterion(ac_id="AC-02", title="Chặn voucher khi đơn < 200k", description="Báo lỗi khi đơn không đủ điều kiện", risk_level="Medium")
        ]
    )
    assert ecom_analysis.business_domain == "E-Commerce & Retail (Cart, Checkout, Promotion, Flash Sale)"
    
    ecom_cases = [
        TestCase(testcase_id="TC 01", group_feature="1. Áp voucher (AC-01)", group_functional="1.1. Thành công", title='Kiểm tra áp voucher thành công khi đơn "250000" VND', preconditions="User có voucher", steps="1. Gửi request áp voucher\n2. Kiểm tra giảm giá", expected_result="Giảm 50,000 VND, HTTP 200 OK", test_data='{"cart_total": 250000}', note="AC-01"),
        TestCase(testcase_id="TC 02", group_feature="1. Áp voucher (AC-02)", group_functional="1.2. Bắt lỗi", title='Kiểm tra báo lỗi khi đơn "150000" dưới mức tối thiểu', preconditions="User có voucher", steps="1. Gửi request áp voucher\n2. Kiểm tra lỗi", expected_result="HTTP 400 Bad Request, mã lỗi 'VOUCHER_MIN_ORDER_NOT_MET'", test_data='{"cart_total": 150000}', note="AC-02")
    ]
    ecom_issues = lint_test_suite_coverage(ecom_analysis, ecom_cases)
    assert not any(i.issue_type == "Traceability Gap" for i in ecom_issues)
    print("  -> E-Commerce Domain analysis & testcase coverage verified!")

    # 2. Test Logistics & Supply Chain Domain
    logistics_analysis = RequirementAnalysis(
        feature_name="Cập nhật trạng thái lộ trình vận chuyển đơn hàng",
        app_name="GHTK / ViettelPost Delivery Hub",
        banking_domain="Logistics, Supply Chain & Fleet Tracking",
        business_overview="Tài xế quét mã barcode để chuyển trạng thái từ IN_TRANSIT sang DELIVERED",
        acceptance_criteria=[
            AcceptanceCriterion(ac_id="AC-01", title="Quét giao thành công", description="Cập nhật DELIVERED", risk_level="High")
        ]
    )
    assert logistics_analysis.business_domain == "Logistics, Supply Chain & Fleet Tracking"
    print("  -> Logistics Domain verified!")

def test_linter_dead_checks_regression():
    """
    D2 regression: bộ test suite Healthcare có 1 rủi ro Critical (RSK-01) chưa được bao phủ
    và chỉ có duy nhất 1 test case happy-path (mặc định trả về "HTTP Status 200 OK").
    Trước khi sửa Step 4-5, Linter chỉ phát hiện được 'Technique Under-Coverage (Negative EP)'
    vì BVA-check và RBT-check đều là dead code (luôn no-op) và Healthcare không có domain rule riêng.
    """
    print("\n[7/7] Testing Linter Dead-Checks Regression (BVA / RBT / Domain PHI)...")
    healthcare_analysis = RequirementAnalysis(
        feature_name="Tra cứu hồ sơ bệnh án điện tử",
        banking_domain="Healthcare",
        acceptance_criteria=[
            AcceptanceCriterion(ac_id="AC-01", title="Xem hồ sơ bệnh án", description="Bác sĩ xem được hồ sơ bệnh án của bệnh nhân", risk_level="Critical")
        ],
        product_risks=[
            ProductRisk(risk_id="RSK-01", risk_title="Truy cập trái phép hồ sơ bệnh án", risk_level="Critical", linked_ac_id="AC-01")
        ]
    )
    happy_path_case = TestCase()  # Mặc định: title="Test case", expected_result="HTTP Status 200 OK, xử lý thành công."
    issues = lint_test_suite_coverage(healthcare_analysis, [happy_path_case])
    issue_types = [i.issue_type for i in issues]

    assert "Technique Under-Coverage (Negative EP)" in issue_types
    assert "Technique Under-Coverage (BVA)" in issue_types
    assert "RBT Under-Coverage Violation" in issue_types
    assert "Missing PHI Access-Control Case" in issue_types
    print(f"  -> Linter correctly flagged all {len(issue_types)} previously-dead checks: {issue_types}")


def test_new_qa_capabilities():
    """
    Kiểm chứng trực tiếp 6 năng lực mới của bộ khung Linter/Config đã bổ sung:
    Assertion-Anchor, Duplicate Detection, Scenario-Level Lint, Live qa_rules, Domain Pack Routing,
    Phantom AC Reference (TestCase-level Scope Drift Guard).
    """
    print("\n[8/8] Testing New QA Capabilities (Assertion-Anchor, Duplicate, Scenario Lint, Live Config, Domain Routing, Phantom AC)...")

    # 1. Assertion-Anchor check (4c): Expected Result đủ dài nhưng KHÔNG có tiêu chí định lượng nào
    vague_tc = TestCase(expected_result="Hệ thống xử lý xong và hiển thị thông báo cho người dùng biết kết quả")
    anchor_issues = lint_test_case(vague_tc)
    assert any(i.issue_type == "Non-Deterministic Expected Result" and "định lượng" in i.description for i in anchor_issues)
    print("  -> Assertion-Anchor check correctly rejected Expected Result without HTTP/status/schema/số liệu!")

    # 2. Duplicate Test Case check (4d): 2 test case trùng tiêu đề + test data
    dup_a = TestCase(testcase_id="TC 01", title="Đăng nhập thành công", test_data='{"user": "a"}')
    dup_b = TestCase(testcase_id="TC 02", title="Đăng nhập thành công", test_data='{"user": "a"}')
    dup_analysis = RequirementAnalysis(acceptance_criteria=[AcceptanceCriterion(ac_id="AC-01")])
    dup_issues = lint_test_suite_coverage(dup_analysis, [dup_a, dup_b])
    assert any(i.issue_type == "Duplicate Test Case" for i in dup_issues)
    print("  -> Duplicate Test Case check correctly flagged 2 identical test cases!")

    # 3. Scenario-Level Lint (Step 7): phantom AC, thiếu kỹ thuật bắt buộc, rò rỉ tên kỹ thuật, thiếu RBT
    scenario_analysis = RequirementAnalysis(
        acceptance_criteria=[AcceptanceCriterion(ac_id="AC-01")],
        product_risks=[ProductRisk(risk_id="RSK-01", risk_level="Critical")]
    )
    leaky_scenario = TestScenario(scenario_id="SC_01", trace_ac_id="AC-99", scenario_title="Kiểm tra BVA giá trị biên", testing_technique="Equivalence Partitioning")
    scenario_issues = lint_scenarios(scenario_analysis, [leaky_scenario])
    scenario_issue_types = [i.issue_type for i in scenario_issues]
    assert "Traceability Gap" in scenario_issue_types  # AC-99 không tồn tại + AC-01 chưa được bao phủ
    assert "Technique Under-Coverage" in scenario_issue_types  # Thiếu Boundary Value Analysis
    assert "Format Violation" in scenario_issue_types  # "BVA" rò rỉ vào scenario_title
    assert "RBT Under-Coverage Violation" in scenario_issue_types  # RSK-01 Critical chưa có scenario trace tới
    print(f"  -> Scenario-Level Linter correctly flagged {len(scenario_issues)} scenario issues: {scenario_issue_types}")

    # 4. Live qa_rules (Step 3): config.yaml là nguồn thật duy nhất, không hardcode rải rác trong code
    live_rules = load_qa_rules()
    yaml_qa_rules = load_config().get("qa_rules", {})
    assert live_rules["min_review_score"] == yaml_qa_rules["min_review_score"] == 95
    assert "verify it works" in live_rules["banned_vague_words"]
    print(f"  -> qa_rules đọc trực tiếp từ config.yaml, min_review_score={live_rules['min_review_score']} (không hardcode)!")

    # 5. Domain Pack Routing (Step 1/5): đúng domain pack theo từ khóa (nguyên từ), mặc định 'api-platform' khi không khớp
    routing_cases = [
        ("FinTech & Banking (Napas, VietQR)", "", "fintech-banking"),
        ("E-Commerce & Retail (Cart, Checkout)", "", "ecommerce-retail"),
        ("Một tính năng nội bộ không rõ ngành", "", "api-platform"),
        ("Lending", "Giải ngân khoản vay tiêu dùng", "fintech-banking"),
        ("Credit Cards", "Phát hành thẻ tín dụng", "fintech-banking"),
        ("Cards", "Khóa thẻ ghi nợ", "fintech-banking"),
        ("Overdraft", "Cấp hạn mức thấu chi", "fintech-banking"),
        ("Loan Origination", "Chấm điểm tín dụng", "fintech-banking"),
        ("Treasury", "Phiếu chi quỹ", "api-platform"),  # 'phi' (healthcare) không được khớp chuỗi con trong 'Phiếu'
        ("Developer tools", "Sinh code mẫu cho SDK", "api-platform"),  # 'cod' (logistics) không được khớp trong 'code'
        ("Hospital", "Tra cứu PHI của bệnh nhân", "healthcare"),
    ]
    for domain, feature, expected_pack in routing_cases:
        assert resolve_domain_pack(domain, feature) == expected_pack, (domain, feature, resolve_domain_pack(domain, feature))
    assert resolve_banking_modules("Cards", "Khóa thẻ khi nhập sai PIN") == ["cards"]
    assert resolve_banking_modules("Lending", "Thu nợ gốc lãi khoản vay quá hạn") == ["lending"]
    assert resolve_banking_modules("Overdraft", "Cấp hạn mức thấu chi") == ["overdraft"]
    assert resolve_banking_modules("Deposits", "Tất toán trước hạn sổ tiết kiệm") == ["deposits"]
    assert resolve_banking_modules("Core Banking", "Chặn rút tiền trong giờ EOD") == []
    core_pack = load_domain_pack("FinTech & Banking")
    assert "Double-Entry" in core_pack and "Bypass Phong tỏa" in core_pack and "Hạn mức Thấu chi (OD)" in core_pack
    assert "# MODULE:" not in core_pack  # không nhắc sản phẩm -> chỉ nạp lõi chung
    lending_pack = load_domain_pack("Lending", "Giải ngân khoản vay", "Thu nợ theo job 17h khi khoản vay quá hạn")
    assert "LÕI CHUNG" in lending_pack and "# MODULE: LENDING" in lending_pack and "# MODULE: CARDS" not in lending_pack
    assert "Decision Table thứ tự phân bổ thu nợ" in lending_pack
    cards_od_pack = load_domain_pack("Cards", "Giao dịch thẻ dùng hạn mức thấu chi")
    assert "# MODULE: CARDS" in cards_od_pack and "# MODULE: OVERDRAFT" in cards_od_pack and "# MODULE: LENDING" not in cards_od_pack
    assert "CROSS-COMPONENT BUSINESS INTERACTION" in load_prompt("02_scenario_designer")
    assert "CROSS-FEATURE / CROSS-COMPONENT BUSINESS LOGIC" in load_prompt("03_testcase_generator")
    assert "tính năng phụ thuộc/tương tác với cơ chế nghiệp vụ" in load_prompt("01_requirement_analyst")
    print("  -> Domain Pack routing khớp nguyên từ, nạp lõi ngân hàng + đúng module sản phẩm, fallback 'api-platform' khi không khớp!")

    # 5b. Banking linter: rule chỉ kích hoạt khi yêu cầu nhắc chủ đề; marker/chuỗi con không được tính là bằng chứng
    def banking_issue_types(feature: str, ac_text: str, tc_texts: List[str]) -> List[str]:
        analysis = RequirementAnalysis(feature_name=feature, banking_domain="Core Banking",
                                       acceptance_criteria=[AcceptanceCriterion(ac_id="AC-01", title=feature, description=ac_text)])
        cases = [TestCase(testcase_id=f"TC {i:02d}", title=text, steps="1. Thực hiện", expected_result="HTTP 200, trạng thái ACTIVE",
                          test_data='{"x": 1}', note="AC-01") for i, text in enumerate(tc_texts, start=1)]
        return [i.issue_type for i in lint_test_suite_coverage(analysis, cases)]

    config_types = banking_issue_types("Cấu hình biểu lãi suất tiền gửi", "Admin cập nhật bảng lãi suất theo kỳ hạn", ["Kiểm tra cập nhật lãi suất"])
    assert "Missing Concurrency/Duplicate Case" not in config_types and "Missing Gateway Timeout/Reconciliation Case" not in config_types, config_types
    marker_types = banking_issue_types("Chuyển tiền Napas 24/7", "Chuyển tiền liên ngân hàng qua Napas",
                                       ["Kiểm tra chuyển tiền PENDING CLARIFICATION", "Kiểm tra trace log giao dịch trùng khớp số tiền"])
    assert "Missing Concurrency/Duplicate Case" in marker_types and "Missing Gateway Timeout/Reconciliation Case" in marker_types, marker_types
    covered_types = banking_issue_types("Chuyển tiền Napas 24/7", "Chuyển tiền liên ngân hàng qua Napas",
                                        ["Kiểm tra gửi đồng thời 2 lệnh chuyển tiền", "Kiểm tra Napas trả 504 timeout chuyển sang đối soát"])
    assert "Missing Concurrency/Duplicate Case" not in covered_types and "Missing Gateway Timeout/Reconciliation Case" not in covered_types, covered_types
    pin_types = banking_issue_types("Đổi PIN thẻ", "Khách hàng đổi PIN trên App", ["Kiểm tra đổi PIN thành công"])
    assert "Missing PIN Retry/Lock Case" in pin_types and "Missing Repayment Allocation Case" not in pin_types, pin_types
    assert "Missing PIN Retry/Lock Case" not in banking_issue_types("Đổi PIN thẻ", "Khách hàng đổi PIN trên App", ["Kiểm tra nhập sai PIN 3 lần thì thẻ bị khóa"])
    repay_types = banking_issue_types("Thu nợ khoản vay", "Job 17h thu nợ gốc và lãi", ["Kiểm tra thu nợ đủ gốc lãi"])
    assert "Missing Repayment Allocation Case" in repay_types and "Missing PIN Retry/Lock Case" not in repay_types, repay_types
    print("  -> Banking linter rules chỉ áp dụng khi yêu cầu nhắc chủ đề, không bị đánh lừa bởi 'PENDING CLARIFICATION'/'trace'/'trùng khớp'!")

    # 5c. Skill .agents/banking-qa-testsuite-generator dùng đúng bản Domain Pack của pipeline (không drift)
    repo_root = Path(__file__).resolve().parent.parent
    skill_pack_dir = repo_root / ".agents/skills/banking-qa-testsuite-generator/references/05-banking-domain-pack"
    pack_sources = {"core.md": repo_root / "prompts/domains/fintech-banking.md",
                    **{p.name: p for p in (repo_root / "prompts/domains/banking").glob("*.md")}}
    assert sorted(p.name for p in skill_pack_dir.glob("*.md")) == sorted(pack_sources)
    for name, source in pack_sources.items():
        assert (skill_pack_dir / name).read_text(encoding="utf-8") == source.read_text(encoding="utf-8"), f"Skill pack drift: {name}"
    print("  -> Skill banking-qa-testsuite-generator đồng bộ 100% với Domain Pack ngân hàng của pipeline!")

    # 6. Phantom AC Reference at TestCase level (Scope Drift Guard): TC trỏ tới AC không tồn tại trong analysis
    scope_analysis = RequirementAnalysis(acceptance_criteria=[AcceptanceCriterion(ac_id="AC-01")])
    onscope_tc = TestCase(testcase_id="TC 01", title="Rút tiền thành công trước EOD", group_feature="1. Chặn rút tiền EOD (AC-01)", note="Trace: AC-01")
    drifted_tc = TestCase(testcase_id="TC 02", title="Chuyển tiền Napas thành công (AC-99)", group_feature="2. Chuyển tiền Napas (AC-99)", note="Trace: AC-99")
    drift_issues = lint_test_suite_coverage(scope_analysis, [onscope_tc, drifted_tc])
    phantom_tc_issues = [i for i in drift_issues if i.issue_type == "Scope Drift / Phantom AC Reference"]
    assert len(phantom_tc_issues) == 1 and phantom_tc_issues[0].target_tc_id == "TC 02" and "AC-99" in phantom_tc_issues[0].description
    assert not any(i.issue_type == "Scope Drift / Phantom AC Reference" for i in lint_test_suite_coverage(scope_analysis, [onscope_tc]))
    print("  -> Phantom AC Reference check correctly flagged Test Case tracing a non-existent AC (Scope Drift)!")


def test_clarification_gate():
    """
    Kiểm chứng cơ chế Hard-Stop Clarification Gate:
    - Deterministic detector + gate (Step 1) bắt buộc bật needs_user_clarification khi thiếu API sample / message.
      Mặc định assume User Story là cho API; nếu tài liệu có yếu tố UI mà không tự nhắc tới API thì bỏ qua nhóm câu hỏi API.
      Khi là câu chuyện API: bắt buộc rõ CẢ request lẫn response. Message: bắt buộc rõ CẢ luồng thành công lẫn thất bại.
    - Waiver phrases ("KHÔNG CÓ API" / "KHÔNG CÓ MESSAGE") miễn trừ nhóm câu hỏi tương ứng.
    - Fabricated-message linter check (Step 4) chỉ flag Critical khi message KHÔNG có căn cứ trong tài liệu gốc.
    - Generator marker invariant (Step 3): test case đánh dấu PENDING CLARIFICATION nhưng không kèm câu hỏi
      thì generate_test_cases() phải tự tổng hợp 1 câu hỏi thay thế.
    """
    print("\n[9/9] Testing Clarification Gate (Missing API Sample / Message)...")
    from unittest.mock import patch
    from src.core.clarification import (
        detect_missing_artifacts, apply_clarification_gate,
        MISSING_API_REQUEST_QUESTION, MISSING_API_RESPONSE_QUESTION,
        MISSING_SUCCESS_MESSAGE_QUESTION, MISSING_ERROR_MESSAGE_QUESTION,
    )
    from src.agents.testcase_generator import generate_test_cases, BatchTestSuiteResponse

    # 1. Mặc định: concept của User Story được ASSUME LÀ CHO API -> tài liệu không nhắc UI lẫn API
    #    vẫn bị hỏi đủ 4 điểm: request, response, message thành công, message lỗi.
    bare = "Chặn rút tiền trong giờ EOD 18h"
    assert detect_missing_artifacts(bare) == [
        MISSING_API_REQUEST_QUESTION, MISSING_API_RESPONSE_QUESTION,
        MISSING_SUCCESS_MESSAGE_QUESTION, MISSING_ERROR_MESSAGE_QUESTION,
    ], detect_missing_artifacts(bare)

    # 1b. Tài liệu có yếu tố UI nhưng KHÔNG nhắc tới API -> bỏ qua nhóm câu hỏi API, vẫn hỏi đủ 2 message
    ui_only = bare + " Yêu cầu hiển thị thông tin trên màn hình ứng dụng."
    assert detect_missing_artifacts(ui_only) == [MISSING_SUCCESS_MESSAGE_QUESTION, MISSING_ERROR_MESSAGE_QUESTION], detect_missing_artifacts(ui_only)

    # 1c. Tài liệu UI nhưng CÓ nhắc tới việc gọi API -> hỏi lại nhóm API (2) cộng nhóm message (2)
    ui_with_api = ui_only + " Màn hình gọi API để xử lý giao dịch."
    assert len(detect_missing_artifacts(ui_with_api)) == 4, detect_missing_artifacts(ui_with_api)

    # 1d. Có request nhưng CHƯA có response -> chỉ còn thiếu response (request đã thỏa)
    request_only = ui_with_api + ' Gọi POST /api/v1/withdraw body {"amount": 1000}.'
    assert detect_missing_artifacts(request_only) == [MISSING_API_RESPONSE_QUESTION, MISSING_SUCCESS_MESSAGE_QUESTION, MISSING_ERROR_MESSAGE_QUESTION]

    # 1e. Đủ CẢ request, response, message thành công lẫn message lỗi -> không còn câu hỏi nào
    full_api = (
        request_only + ' Response trả về HTTP 200 kèm thông báo "Rút tiền thành công". '
        'Trường hợp lỗi trả về HTTP 400 mã lỗi CV_043 kèm thông báo "Giao dịch thất bại do tài khoản bị khóa".'
    )
    assert detect_missing_artifacts(full_api) == [], detect_missing_artifacts(full_api)
    assert detect_missing_artifacts(ui_with_api + " KHÔNG CÓ API, KHÔNG CÓ MESSAGE") == []

    # 1f. Waiver TỰ DO (không cần đúng khuôn mẫu "KHÔNG CÓ API/MESSAGE") vẫn được chấp nhận
    free_form_waiver = bare + " Tính năng này hiện chưa có API nào cả, cũng chưa quy định message riêng gì hết."
    assert detect_missing_artifacts(free_form_waiver) == [], detect_missing_artifacts(free_form_waiver)
    qna_style_waiver = bare + " Message: N/A. API: not applicable."
    assert detect_missing_artifacts(qna_style_waiver) == [], detect_missing_artifacts(qna_style_waiver)

    # 1g. Dán nguyên lệnh cURL thật (không phải văn bản "POST /path") -> phía REQUEST phải được coi là ĐỦ,
    #     KHÔNG được hỏi lại MISSING_API_REQUEST_QUESTION (bug: trước đây regex chỉ nhận "METHOD /path",
    #     bỏ sót cú pháp cURL thật -X POST + URL đầy đủ -> Agent cứ hỏi API hoài dù User đã cung cấp).
    curl_only = bare + ''' curl -X POST https://api.bank.com/v1/withdraw -H "Content-Type: application/json" -d '{"amount": 1000000}' '''
    curl_issues = detect_missing_artifacts(curl_only)
    assert MISSING_API_REQUEST_QUESTION not in curl_issues, curl_issues
    assert MISSING_API_RESPONSE_QUESTION in curl_issues, curl_issues
    # cURL không kèm -X (mặc định GET) vẫn phải được nhận diện là 1 request cụ thể
    curl_bare_get = bare + " curl https://api.bank.com/v1/accounts/123"
    assert MISSING_API_REQUEST_QUESTION not in detect_missing_artifacts(curl_bare_get)
    # cURL + response mẫu đầy đủ -> hết sạch câu hỏi API (chỉ còn message nếu tài liệu chưa nêu)
    curl_full = curl_only + ' Response trả về HTTP 200 kèm thông báo "Rút tiền thành công". Trường hợp lỗi trả về HTTP 400 mã lỗi CV_043 kèm thông báo "Giao dịch thất bại".'
    assert detect_missing_artifacts(curl_full) == [], detect_missing_artifacts(curl_full)
    print("  -> A real cURL command alone already satisfies the API REQUEST requirement; Agent no longer loops asking for it!")

    gated_default = apply_clarification_gate(RequirementAnalysis(feature_name="X"), bare)
    assert gated_default.needs_user_clarification is True and len(gated_default.clarification_questions) == 4
    gated_ui = apply_clarification_gate(RequirementAnalysis(feature_name="Y"), ui_only)
    assert gated_ui.needs_user_clarification is True and gated_ui.clarification_questions == [MISSING_SUCCESS_MESSAGE_QUESTION, MISSING_ERROR_MESSAGE_QUESTION]
    print("  -> Deterministic detector requires BOTH request+response and BOTH success+error message; UI-only docs skip the API group; waivers honoured!")

    # 1h. REGRESSION for the reported production bug: User replies to a clarification round with a
    # genuinely freeform, non-templated Vietnamese phrase — the bot must NOT rigidly re-ask the exact
    # same question. `detect_missing_artifacts()` itself still can't see the reply (no "api"/"message"
    # keyword anywhere in it) — that IS the point: no fixed regex/phrase whitelist can cover genuine
    # natural language, so `apply_clarification_gate`'s `prior_questions` arg must defer to the LLM's
    # own NLU verdict (mocked here) for any question already asked in a previous round.
    from src.agents.requirement_analyst import analyze_requirements as _analyze_requirements

    round1_questions = list(gated_default.clarification_questions)
    assert round1_questions == [
        MISSING_API_REQUEST_QUESTION, MISSING_API_RESPONSE_QUESTION,
        MISSING_SUCCESS_MESSAGE_QUESTION, MISSING_ERROR_MESSAGE_QUESTION,
    ], round1_questions

    reported_reply = "cứ để tạm example đi ko có cụ thể"  # verbatim from the actual reported Slack bug
    other_freeform_replies = [
        "thôi kệ đi, chưa cần cụ thể đâu, để vậy trước đã",
        "sao cũng được, không quan trọng đâu",
    ]
    for freeform_reply in [reported_reply] + other_freeform_replies:
        merged_round2 = bare + "\n\n## THÔNG TIN BỔ SUNG / LÀM RÕ TỪ USER\n" + freeform_reply
        # Reply never mentions "api"/"message" -> the deterministic detector alone still (correctly,
        # unchanged) flags all 4 as missing; this is the strict safety net that must stay intact.
        assert detect_missing_artifacts(merged_round2) == round1_questions, detect_missing_artifacts(merged_round2)
        with patch("src.agents.requirement_analyst.invoke_structured_llm") as mock_llm:
            # Simulates the LLM having read the WHOLE merged content (incl. the freeform reply) and
            # correctly judged every previously-asked point resolved/waived.
            mock_llm.return_value = RequirementAnalysis(
                feature_name="Chặn rút tiền EOD",
                needs_user_clarification=False,
                clarification_questions=[],
            )
            resolved = _analyze_requirements(
                raw_content=merged_round2,
                provider="gemini",
                prior_clarification_questions=round1_questions,
            )
        assert resolved.needs_user_clarification is False, resolved.clarification_questions
        assert resolved.clarification_questions == [], resolved.clarification_questions
    print(f"  -> Reported bug fixed: freeform reply '{reported_reply}' (+ 2 other phrasings), with zero api/message "
          f"keywords, no longer re-triggers the exact same clarification question once the LLM itself judges it resolved!")

    # 1i. Safety check: the mechanism must NOT blindly clear everything -- if the LLM (having read the
    # SAME freeform reply) still independently judges one particular previously-asked question as
    # genuinely unresolved, the gate must keep surfacing exactly that one (per-question LLM judgment,
    # never a blanket bypass).
    with patch("src.agents.requirement_analyst.invoke_structured_llm") as mock_llm:
        mock_llm.return_value = RequirementAnalysis(
            feature_name="Chặn rút tiền EOD",
            needs_user_clarification=True,
            clarification_questions=[MISSING_API_REQUEST_QUESTION],
        )
        still_pending = _analyze_requirements(
            raw_content=bare + "\n\n## THÔNG TIN BỔ SUNG / LÀM RÕ TỪ USER\n" + reported_reply,
            provider="gemini",
            prior_clarification_questions=round1_questions,
        )
    assert still_pending.needs_user_clarification is True
    assert still_pending.clarification_questions == [MISSING_API_REQUEST_QUESTION], still_pending.clarification_questions
    print("  -> Safety check: apply_clarification_gate defers to the LLM's PER-QUESTION judgment, not a blanket bypass -- a question the LLM itself still flags stays surfaced!")

    # 1j. First-pass behaviour (no prior_questions arg at all, e.g. every pre-existing call site in
    # this test file / the rest of the codebase) must remain byte-identical to before this fix.
    assert gated_default.needs_user_clarification is True and len(gated_default.clarification_questions) == 4
    assert gated_ui.needs_user_clarification is True and gated_ui.clarification_questions == [MISSING_SUCCESS_MESSAGE_QUESTION, MISSING_ERROR_MESSAGE_QUESTION]
    print("  -> First-pass behaviour (prior_questions omitted) remains byte-identical to before this fix!")

    # 2. Fabricated-message linter check: message bịa đặt bị Critical-flag, message có căn cứ thì sạch
    msg = "Giao dịch của bạn đã bị từ chối do hệ thống đang khóa"
    fab_tc = TestCase(testcase_id="TC 01", title="Rút tiền bị chặn (AC-01)", note="Trace: AC-01",
                       expected_result='HTTP 400, message "' + msg + '"')
    fab_analysis = RequirementAnalysis(acceptance_criteria=[AcceptanceCriterion(ac_id="AC-01", title="Chặn rút tiền EOD")])
    bad = [i for i in lint_test_suite_coverage(fab_analysis, [fab_tc], raw_content="Chặn rút tiền trong giờ EOD, trả HTTP 400.")
           if i.issue_type == "Fabricated Message / Ungrounded Value"]
    assert len(bad) == 1 and bad[0].severity == "Critical" and bad[0].target_tc_id == "TC 01", bad
    good = [i for i in lint_test_suite_coverage(fab_analysis, [fab_tc], raw_content='Khi bị chặn, hiển thị message "' + msg + '".')
            if i.issue_type == "Fabricated Message / Ungrounded Value"]
    assert good == [], good
    assert [i for i in lint_test_suite_coverage(fab_analysis, [fab_tc]) if i.issue_type == "Fabricated Message / Ungrounded Value"] == []
    print("  -> Fabricated-message linter check flags invented messages Critical and clears grounded ones!")

    # 3. Generator marker invariant: PENDING CLARIFICATION marker without a question synthesizes one
    gen_analysis = RequirementAnalysis(feature_name="Chặn rút tiền EOD", acceptance_criteria=[AcceptanceCriterion(ac_id="AC-01")])
    gen_scenarios = [TestScenario(scenario_id="SC_01", trace_ac_id="AC-01", group_feature="1. Chặn EOD", group_functional="1.1. Luồng chính")]
    marked_tc = TestCase(testcase_id="TC 01", title="Rút tiền bị chặn", expected_result="HTTP 400", note="AC-01 | PENDING CLARIFICATION")
    with patch("src.agents.testcase_generator.invoke_structured_llm") as mock_gen:
        mock_gen.return_value = BatchTestSuiteResponse(test_cases=[marked_tc], clarification_questions=[])
        gen_result = generate_test_cases(gen_analysis, gen_scenarios, provider="gemini")
    assert len(gen_result.clarification_questions) == 1, gen_result.clarification_questions
    print("  -> Generator marker invariant: PENDING CLARIFICATION without a question synthesizes one!")


def test_gate_status_reporting():
    """
    Kiểm chứng bug đã sửa: lý do CHƯA ĐẠT Quality Gate hiển thị cho User (CLI/Slack) phải khớp ĐÚNG
    điều kiện gate thật (score >= min_review_score VÀ không Critical/Major), KHÔNG được hardcode
    "Score X/100 < 95" trong khi X đã >= ngưỡng cấu hình và lý do thật là còn issue Critical/Major.
    """
    print("\n[10/10] Testing QA Gate Status Reporting (Score vs. Critical/Major reasons)...")
    from src.agents.reviewer import gate_failure_reasons

    min_score = load_qa_rules()["min_review_score"]

    # 1. Score đạt ngưỡng nhưng còn issue Critical -> lý do phải là Critical, TUYỆT ĐỐI KHÔNG được nói "Score < ngưỡng"
    high_score_critical = ReviewResult(
        passed=False, score=min_score + 1,
        issues=[ReviewIssue(target_tc_id="TC 01", issue_type="X", severity="Critical", description="d")]
    )
    reasons = gate_failure_reasons(high_score_critical)
    assert any("Critical" in r for r in reasons), reasons
    assert not any("chưa đạt ngưỡng" in r for r in reasons), reasons

    # 2. Score dưới ngưỡng, không issue nặng -> lý do phải là Score, đúng số min_score cấu hình (không hardcode 95)
    low_score_clean = ReviewResult(passed=False, score=min_score - 5, issues=[])
    reasons2 = gate_failure_reasons(low_score_clean)
    assert reasons2 == [f"Score {min_score - 5}/100 chưa đạt ngưỡng {min_score}/100"], reasons2

    # 3. Đạt cả điểm lẫn không issue nặng -> không còn lý do nào
    assert gate_failure_reasons(ReviewResult(passed=True, score=min_score, issues=[])) == []
    print(f"  -> gate_failure_reasons() correctly attributes FAILED to Critical/Major issues (not a false score threshold), using live min_review_score={min_score}!")


class FakeSlackClient:
    def __init__(self):
        self.posted = []
        self.updates = []
        self.uploads = []
    def chat_postMessage(self, **kwargs):
        self.posted.append(kwargs)
        return {"ts": f"{len(self.posted)}.000"}
    def chat_update(self, **kwargs):
        self.updates.append(kwargs)
        return {"ts": kwargs.get("ts")}
    def files_upload_v2(self, **kwargs):
        self.uploads.append(kwargs)


def _patch_pipeline(analyze, scenarios=None, generate=None, review=None, export=None):
    """Patch các Agent bên trong LangGraph pipeline (src.core.workflow) + Agent của engine hội thoại."""
    from unittest.mock import patch
    from contextlib import ExitStack
    from src.agents.testcase_generator import TestCaseGenerationResult
    stack = ExitStack()
    stack.enter_context(patch("src.core.workflow.analyze_requirements", side_effect=analyze))
    stack.enter_context(patch("src.core.conversation.analyze_requirements", side_effect=analyze))
    stack.enter_context(patch("src.core.workflow.design_test_scenarios",
                              return_value=scenarios or [TestScenario(scenario_id="SC-01", scenario_title="x", technique="EP")]))
    stack.enter_context(patch("src.core.workflow.generate_test_cases", side_effect=generate or (
        lambda **kw: TestCaseGenerationResult(test_cases=[TestCase(testcase_id="TC 01", title="x")], clarification_questions=[])
    )))
    review_fn = review or (lambda **kw: ReviewResult(passed=True, score=100))
    stack.enter_context(patch("src.core.workflow.review_and_lint_test_suite", side_effect=review_fn))
    stack.enter_context(patch("src.core.conversation.review_and_lint_test_suite", side_effect=review_fn))
    export_fn = export or (lambda **kw: None)
    stack.enter_context(patch("src.core.workflow.export_test_cases_to_excel", side_effect=export_fn))
    stack.enter_context(patch("src.core.conversation.export_test_cases_to_excel", side_effect=export_fn))
    return stack


def test_slack_thread_context_memory():
    """
    Agent hỏi lại User trong Slack thread (thiếu API sample) rồi User trả lời ngắn gọn trong thread ->
    câu trả lời PHẢI được ghép đúng câu hỏi, gộp vào ticket gốc dưới dạng User Clarifications (không bị
    coi là yêu cầu mới rồi bị Guardrail chặn), và phiên được GIỮ LẠI sau khi sinh xong để User tiếp tục
    bổ sung/feedback trong cùng thread.
    """
    print("\n[11/11] Testing Slack Thread Session Memory (Clarification Answer Merged Into Original Ticket)...")
    from unittest.mock import patch
    import src.integrations.slack_bot as slack_bot
    from src.core.session import UserTurn
    from src.core.models import ClarificationAnswer
    from src.agents.turn_interpreter import UserTurnInterpretation

    slack_bot._sessions.clear()
    client = FakeSlackClient()
    session_key = "C123:111.111"
    question = "Vui lòng cung cấp API sample (request/response) cho tính năng này."
    original_ticket_text = (
        "Yeu cau nghiep vu Chuyen tien nhanh Napas hai bon bay: khach hang ca nhan chuyen tien den "
        "so tai khoan ngan hang khac. AC1 so tien toi thieu 10000 toi da 499999999 VND moi giao dich."
    )

    analyze_calls = []
    def fake_analyze_requirements(raw_content, **kwargs):
        analyze_calls.append((raw_content, kwargs.get("prior_clarification_questions")))
        if len(analyze_calls) == 1:
            return RequirementAnalysis(feature_name="Chuyen tien Napas", needs_user_clarification=True, clarification_questions=[question])
        return RequirementAnalysis(feature_name="Chuyen tien Napas", needs_user_clarification=False)

    interpreter_inputs = []
    def fake_interpret(message, open_questions, **kwargs):
        interpreter_inputs.append((message, list(open_questions)))
        return UserTurnInterpretation(answers=[ClarificationAnswer(question=question, answer="KHÔNG CÓ API")])

    with _patch_pipeline(fake_analyze_requirements), \
         patch("src.core.conversation.interpret_user_turn", side_effect=fake_interpret):
        slack_bot.dispatch_turn(client, "C123", "111.111", session_key, UserTurn(text=original_ticket_text), background=False)
        session = slack_bot._sessions.get(session_key)
        assert session is not None and session.awaiting_user and session.open_questions == [question]
        assert not session.suite_ready

        slack_bot.dispatch_turn(client, "C123", "111.111", session_key, UserTurn(text="KHÔNG CÓ API"), background=False)

    assert len(analyze_calls) == 2, f"Expected exactly 2 analysis calls (original + answered), got {len(analyze_calls)}"
    assert interpreter_inputs == [("KHÔNG CÓ API", [question])], "The open question must be handed to the interpreter to pair the answer!"
    second_raw, second_prior = analyze_calls[1]
    assert "Napas" in second_raw, "Original ticket content was lost on the clarification reply round!"
    assert f"- Hỏi: {question}\n  User trả lời: KHÔNG CÓ API" in second_raw, "Answer must be merged as a Q/A pair under User Clarifications!"
    assert second_prior == [question], "Previously asked questions must be passed to the analyst so it does not re-ask them!"
    assert session.suite_ready and not session.awaiting_user
    assert slack_bot._sessions.get(session_key) is session, "Session must persist after the suite is delivered (for later feedback)!"
    print("  -> Short free-form answer paired with its question, merged into the original ticket; session kept for follow-ups!")


def test_slack_gate_failure_visibility():
    """
    1. Vòng lặp Feedback Loop đọc `max_review_iterations` LIVE từ config.yaml (qua `load_qa_rules()`).
    2. Quality Gate CHƯA ĐẠT sau khi hết vòng lặp -> tin nhắn tổng hợp trên Slack PHẢI liệt kê chi tiết
       issue Critical/Major (Target TC, đề xuất sửa) để User biết cần sửa/hỏi gì.
    """
    print("\n[12/12] Testing Slack Quality Gate Failure Visibility (Config-Driven Retries & Issue Detail)...")
    import src.integrations.slack_bot as slack_bot
    from src.core.session import UserTurn
    from src.agents.testcase_generator import TestCaseGenerationResult

    slack_bot._sessions.clear()
    expected_max_iter = load_qa_rules()["max_review_iterations"]
    client = FakeSlackClient()
    gen_calls = []

    def fake_generate_test_cases(**kwargs):
        gen_calls.append(1)
        return TestCaseGenerationResult(test_cases=[TestCase(testcase_id="TC 01", title="x")], clarification_questions=[])

    stuck_issue = ReviewIssue(target_tc_id="TC 01", severity="Major", issue_type="Business Logic Gap",
                               description="Chua ro PIB bypass co dung tiep han muc OD hay khong",
                               suggested_fix="Lam ro quy tac tuong tac giua Blockade va OD")

    with _patch_pipeline(lambda raw_content, **kw: RequirementAnalysis(feature_name="Bypass Phong toa"),
                         generate=fake_generate_test_cases,
                         review=lambda **kw: ReviewResult(passed=False, score=96, issues=[stuck_issue])):
        slack_bot.dispatch_turn(client, "C123", "222.222", "C123:222.222",
                                UserTurn(text="Yeu cau nghiep vu Bypass phong toa CASA/OD"), background=False)

    assert len(gen_calls) == expected_max_iter, f"Expected exactly {expected_max_iter} generation attempts (config-driven), got {len(gen_calls)}"

    summary_calls = [p for p in client.posted if "blocks" in p]
    assert len(summary_calls) == 1, "Expected exactly 1 final summary message with Block Kit blocks"
    all_block_text = " ".join(
        b.get("text", {}).get("text", "")
        for p in summary_calls for b in p["blocks"] if b.get("type") == "section"
    )
    assert "TC 01" in all_block_text and "Lam ro quy tac tuong tac" in all_block_text, \
        "Unresolved Major issue detail (target TC + suggested fix) must be visible in the Slack summary!"
    print("  -> Feedback loop uses config-driven max_review_iterations, and unresolved Major issue detail is surfaced in Slack summary!")



def test_raw_content_grounding():
    """
    Kiểm chứng bug cố định: tài liệu gốc (raw_content) do User cung cấp phải được nhúng
    nguyên văn vào prompt của Scenario Designer và Test Case Generator, không chỉ dựa vào
    bản tóm tắt Requirement Analysis - để tránh Agent tự bịa field/API sample không có trong tài liệu.
    """
    print("\n[13/13] Testing Raw-Content Grounding (Scenario Designer & Test Case Generator)...")
    from unittest.mock import patch
    from src.agents.scenario_designer import design_test_scenarios, ScenarioListResponse
    from src.agents.testcase_generator import generate_test_cases, BatchTestSuiteResponse

    analysis = RequirementAnalysis(feature_name="X", banking_domain="Y")
    sentinel = "SENTINEL_RAW_DOC_MARKER_curl -X POST /napas/transfer -d amount=499999000"

    with patch("src.agents.scenario_designer.invoke_structured_llm") as mock_sc:
        mock_sc.return_value = ScenarioListResponse(scenarios=[TestScenario(scenario_id="SC-01", scenario_title="x", technique="EP")])
        design_test_scenarios(analysis, raw_content=sentinel, provider="gemini")
        assert sentinel in mock_sc.call_args.kwargs["user_prompt"], "Scenario Designer prompt did not include the raw source document!"

    with patch("src.agents.testcase_generator.invoke_structured_llm") as mock_gen:
        mock_gen.return_value = BatchTestSuiteResponse(test_cases=[TestCase(testcase_id="TC 01", title="x")])
        generate_test_cases(analysis, [TestScenario(scenario_id="SC-01", scenario_title="x", technique="EP")], raw_content=sentinel, provider="gemini")
        assert sentinel in mock_gen.call_args.kwargs["user_prompt"], "Test Case Generator prompt did not include the raw source document!"

    print("  -> Both agents forward the raw source document verbatim into their LLM prompts!")

def test_llm_request_timeout():
    """
    Kiểm chứng bug cố định: trước đây get_llm() không set timeout cho bất kỳ Provider nào, nên nếu
    Provider không phản hồi (không phải lỗi 429 rate-limit), lệnh gọi treo VÔ THỜI HẠN và không có cơ
    chế retry/backoff nào can thiệp được (vì không exception nào được raise ra để bắt).
    Nay get_llm() PHẢI luôn set timeout mặc định từ config.yaml (`model.request_timeout_seconds`),
    và invoke_structured_llm() PHẢI tự động retry khi gặp lỗi timeout rồi raise rõ ràng nếu vẫn treo
    sau khi hết lượt retry - tuyệt đối không được treo vô thời hạn.
    """
    print("\n[14/14] Testing LLM Request Timeout (Provider Hang Prevention)...")
    from unittest.mock import patch, MagicMock
    from src.core import llm as llm_module

    default_timeout = llm_module.load_config()["model"]["request_timeout_seconds"]

    # 1. get_llm() phải luôn set timeout mặc định từ config.yaml cho MỌI provider (không None).
    google_llm = llm_module.get_llm(provider="gemini", api_key="x")
    assert google_llm.timeout == default_timeout, "Provider Google phải nhận timeout mặc định từ config.yaml!"
    openai_llm = llm_module.get_llm(provider="openai", api_key="x")
    assert openai_llm.request_timeout == default_timeout, "Provider OpenAI-compatible phải nhận timeout mặc định!"
    anthropic_llm = llm_module.get_llm(provider="anthropic", api_key="x")
    assert anthropic_llm.default_request_timeout == default_timeout, "Provider Anthropic phải nhận timeout mặc định!"

    # Override tường minh vẫn phải được tôn trọng.
    custom_llm = llm_module.get_llm(provider="gemini", api_key="x", request_timeout=7)
    assert custom_llm.timeout == 7, "request_timeout override phải được áp dụng đúng!"

    # 2. invoke_structured_llm() phải tự retry khi gặp lỗi timeout, thay vì raise/treo ngay lần đầu.
    class FlakyStructuredLLM:
        def __init__(self):
            self.call_count = 0
        def invoke(self, messages):
            self.call_count += 1
            if self.call_count == 1:
                raise TimeoutError("Deadline Exceeded: request timed out")
            return ReviewResult(passed=True, score=99)

    flaky = FlakyStructuredLLM()
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = flaky

    with patch.object(llm_module, "get_llm", return_value=fake_llm), \
         patch.object(llm_module.time, "sleep", return_value=None):
        result = llm_module.invoke_structured_llm(
            system_prompt="sys", user_prompt="usr", schema=ReviewResult, provider="gemini", max_retries=3
        )
    assert result.score == 99 and flaky.call_count == 2, "invoke_structured_llm phải tự retry khi gặp lỗi timeout, không được raise ngay lập tức!"

    # 3. Nếu timeout xảy ra liên tục hết cả max_retries -> PHẢI raise rõ ràng, không được treo vô thời hạn.
    class AlwaysTimeoutLLM:
        def invoke(self, messages):
            raise TimeoutError("Read timed out")

    always_timeout_llm = MagicMock()
    always_timeout_llm.with_structured_output.return_value = AlwaysTimeoutLLM()
    with patch.object(llm_module, "get_llm", return_value=always_timeout_llm), \
         patch.object(llm_module.time, "sleep", return_value=None):
        try:
            llm_module.invoke_structured_llm(system_prompt="sys", user_prompt="usr", schema=ReviewResult, provider="gemini", max_retries=2)
            assert False, "Phải raise lỗi timeout sau khi hết max_retries, tuyệt đối không được treo vô thời hạn!"
        except TimeoutError:
            pass

    print("  -> get_llm() luôn set request timeout cho mọi Provider; invoke_structured_llm() tự retry rồi raise rõ ràng thay vì treo vô thời hạn!")


def test_batch_multi_group_processing():
    """
    Kiểm chứng run.py --batch: mỗi nhóm nguồn (1 tham số vị trí; dấu phẩy BÊN TRONG nó gộp thêm
    tài liệu bổ sung CHỈ thuộc về CHÍNH ticket đó) phải chạy qua process_requirement_group() hoàn
    toàn ĐỘC LẬP - sinh RequirementAnalysis/output riêng biệt, KHÔNG để lọt tài liệu bổ sung của
    nhóm này sang nhóm khác (đây là yêu cầu cốt lõi: gán tài liệu -> ticket phải tường minh, xác
    định 100% từ cấu trúc argv, không suy đoán) - và một nhóm lỗi (Guardrail reject) không được
    phép chặn các nhóm còn lại hoàn tất.
    """
    print("\n[15/15] Testing --batch Multi-Group Processing (Deterministic Doc-to-Ticket Mapping, Zero Cross-Contamination, Partial-Failure Isolation)...")
    import argparse
    import tempfile
    from unittest.mock import patch
    import run
    from src.integrations.jira_connector import JiraConnector, extract_jira_key
    from src.agents.scenario_designer import ScenarioListResponse
    from src.agents.testcase_generator import BatchTestSuiteResponse
    from src.agents.reviewer import SemanticReviewPayload

    tmpdir = tempfile.mkdtemp(prefix="qa_batch_test_")
    doc_a_path = os.path.join(tmpdir, "supplement_a.md")
    doc_b_path = os.path.join(tmpdir, "supplement_b.md")
    with open(doc_a_path, "w", encoding="utf-8") as f:
        f.write("# Tai lieu bo sung rieng cho Ticket A\nSUPPLEMENT_A_ONLY_FIELD: accountNumber123")
    with open(doc_b_path, "w", encoding="utf-8") as f:
        f.write("# Tai lieu bo sung rieng cho Ticket B\nSUPPLEMENT_B_ONLY_FIELD: cardNumber456")

    def _fake_fetch_issue(issue_key_or_url):
        key = extract_jira_key(issue_key_or_url) or issue_key_or_url
        # Waiver "KHÔNG CÓ API, KHÔNG CÓ MESSAGE" tránh Clarification Gate (Node 1) chặn pipeline
        # lại giữa chừng vì thiếu API sample / message - không liên quan tới điều đang test ở đây.
        if key == "VWCBT-9001":
            return {
                "key": "VWCBT-9001", "summary": "Feature A ticket",
                "jira_url": "https://example.atlassian.net/browse/VWCBT-9001",
                "formatted_requirement": "Yeu cau nghiep vu Chuyen tien nhanh Feature A. MARKER_A_JIRA_ONLY. KHÔNG CÓ API, KHÔNG CÓ MESSAGE.",
            }
        if key == "VWCBT-9002":
            return {
                "key": "VWCBT-9002", "summary": "Feature B ticket",
                "jira_url": "https://example.atlassian.net/browse/VWCBT-9002",
                "formatted_requirement": "Yeu cau nghiep vu Rut tien Feature B. MARKER_B_JIRA_ONLY. KHÔNG CÓ API, KHÔNG CÓ MESSAGE.",
            }
        raise AssertionError(f"Unexpected Jira key requested in test: {issue_key_or_url}")

    analyst_prompts = []

    def _fake_analyst_llm(**kwargs):
        prompt = kwargs.get("user_prompt", "")
        analyst_prompts.append(prompt)
        if "MARKER_A_JIRA_ONLY" in prompt:
            feature = "FeatureA_ChuyenTien"
        elif "MARKER_B_JIRA_ONLY" in prompt:
            feature = "FeatureB_RutTien"
        else:
            feature = "FeatureUnknown"
        return RequirementAnalysis(
            feature_name=feature,
            banking_domain="Payments & Fund Transfers (Napas, VietQR, Swift)",
            acceptance_criteria=[AcceptanceCriterion(ac_id="AC-01", title=f"AC for {feature}")],
            needs_user_clarification=False,
        )

    def _fake_scenario_llm(**kwargs):
        return ScenarioListResponse(scenarios=[TestScenario(scenario_id="SC-01", scenario_title="Scenario chuan", technique="EP")])

    def _fake_gen_llm(**kwargs):
        return BatchTestSuiteResponse(test_cases=[TestCase(testcase_id="TC 01", title="Test case chuan", expected_result="OK")], clarification_questions=[])

    def _fake_review_llm(**kwargs):
        return SemanticReviewPayload(semantic_score=100, traceability_matrix=[], semantic_issues=[], feedback_summary="Dat chuan")

    fake_args = argparse.Namespace(
        provider="google", model="gemini-3.6-flash", base_url=None, api_key=None,
        app=None, version=None, jira=None, sheet=None, template=None,
        output=None, max_iter=1, extra_info=None, batch=True, inputs=[]
    )

    # Nhóm giữa (fail) mô phỏng lỗi Guardrail reject để chứng minh cách ly lỗi từng nhóm.
    groups = [
        ["VWCBT-9001", doc_a_path],
        ["hi"],
        ["VWCBT-9002", doc_b_path],
    ]

    with patch.object(JiraConnector, "fetch_issue", side_effect=_fake_fetch_issue), \
         patch("src.agents.requirement_analyst.invoke_structured_llm", side_effect=_fake_analyst_llm), \
         patch("src.agents.scenario_designer.invoke_structured_llm", side_effect=_fake_scenario_llm), \
         patch("src.agents.testcase_generator.invoke_structured_llm", side_effect=_fake_gen_llm), \
         patch("src.agents.reviewer.invoke_structured_llm", side_effect=_fake_review_llm):
        results = [run.process_requirement_group(list(g), fake_args, f"Test Group {i + 1}") for i, g in enumerate(groups)]

    res_a, res_fail, res_b = results

    # 1. Group A & B đều hoàn thành, sinh feature_name & output path RIÊNG BIỆT cho mỗi ticket.
    assert res_a["error"] is None, res_a
    assert res_b["error"] is None, res_b
    assert res_a["feature_name"] == "FeatureA_ChuyenTien", res_a
    assert res_b["feature_name"] == "FeatureB_RutTien", res_b
    assert res_a["feature_name"] != res_b["feature_name"]
    assert res_a["output_excel_path"] and res_b["output_excel_path"]
    assert res_a["output_excel_path"] != res_b["output_excel_path"]
    assert os.path.exists(res_a["output_excel_path"])
    assert os.path.exists(res_b["output_excel_path"])
    print(f"  -> Group A -> '{res_a['feature_name']}' ({res_a['output_excel_path']}); "
          f"Group B -> '{res_b['feature_name']}' ({res_b['output_excel_path']}): distinct outputs confirmed!")

    # 2. Nhóm lỗi (Guardrail reject) bị cách ly, KHÔNG chặn 2 nhóm còn lại hoàn tất.
    assert res_fail["error"] is not None, res_fail
    assert res_fail["feature_name"] is None and res_fail["output_excel_path"] is None
    print(f"  -> Simulated Guardrail failure isolated to its own group ('{res_fail['error']}'); other groups still completed!")

    # 3. ZERO cross-contamination: đúng 2 lần gọi Analyst LLM (Group A & B; nhóm fail bị chặn ở
    #    Guardrail nên KHÔNG hề gọi tới LLM/Jira), và tài liệu bổ sung + nội dung Jira của nhóm này
    #    tuyệt đối KHÔNG xuất hiện trong prompt phân tích của nhóm kia.
    assert len(analyst_prompts) == 2, f"Expected exactly 2 Analyst LLM calls (A & B only), got {len(analyst_prompts)}"
    prompt_a, prompt_b = analyst_prompts
    assert "MARKER_A_JIRA_ONLY" in prompt_a and "SUPPLEMENT_A_ONLY_FIELD" in prompt_a
    assert "MARKER_B_JIRA_ONLY" not in prompt_a and "SUPPLEMENT_B_ONLY_FIELD" not in prompt_a, \
        "Cross-contamination detected: Group B's ticket/document leaked into Group A's analysis prompt!"
    assert "MARKER_B_JIRA_ONLY" in prompt_b and "SUPPLEMENT_B_ONLY_FIELD" in prompt_b
    assert "MARKER_A_JIRA_ONLY" not in prompt_b and "SUPPLEMENT_A_ONLY_FIELD" not in prompt_b, \
        "Cross-contamination detected: Group A's ticket/document leaked into Group B's analysis prompt!"
    print("  -> Doc-to-ticket mapping is 100% deterministic from argv structure: zero cross-group document contamination confirmed!")


def test_slack_batch_parse_groups():
    """
    Kiểm chứng `parse_batch_groups()` - quy ước Batch Mode gốc Slack (`--batch` + xuống dòng theo
    nhóm + ` | ` theo nguồn trong nhóm). Đây là quy ước NATIVE cho Slack, khác quy ước argv của CLI
    (`run.py --batch`) vì shell quoting để giữ 1 token liền mạch qua khoảng trắng không áp dụng được
    cho text phẳng của Slack - ghi chú bổ sung tiếng Việt tự nhiên thường xuyên chứa CẢ khoảng trắng
    LẪN dấu phẩy, nên dấu phẩy không thể tái sử dụng làm ký tự phân tách trong nhóm mà không có nguy
    cơ tách nhầm 1 ghi chú văn xuôi thành các nhóm giả.
    """
    print("\n[16/16] Testing Slack `--batch` Message Parsing (Newline-per-Group + Pipe-per-Source Convention)...")
    from src.integrations.slack_bot import parse_batch_groups

    # 1. Tin nhắn không bắt đầu bằng `--batch` (không phân biệt hoa/thường) -> KHÔNG kích hoạt Batch
    #    Mode, trả về rỗng để caller giữ nguyên 100% hành vi yêu cầu đơn hiện tại.
    assert parse_batch_groups("VWCBT-3800 cần chú ý OTP") == []
    assert parse_batch_groups("") == []
    assert parse_batch_groups("   ") == []
    assert parse_batch_groups(None) == []

    # 2. Ví dụ đúng theo đặc tả: ghi chú bổ sung CHỨA DẤU PHẨY ("cần chú ý thêm luồng OTP, ưu tiên
    #    kiểm tra timeout") của dòng 1 PHẢI được giữ nguyên làm 1 nguồn DUY NHẤT thuộc về ĐÚNG dòng
    #    (nhóm) đó - dấu phẩy bên trong ghi chú không được phép tách nhầm thành nhóm giả.
    raw = (
        "--batch\n"
        "VWCBT-3800 | cần chú ý thêm luồng OTP, ưu tiên kiểm tra timeout\n"
        "VWCBT-3801\n"
        "VWCBT-3802 | ưu tiên kiểm tra rollback\n"
    )
    groups = parse_batch_groups(raw)
    assert len(groups) == 3, f"Expected exactly 3 independent groups (1 per line), got {len(groups)}: {groups}"
    assert groups[0] == ["VWCBT-3800", "cần chú ý thêm luồng OTP, ưu tiên kiểm tra timeout"], groups[0]
    assert groups[1] == ["VWCBT-3801"], groups[1]
    assert groups[2] == ["VWCBT-3802", "ưu tiên kiểm tra rollback"], groups[2]

    # 3. Trigger không phân biệt hoa/thường + khoảng trắng thừa quanh `--batch`/dòng trống bị bỏ qua.
    groups_ci = parse_batch_groups("  --BATCH  \nA | b, c\n\n  D | e\n")
    assert groups_ci == [["A", "b, c"], ["D", "e"]], groups_ci

    # 4. Hai dòng/nhóm khác nhau tuyệt đối KHÔNG chia sẻ nội dung với nhau (mỗi list độc lập).
    assert groups[0] is not groups[1]
    assert groups[0][0] != groups[2][0]
    assert "OTP" not in groups[2][0] and "OTP" not in "".join(groups[2])
    assert "rollback" not in "".join(groups[0])

    print("  -> `--batch` trigger + newline-per-group + ` | `-per-source convention verified: comma-laden notes stay attached to their own single group, zero ambiguity!")


def test_slack_batch_multi_group_processing():
    """
    Kiểm chứng `run_batch_workflow_in_background()`: mỗi nhóm (1 dòng sau `--batch`, nguồn tách bằng
    ` | `) chạy trong 1 phiên hội thoại riêng hoàn toàn ĐỘC LẬP - ghi chú riêng chứa dấu phẩy (gắn vào
    đúng dòng của nó qua ` | `) không được rò rỉ sang nhóm khác (zero cross-contamination), và 1 nhóm
    lỗi (nội dung quá ngắn) không được phép chặn các nhóm còn lại hoàn tất.
    """
    print("\n[17/21] Testing Slack `run_batch_workflow_in_background` (Zero Cross-Group Contamination, Partial-Failure Isolation)...")
    import src.integrations.slack_bot as slack_bot

    slack_bot._sessions.clear()
    slack_bot._batch_threads.clear()

    raw_text = (
        "--batch\n"
        "VWCBT-8801 tinh nang thanh toan | ghi chu rieng cho nhom 1, uu tien kiem tra OTP timeout MARKER_GROUP1_ONLY\n"
        "hi\n"
        "VWCBT-8802 tinh nang rut tien | ghi chu rieng cho nhom 2 MARKER_GROUP2_ONLY\n"
    )
    groups = slack_bot.parse_batch_groups(raw_text)
    assert len(groups) == 3, groups

    client = FakeSlackClient()
    analyst_prompts = []

    def fake_analyze_requirements(raw_content, **kwargs):
        analyst_prompts.append(raw_content)
        if "MARKER_GROUP1_ONLY" in raw_content:
            feature = "FeatureGroup1_ThanhToan"
        elif "MARKER_GROUP2_ONLY" in raw_content:
            feature = "FeatureGroup2_RutTien"
        else:
            feature = "FeatureUnknown"
        return RequirementAnalysis(feature_name=feature, needs_user_clarification=False)

    with _patch_pipeline(fake_analyze_requirements, export=lambda **kw: "/tmp/fake_batch_output.xlsx"):
        slack_bot.run_batch_workflow_in_background(client, "C999", "555.555", groups)

    # 1. Đúng 2 lần gọi Analyst LLM (nhóm giữa "hi" bị chặn vì nội dung quá ngắn TRƯỚC khi tới Node 1)
    #    và ghi chú/tài liệu của nhóm này KHÔNG rò rỉ sang prompt của nhóm kia.
    assert len(analyst_prompts) == 2, f"Expected exactly 2 Analyst LLM calls (Group 1 & 2 only), got {len(analyst_prompts)}"
    prompt_1, prompt_2 = analyst_prompts
    assert "MARKER_GROUP1_ONLY" in prompt_1 and "ghi chu rieng cho nhom 1" in prompt_1
    assert "MARKER_GROUP2_ONLY" not in prompt_1 and "ghi chu rieng cho nhom 2" not in prompt_1, \
        "Cross-contamination detected: Group 2's ticket/note leaked into Group 1's analysis prompt!"
    assert "MARKER_GROUP2_ONLY" in prompt_2 and "ghi chu rieng cho nhom 2" in prompt_2
    assert "MARKER_GROUP1_ONLY" not in prompt_2 and "ghi chu rieng cho nhom 1" not in prompt_2, \
        "Cross-contamination detected: Group 1's ticket/note leaked into Group 2's analysis prompt!"

    # 2. Nhóm lỗi bị cách ly; tin nhắn tổng kết liệt kê đủ 3 nhóm với đúng trạng thái.
    def is_aggregate_summary(msg):
        return "blocks" in msg and any(
            b.get("type") == "header" and "TỔNG KẾT BATCH" in b.get("text", {}).get("text", "")
            for b in msg["blocks"]
        )
    final_summary = [p for p in client.posted if is_aggregate_summary(p)]
    assert len(final_summary) == 1, f"Expected exactly 1 final aggregate summary message with Block Kit blocks, got {len(final_summary)}"
    summary_text = " ".join(
        b.get("text", {}).get("text", "") for b in final_summary[0]["blocks"] if b.get("type") == "section"
    )
    assert "FeatureGroup1_ThanhToan" in summary_text and "FeatureGroup2_RutTien" in summary_text
    assert "VWCBT-8801" in summary_text and "VWCBT-8802" in summary_text
    assert "*g2*" in summary_text and "quá ngắn" in summary_text, \
        "Failed middle group (no Jira key resolvable) must be listed under its fallback group_key ('g2') with its error!"
    assert final_summary[0]["text"].startswith("✅ 2/3"), final_summary[0]["text"]
    assert slack_bot._get_batch_groups("C999:555.555") == ["VWCBT-8801", "g2", "VWCBT-8802"]
    print("  -> Batch groups processed in isolated sessions; middle group's failure isolated from the other two!")


def test_slack_batch_pending_clarification_disambiguation():
    """
    Hai nhóm batch CÙNG dừng lại hỏi User trong CÙNG 1 thread -> cả 2 phiên phải chờ User riêng biệt;
    câu trả lời sau đó PHẢI được định tuyến CHÍNH XÁC theo mã ticket nhắc lại (chỉ phiên của nhóm đó
    nhận câu trả lời, nhóm kia giữ nguyên), và nếu không nhắc mã ticket nào trong khi còn >=2 nhóm chờ
    thì PHẢI trả về None (hỏi lại) - KHÔNG BAO GIỜ đoán bừa hay gộp nhầm sang nhóm không liên quan.
    """
    print("\n[18/21] Testing Slack Batch Multi-Group Pending-Clarification Disambiguation (Zero Silent Drop/Merge)...")
    from unittest.mock import patch
    import src.integrations.slack_bot as slack_bot
    from src.core.session import UserTurn
    from src.core.models import ClarificationAnswer
    from src.agents.turn_interpreter import UserTurnInterpretation

    slack_bot._sessions.clear()
    slack_bot._batch_threads.clear()

    channel_id, thread_ts = "C777", "666.666"
    thread_key = f"{channel_id}:{thread_ts}"
    question = "Vui lòng cung cấp API sample (request/response)."
    client = FakeSlackClient()
    groups = [["VWCBT-9101 chuyen tien nhanh"], ["VWCBT-9102 rut tien ATM"]]

    def analyze(raw_content, **kwargs):
        answered = "User trả lời" in raw_content
        return RequirementAnalysis(feature_name="Batch", needs_user_clarification=not answered,
                                   clarification_questions=[] if answered else [question])

    with _patch_pipeline(analyze), \
         patch("src.core.conversation.interpret_user_turn",
               return_value=UserTurnInterpretation(answers=[ClarificationAnswer(question=question, answer="KHÔNG CÓ API")])):
        slack_bot.run_batch_workflow_in_background(client, channel_id, thread_ts, groups)

        group_keys = slack_bot._get_batch_groups(thread_key)
        def awaiting():
            return [g for g in group_keys if slack_bot._sessions.get(f"{thread_key}:{g}").awaiting_user]
        assert set(awaiting()) == {"VWCBT-9101", "VWCBT-9102"}, f"Expected both groups awaiting the user, got {awaiting()}"

        # 1. 2 nhóm cùng chờ + reply không nhắc mã -> mơ hồ, không đoán.
        assert slack_bot.resolve_batch_reply_group_key(group_keys, "toi da tra loi roi, khong co API nao ca", awaiting()) is None

        # 2. Reply nhắc ĐÚNG mã 1 ticket -> chỉ phiên đó nhận câu trả lời & sinh bộ test case.
        matched = slack_bot.resolve_batch_reply_group_key(group_keys, "VWCBT-9101 KHÔNG CÓ API", awaiting())
        assert matched == "VWCBT-9101", f"Reply mentioning VWCBT-9101 must resolve to that exact group, got {matched!r}"
        slack_bot.dispatch_turn(client, channel_id, thread_ts, f"{thread_key}:{matched}",
                                UserTurn(text="VWCBT-9101 KHÔNG CÓ API"), group_label=matched, background=False)
        s1 = slack_bot._sessions.get(f"{thread_key}:VWCBT-9101")
        s2 = slack_bot._sessions.get(f"{thread_key}:VWCBT-9102")
        assert s1.suite_ready and not s1.awaiting_user
        assert s2.awaiting_user and not s2.answers and not s2.suite_ready, "The other group's session must stay untouched!"

        # 3. Chỉ còn đúng 1 nhóm chờ -> reply không nhắc mã được định tuyến về nhóm đó.
        assert awaiting() == ["VWCBT-9102"]
        assert slack_bot.resolve_batch_reply_group_key(group_keys, "KHÔNG CÓ API", awaiting()) == "VWCBT-9102"

    print("  -> Multi-group routing is deterministic: exact-match goes only to its own session, sole-awaiting default works, "
          "and 2+-way ambiguity is never guessed!")


def test_conversation_followup_updates_suite():
    """
    Sau khi đã giao bộ test case, User gửi feedback + trả lời câu hỏi còn mở trong cùng hội thoại (không
    gọi lại bot) -> Agent cập nhật TĂNG DẦN bộ hiện có (Reviser), review lại và xuất ĐÈ đúng file/sheet
    cũ; KHÔNG chạy lại toàn bộ pipeline. Tin nhắn đến khi worker đang chạy được xếp hàng và hấp thụ ngay
    trong lượt chạy đó, không mở worker thứ hai.
    """
    print("\n[19/21] Testing Conversational Follow-up (Incremental Revise, Same Excel, Mid-run Messages)...")
    from unittest.mock import patch
    from src.core.session import QASession, SessionOptions, UserTurn
    from src.core.conversation import run_session
    from src.core.models import ClarificationAnswer
    from src.agents.turn_interpreter import UserTurnInterpretation
    from src.agents.testcase_reviser import TestSuiteRevisionResult
    from src.agents.testcase_generator import TestCaseGenerationResult

    class Recorder:
        def __init__(self):
            self.events = []
        def progress(self, lines, new=False): pass
        def notify(self, text): self.events.append(("notify", text))
        def ask(self, session, questions, stage): self.events.append(("ask", stage, list(questions)))
        def deliver(self, session, outcome): self.events.append(("deliver", outcome.updated, list(outcome.change_summary)))
        def fail(self, session, text): self.events.append(("fail", text))

    pending_q = "Message lỗi khi vượt hạn mức là gì?"
    session = QASession(key="t", options=SessionOptions(llm_provider="gemini"))
    reporter = Recorder()
    exports, revise_calls, gen_calls = [], [], []
    mid_run = {"sent": False, "submit_result": None}

    def generate(**kw):
        gen_calls.append(1)
        # User nhắn thêm trong lúc Agent đang sinh -> xếp hàng vào worker đang chạy.
        if not mid_run["sent"]:
            mid_run["sent"] = True
            mid_run["submit_result"] = session.submit(UserTurn(text="thêm case hết hạn OTP"))
        return TestCaseGenerationResult(test_cases=[TestCase(testcase_id="TC 01", title="Chuyển tiền thành công")],
                                        clarification_questions=[pending_q])

    def interpret(message, open_questions, **kw):
        if message == "thêm case hết hạn OTP":
            return UserTurnInterpretation(testcase_feedback=["Thêm test case OTP hết hạn"])
        assert open_questions == [pending_q], open_questions
        return UserTurnInterpretation(answers=[ClarificationAnswer(question=pending_q, answer='"Vượt hạn mức ngày"')],
                                      testcase_feedback=["Đổi priority TC 01 thành Critical"])

    def revise(analysis, test_cases, instructions, **kw):
        revise_calls.append(list(instructions))
        tcs = list(test_cases) + [TestCase(testcase_id=f"TC {len(test_cases) + 1:02d}", title=f"Rev {len(revise_calls)}")]
        return TestSuiteRevisionResult(test_cases=tcs, clarification_questions=[], change_summary=[f"Rev {len(revise_calls)}"])

    def export(**kw):
        exports.append((kw.get("output_path"), kw.get("target_sheet_name")))
        return "/tmp/conv_suite.xlsx"

    with _patch_pipeline(lambda raw_content, **kw: RequirementAnalysis(feature_name="Chuyen tien"),
                         generate=generate, export=export), \
         patch("src.core.conversation.interpret_user_turn", side_effect=interpret), \
         patch("src.core.conversation.revise_test_cases", side_effect=revise):
        assert session.submit(UserTurn(text="Yeu cau nghiep vu chuyen tien noi bo, han muc 500 trieu/ngay")) is True
        run_session(session, reporter)

        # Lần chạy đầu: tin nhắn giữa chừng không mở worker mới, được áp dụng thành 1 lượt cập nhật.
        assert mid_run["submit_result"] is False, "Submitting while the worker runs must queue the turn, not start a 2nd worker!"
        assert len(gen_calls) == 1, f"Feedback mid-run must not regenerate the whole suite, got {len(gen_calls)} generations"
        assert [e[:2] for e in reporter.events if e[0] == "deliver"] == [("deliver", False), ("deliver", True)]
        assert any("OTP" in i for i in revise_calls[0])
        assert not session.awaiting_user and session.open_stage == "", session.open_questions
        sheet = exports[0][1]
        assert sheet, "Graph export must pass a sheet name"

        # Phiên vẫn sống: trả lời + feedback sau khi đã giao -> cập nhật tại chỗ.
        session.open_questions = [pending_q]
        assert session.submit(UserTurn(text='Vượt hạn mức: "Vượt hạn mức ngày". Đổi TC 01 sang Critical')) is True
        run_session(session, reporter)

    assert len(gen_calls) == 1, "Follow-up feedback must update the existing suite, not rerun the pipeline!"
    last_instr = revise_calls[-1]
    assert any("Vượt hạn mức ngày" in i for i in last_instr) and any("Critical" in i for i in last_instr), last_instr
    assert session.answers[-1].question == pending_q
    assert len(session.test_cases) == 3 and session.test_cases[-1].title == "Rev 2"
    assert exports[-1] == ("/tmp/conv_suite.xlsx", sheet), f"Revision must overwrite the same file & sheet, got {exports[-1]}"
    assert not session.running and session.error is None
    print("  -> Mid-run message queued & absorbed; follow-up answer/feedback revised the suite in place and re-exported to the same file!")


def test_apply_revision_merge():
    """Áp bản sửa của Reviser: sửa theo mã (chấp nhận 'TC1'/'tc 01'), xóa, thêm mới chèn đúng nhóm con, cập
    nhật mã không tồn tại coi như thêm mới; sau finalize, mã được đánh lại liên tục TC 01..N."""
    print("\n[20/21] Testing Incremental Revision Merge (update/remove/add placement & renumbering)...")
    from src.agents.testcase_reviser import apply_revision, TestSuiteRevision
    from src.agents.testcase_generator import finalize_test_suite

    suite = [
        TestCase(testcase_id="TC 01", group_functional="1.1. A", title="a1"),
        TestCase(testcase_id="TC 02", group_functional="1.1. A", title="a2"),
        TestCase(testcase_id="TC 03", group_functional="1.2. B", title="b1"),
    ]
    merged = apply_revision(suite, TestSuiteRevision(
        updated_test_cases=[TestCase(testcase_id="tc1", group_functional="1.1. A", title="a1 sửa"),
                            TestCase(testcase_id="TC 99", group_functional="1.2. B", title="b-new-from-update")],
        added_test_cases=[TestCase(testcase_id="", group_functional="1.1. A", title="a-new")],
        removed_testcase_ids=["TC 02"],
    ))
    assert [t.title for t in merged] == ["a1 sửa", "a-new", "b1", "b-new-from-update"], [t.title for t in merged]
    final = finalize_test_suite(merged, [])
    assert [t.testcase_id for t in final.test_cases] == ["TC 01", "TC 02", "TC 03", "TC 04"]
    print("  -> Updates by normalized ID, removals, grouped insertion and renumbering all correct!")


def test_asked_questions_not_treated_as_waivers():
    """Câu hỏi đã hỏi được nhắc lại trong khối User Clarifications ('- Hỏi: ...không có API...') KHÔNG được
    làm Clarification Gate tưởng User đã miễn trừ; chỉ câu trả lời thật của User mới miễn trừ."""
    print("\n[21/21] Testing Clarification Gate Ignores Echoed Questions...")
    from src.core.clarification import detect_missing_artifacts, MISSING_API_REQUEST_QUESTION
    from src.core.session import QASession, SessionOptions, SourceDocument
    from src.core.models import ClarificationAnswer

    session = QASession(key="g", options=SessionOptions())
    session.documents = [SourceDocument(label="US", content="Chuyen tien noi bo, han muc 500 trieu/ngay.")]
    session.answers = [ClarificationAnswer(question=MISSING_API_REQUEST_QUESTION, answer="để mai mình gửi")]
    assert MISSING_API_REQUEST_QUESTION in detect_missing_artifacts(session.compose_requirement()), \
        "Echoed question text must not count as the user's waiver!"
    session.answers = [ClarificationAnswer(question=MISSING_API_REQUEST_QUESTION, answer="Tính năng này không có API")]
    assert MISSING_API_REQUEST_QUESTION not in detect_missing_artifacts(session.compose_requirement())
    print("  -> Only the user's own answer waives a deterministic question!")


def test_remote_channel_file_sandbox():
    """Kênh từ xa (Slack/Web): tin nhắn chứa đường dẫn file của server (vd `.env`) KHÔNG được đọc nội dung
    file đó ra; chỉ file nằm trong thư mục upload mới được đọc. CLI (root=None) vẫn đọc file local bình thường."""
    print("\n[22/25] Testing Remote-Channel File Sandbox (no server file disclosure via message text)...")
    from src.utils.file_parsers import merge_multiple_sources
    from src.core.session import remote_upload_dir

    with tempfile.TemporaryDirectory() as outside:
        secret = os.path.join(outside, "secret.md")
        with open(secret, "w", encoding="utf-8") as f:
            f.write("SERVER_SECRET_TOKEN=abc")
        remote_text, _, _ = merge_multiple_sources([secret], local_file_root=remote_upload_dir())
        assert "SERVER_SECRET_TOKEN" not in remote_text, "Remote channel must not read server files outside the upload dir!"
        multi_text, _, _ = merge_multiple_sources([secret, "ghi chu them"], local_file_root=remote_upload_dir())
        assert "SERVER_SECRET_TOKEN" not in multi_text
        cli_text, _, _ = merge_multiple_sources([secret])
        assert "SERVER_SECRET_TOKEN" in cli_text, "CLI (trusted, root=None) must still read local files"

    fd, uploaded = tempfile.mkstemp(suffix=".md", dir=remote_upload_dir())
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("UPLOADED_DOC_MARKER")
    try:
        up_text, _, _ = merge_multiple_sources([uploaded], local_file_root=remote_upload_dir())
        assert "UPLOADED_DOC_MARKER" in up_text
    finally:
        os.remove(uploaded)
    print("  -> Only files inside the upload dir are readable from Slack/Web; CLI unaffected!")


WEB_QUESTION = "Hạn mức tối đa mỗi giao dịch là bao nhiêu?"


def _web_pipeline_mocks(analyst_inputs: list):
    """Pipeline giả cho Web GUI: lần đầu Agent hỏi hạn mức; trả lời xong thì sinh 1 TC; feedback thêm 1 TC.
    Excel giả ghi vào đúng `output_path` engine truyền xuống, nội dung = tên tính năng + số TC."""
    from contextlib import ExitStack
    from unittest.mock import patch
    from src.core.models import ClarificationAnswer
    from src.agents.turn_interpreter import UserTurnInterpretation
    from src.agents.testcase_reviser import TestSuiteRevisionResult

    def analyze(raw_content, **kw):
        analyst_inputs.append(raw_content)
        answered = "User trả lời" in raw_content
        return RequirementAnalysis(feature_name="Web Chuyen tien", needs_user_clarification=not answered,
                                   clarification_questions=[] if answered else [WEB_QUESTION])

    def interpret(message, open_questions, **kw):
        if open_questions:
            return UserTurnInterpretation(answers=[ClarificationAnswer(question=WEB_QUESTION, answer=message)])
        return UserTurnInterpretation(testcase_feedback=[message])

    def revise(analysis, test_cases, instructions, **kw):
        return TestSuiteRevisionResult(test_cases=list(test_cases) + [TestCase(testcase_id=f"TC {len(test_cases) + 1:02d}", title="OTP het han")],
                                       change_summary=["Thêm TC OTP hết hạn"])

    def export(analysis, test_cases, output_path=None, **kw):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(f"{analysis.feature_name}|{len(test_cases)}".encode())
        return output_path

    stack = ExitStack()
    stack.enter_context(_patch_pipeline(analyze, export=export))
    stack.enter_context(patch("src.core.conversation.interpret_user_turn", side_effect=interpret))
    stack.enter_context(patch("src.core.conversation.revise_test_cases", side_effect=revise))
    return stack


class _WebUser:
    """Một trình duyệt dùng Web GUI (mã X-Client-Id riêng)."""

    def __init__(self, client, client_id: str):
        self.client, self.headers = client, {"X-Client-Id": client_id}

    def new_conversation(self) -> str:
        return self.client.post("/api/sessions", headers=self.headers).json()["session_id"]

    def send(self, sid: str, text: str = "", files=None):
        return self.client.post(f"/api/sessions/{sid}/messages", data={"text": text}, files=files or [])

    def wait_idle(self, sid: str) -> dict:
        import time
        deadline = time.time() + 10
        while time.time() < deadline:
            data = self.client.get(f"/api/sessions/{sid}/events").json()
            if not data["state"]["running"]:
                return data
            time.sleep(0.05)
        raise AssertionError("Web session worker did not finish")

    def conversations(self, q: str = "") -> list:
        return self.client.get("/api/conversations", params={"q": q}, headers=self.headers).json()["conversations"]


def test_web_gui_conversation_flow():
    """Web GUI: guardrail chặn lời chào cho yêu cầu mới; upload tài liệu -> Agent hỏi lại -> User trả lời
    -> có kết quả + link tải Excel; feedback sau đó cập nhật cùng file (sự kiện 'result' updated=True);
    file sai định dạng bị từ chối."""
    print("\n[23/25] Testing Web GUI Conversation API (guardrail, upload, ask/answer, download, revise)...")
    from fastapi.testclient import TestClient
    from src.integrations.web_app import create_web_app

    analyst_inputs = []
    with tempfile.TemporaryDirectory() as tmp, _web_pipeline_mocks(analyst_inputs):
        client = TestClient(create_web_app(history_dir=tmp))
        assert client.post("/api/sessions").status_code == 400, "Creating a conversation requires the browser id"
        user = _WebUser(client, "browser-aaaa-1111")
        sid = user.new_conversation()

        r = user.send(sid, "hi")
        assert r.status_code == 200 and r.json()["accepted"] is False
        assert client.get(f"/api/sessions/{sid}/events").json()["events"][-1]["type"] == "guide"
        assert user.send(sid, files=[("files", ("x.exe", b"MZ", "application/octet-stream"))]).status_code == 400

        r = user.send(sid, files=[("files", ("user_story.md", "Chuyen tien noi bo WEB_DOC_MARKER, so du kha dung".encode(), "text/markdown"))])
        assert r.json()["accepted"] is True
        data = user.wait_idle(sid)
        assert any("WEB_DOC_MARKER" in s for s in analyst_inputs), "Uploaded document content must reach the analyst"
        asks = [e for e in data["events"] if e["type"] == "ask"]
        assert asks and asks[-1]["questions"] == [WEB_QUESTION] and data["state"]["awaiting"]
        assert client.get(f"/api/sessions/{sid}/download").status_code == 404

        user.send(sid, "500 triệu")
        data = user.wait_idle(sid)
        result = [e for e in data["events"] if e["type"] == "result"][-1]
        assert result["updated"] is False and result["tc_count"] == 1 and result["download"]
        dl = client.get(result["download"])
        assert dl.status_code == 200 and dl.content == b"Web Chuyen tien|1"
        assert "Testsuite_Web_Chuyen_tien.xlsx" in dl.headers["content-disposition"]

        user.send(sid, "thêm case OTP hết hạn")
        data = user.wait_idle(sid)
        update = [e for e in data["events"] if e["type"] == "result"][-1]
        assert update["updated"] is True and update["tc_count"] == 2 and update["changes"] == ["Thêm TC OTP hết hạn"]
        assert update["download"] != result["download"], "Download link must change so the browser fetches the new file"
        assert client.get(update["download"]).content == b"Web Chuyen tien|2"
        assert data["state"]["suite_ready"]
        assert client.get("/api/sessions/unknown/events").status_code == 404
        assert "QA Agent" in client.get("/").text
    print("  -> Web GUI: guardrail, upload, ask/answer, download and in-place revision all work over the HTTP API!")


def test_web_gui_history_persistence():
    """Lịch sử Web GUI: hội thoại được liệt kê theo trình duyệt (không lộ sang trình duyệt khác), tìm được
    bằng từ khóa không dấu, mỗi hội thoại có file Excel riêng (cùng tên tính năng không ghi đè), và sau khi
    server khởi động lại vẫn mở lại y nguyên + tiếp tục feedback trên đúng bộ test case cũ."""
    print("\n[24/25] Testing Web GUI History (per-browser list, accent-insensitive search, restart & continue)...")
    from fastapi.testclient import TestClient
    from src.integrations.web_app import create_web_app

    story = ("files", ("us.md", "Chuyển tiền nội bộ giữa 2 tài khoản, kiểm tra số dư khả dụng".encode(), "text/markdown"))
    with tempfile.TemporaryDirectory() as tmp, _web_pipeline_mocks([]):
        client = TestClient(create_web_app(history_dir=tmp))
        alice, bob = _WebUser(client, "browser-alice-0001"), _WebUser(client, "browser-bob-00002")

        sid_a = alice.new_conversation()
        alice.send(sid_a, "Đây là yêu cầu chuyển tiền, xem file", files=[story])
        alice.wait_idle(sid_a)
        alice.send(sid_a, "500 triệu")
        alice.wait_idle(sid_a)
        alice.new_conversation()  # Hội thoại trống (chưa nhắn gì) không xuất hiện trong lịch sử.

        sid_b = bob.new_conversation()
        bob.send(sid_b, files=[story])
        bob.wait_idle(sid_b)
        bob.send(sid_b, "1 tỷ")
        bob.wait_idle(sid_b)
        bob.send(sid_b, "thêm case OTP hết hạn")
        bob.wait_idle(sid_b)

        listed = alice.conversations()
        assert [c["id"] for c in listed] == [sid_a], "A browser must only see its own, non-empty conversations"
        assert listed[0]["title"] == "Web Chuyen tien" and listed[0]["status"] == "ready"
        assert [c["id"] for c in alice.conversations("DAY la YEU cau")] == [sid_a], \
            "Search must match the user's own (accented) message text, ignoring case & Vietnamese accents"
        assert alice.conversations("không tồn tại") == []
        dl_a = client.get(f"/api/sessions/{sid_a}/download").content
        dl_b = client.get(f"/api/sessions/{sid_b}/download").content
        assert (dl_a, dl_b) == (b"Web Chuyen tien|1", b"Web Chuyen tien|2"), \
            "Conversations with the same feature name must keep separate Excel files"
        events_before = client.get(f"/api/sessions/{sid_a}/events").json()["events"]

        # Khởi động lại server: app mới, cùng thư mục lịch sử.
        client = TestClient(create_web_app(history_dir=tmp))
        alice = _WebUser(client, "browser-alice-0001")
        assert [c["id"] for c in alice.conversations()] == [sid_a]
        restored = client.get(f"/api/sessions/{sid_a}/events").json()
        assert restored["events"] == events_before and restored["state"]["suite_ready"]
        assert restored["state"]["title"] == "Web Chuyen tien"

        alice.send(sid_a, "thêm case OTP hết hạn")
        data = alice.wait_idle(sid_a)
        update = [e for e in data["events"] if e["type"] == "result"][-1]
        assert update["updated"] is True and update["tc_count"] == 2, "Follow-up after restart must revise the restored suite"
        assert [e["id"] for e in data["events"]] == list(range(len(data["events"]))), "Event ids must continue after restore"
        assert client.get(update["download"]).content == b"Web Chuyen tien|2"
    print("  -> History is per-browser, searchable without accents, file-isolated, and survives a server restart!")


def test_web_gui_access_password():
    """Khi đặt mật khẩu (bắt buộc lúc đưa lên Internet), MỌI đường dẫn — trang chủ, API, tải Excel — đều
    trả 401 kèm yêu cầu Basic Auth nếu thiếu/sai mật khẩu; đúng mật khẩu (tên đăng nhập tùy ý) thì dùng bình thường."""
    print("\n[25/25] Testing Web GUI Access Password (Basic Auth on every route)...")
    import base64
    from fastapi.testclient import TestClient
    from src.integrations.web_app import create_web_app

    def basic(user: str, password: str) -> dict:
        return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}

    with tempfile.TemporaryDirectory() as tmp:
        client = TestClient(create_web_app(history_dir=tmp, access_password="Mật-khẩu:team-QA"))
        browser = {"X-Client-Id": "browser-auth-0001"}
        for headers in ({}, basic("qa", "sai"), basic("qa", "Mật-khẩu"), {"Authorization": "Basic %%%"},
                        {"Authorization": "Bearer " + base64.b64encode("Mật-khẩu:team-QA".encode()).decode()}):
            for method, url in (("GET", "/"), ("GET", "/api/conversations"), ("POST", "/api/sessions"),
                                ("GET", "/api/sessions/abc/events"), ("GET", "/api/sessions/abc/download")):
                r = client.request(method, url, headers={**browser, **headers})
                assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic"), (method, url, headers)

        ok = {**browser, **basic("bất kỳ", "Mật-khẩu:team-QA")}
        assert "QA Agent" in client.get("/", headers=ok).text
        sid = client.post("/api/sessions", headers=ok).json()["session_id"]
        assert client.get(f"/api/sessions/{sid}/events", headers=ok).status_code == 200
        assert client.get("/api/conversations", headers=ok).json() == {"conversations": []}
        assert TestClient(create_web_app(history_dir=tmp)).get("/").status_code == 200, "No password configured = open (LAN mode)"
    print("  -> Every route requires the shared password when WEB_ACCESS_PASSWORD is set!")


if __name__ == "__main__":
    test_file_parser()
    test_linter()
    test_excel_exporter()
    test_graph_compilation()
    test_agent_invocations()
    test_multi_domain_support()
    test_linter_dead_checks_regression()
    test_new_qa_capabilities()
    test_clarification_gate()
    test_gate_status_reporting()
    test_slack_thread_context_memory()
    test_slack_gate_failure_visibility()
    test_raw_content_grounding()
    test_llm_request_timeout()
    test_batch_multi_group_processing()
    test_slack_batch_parse_groups()
    test_slack_batch_multi_group_processing()
    test_slack_batch_pending_clarification_disambiguation()
    test_conversation_followup_updates_suite()
    test_apply_revision_merge()
    test_asked_questions_not_treated_as_waivers()
    test_remote_channel_file_sandbox()
    test_web_gui_conversation_flow()
    test_web_gui_history_persistence()
    test_web_gui_access_password()
    print("\n✅ All component tests PASSED!")
