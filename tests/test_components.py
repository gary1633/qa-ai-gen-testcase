import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
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
from src.core.linter import lint_test_case, lint_test_suite_coverage
from src.utils.file_parsers import extract_input_content
from src.utils.excel_exporter import export_test_cases_to_excel
from src.core.workflow import build_qa_agentic_graph


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
        actual_result="",
        test_data="valid data",
        creator="QA",
        test_date="24/08/2026",
        test_status="Not Test",
        priority="High",
        plan_execution="Sprint",
        executed_date="",
        note="AC-01"
    )
    issues = lint_test_case(bad_tc)
    issue_types = [i.issue_type for i in issues]
    assert "Non-Deterministic Expected Result" in issue_types or "Ambiguous Step" in issue_types
    assert any("wait a bit" in i.description for i in issues)
    assert any("verify it works" in i.description for i in issues)
    print(f"  -> Linter correctly flagged {len(issues)} issues in ambiguous testcase!")

    # Test Banking Domain Linter checks (Missing Idempotency & Conditional QĐ 2345)
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
            actual_result="", test_data='{"amount": 100000}',
            creator="QA", test_date="24/08/2026", test_status="Not Test",
            priority="High", plan_execution="Sprint", executed_date="", note="AC-01"
        )
    ]
    coverage_issues = lint_test_suite_coverage(payment_analysis, incomplete_tcs)
    cov_issue_types = [i.issue_type for i in coverage_issues]
    assert "Missing Idempotency/Timeout Case" in cov_issue_types
    assert "Banking Compliance Violation (QĐ 2345)" in cov_issue_types
    print(f"  -> Banking Linter correctly flagged {len(coverage_issues)} banking domain issues (Idempotency & Conditional QĐ 2345)!")
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
    print("\n[3/4] Testing Excel Exporter with EF_TestCases.xlsx (Standard Template with Logo)...")
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

    sample_test_cases = [
        TestCase(
            testcase_id="TC 01",
            group_feature="1. Chuyển tiền Napas 247 qua Số tài khoản (AC-01)",
            group_functional="1.1. Luồng thành công (Happy Path & Phí giao dịch)",
            title="Chuyển tiền thành công dưới 1 triệu VND (Miễn phí giao dịch)",
            preconditions="Tài khoản nguồn Active, số dư khả dụng >= 500,000 VND. Ngân hàng đích liên kết Napas.",
            steps="1. Gửi request POST /v1/transfer/napas247\n2. Kiểm tra status code và response body",
            expected_result="- HTTP Status: 200 OK\n- Response Body:\n{\n  \"status\": \"SUCCESS\",\n  \"fee\": 0,\n  \"trace_no\": \"NP20260824001\"\n}",
            actual_result="",
            test_data="{\n  \"from_account\": \"1012345678\",\n  \"to_account\": \"9988776655\",\n  \"to_bank_code\": \"VCB\",\n  \"amount\": 500000\n}",
            creator="QA Agent",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-01"
        ),
        TestCase(
            testcase_id="TC 02",
            group_feature="1. Chuyển tiền Napas 247 qua Số tài khoản (AC-01)",
            group_functional="1.1. Luồng thành công (Happy Path & Phí giao dịch)",
            title="Chuyển tiền thành công từ 1 triệu VND trở lên (Thu phí 2,200 VND)",
            preconditions="Tài khoản nguồn Active, số dư khả dụng >= 2,002,200 VND.",
            steps="1. Gửi request POST /v1/transfer/napas247\n2. Kiểm tra trừ tiền gốc và phí",
            expected_result="- HTTP Status: 200 OK\n- Phí giao dịch: 2,200 VND\n- Số dư tài khoản nguồn bị trừ: 2,002,200 VND",
            actual_result="",
            test_data="{\n  \"from_account\": \"1012345678\",\n  \"amount\": 2000000\n}",
            creator="QA Agent",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="High",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-01"
        ),
        TestCase(
            testcase_id="TC 03",
            group_feature="2. Kiểm tra Hạn mức Giao dịch (AC-02)",
            group_functional="2.1. Phân tích giá trị biên (Boundary Value Analysis)",
            title="Kiểm tra chuyển số tiền dưới mức tối thiểu (9,999 VND)",
            preconditions="Tài khoản nguồn hợp lệ.",
            steps="1. Gửi request POST /v1/transfer/napas247 với amount = 9999\n2. Kiểm tra mã lỗi trả về",
            expected_result="- HTTP Status: 400 Bad Request\n- Error Code: ERR_MIN_AMOUNT\n- Error Message: 'Số tiền chuyển tối thiểu là 10,000 VND'",
            actual_result="",
            test_data="{\n  \"amount\": 9999\n}",
            creator="QA Agent",
            test_date="24/08/2026",
            test_status="Not Test",
            priority="Medium",
            plan_execution="Sprint 1",
            executed_date="",
            note="AC-02"
        )
    ]

    out_file = export_test_cases_to_excel(
        analysis=req_analysis,
        test_cases=sample_test_cases,
        template_path="EF_TestCases.xlsx",
        output_path=None,  # Tự động xuất ra outputs/
        target_sheet_name="VWCBT_4102_Napas_Test"
    )

    # Verify generated sheet
    wb = openpyxl.load_workbook(out_file, data_only=False)
    print("  -> Exported file sheet names:", wb.sheetnames)
    assert "Workstream Progress Summary" in wb.sheetnames
    assert "VWCBT_4102_Napas_Test" in wb.sheetnames
    assert "Tài liệu tổng hợp" in wb.sheetnames
    # Template phiếu KTNV or standard common sheets
    assert "Daily Execution Log" in wb.sheetnames
    assert "Checklist Report" in wb.sheetnames
    assert "RAW JIRA Bug" in wb.sheetnames
    assert "EF_BLOCKADE_SA" not in wb.sheetnames
    assert "EF_Calculate_Savings_Interest" not in wb.sheetnames
    
    ws = wb["VWCBT_4102_Napas_Test"]
    # Check metadata
    assert ws.cell(10, 3).value == "Branch Portal / Mobile Banking"
    assert ws.cell(11, 3).value == "UAT 3.1.0"
    
    # Check formula in row 19
    total_formula = ws.cell(19, 1).value
    print("  -> Generated formula for Total:", total_formula)
    assert total_formula.startswith("=COUNTIF(A22:A")
    
    print(f"  -> Excel Exporter OK! Sheet 'VWCBT_4102_Napas_Test' created and populated.")


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
                TestCase(testcase_id="TC 01", group_feature="1. Chặn EOD", group_functional="1.1. Luồng chính", title='Kiểm tra "18:00:00"', preconditions="Active", steps="POST", expected_result="400 CV_043", actual_result="", test_data="{}", creator="QA", test_date="24/08/2026", test_status="Not Test", priority="High", plan_execution="Release", executed_date="", note="AC-01")
            ]
        )
        test_cases = generate_test_cases(analysis, scenarios, provider="gemini")
        assert mock_gen.call_count == 1
        assert "system_prompt" in mock_gen.call_args.kwargs
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

if __name__ == "__main__":
    test_file_parser()
    test_linter()
    test_excel_exporter()
    test_graph_compilation()
    test_agent_invocations()
    print("\n✅ All component tests PASSED!")
