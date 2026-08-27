import os
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from src.core.state import QAWorkflowState
from src.utils.file_parsers import extract_input_content
from src.agents.requirement_analyst import analyze_requirements
from src.agents.scenario_designer import design_test_scenarios
from src.agents.testcase_generator import generate_test_cases
from src.agents.reviewer import review_and_lint_test_suite
from src.core.llm import load_qa_rules
from src.utils.excel_exporter import export_test_cases_to_excel, sanitize_sheet_name


def parse_input_node(state: QAWorkflowState) -> Dict[str, Any]:
    """Node 0: Trích xuất nội dung từ file hoặc raw text."""
    input_target = state.get("input_file_path") or state.get("input_raw_text") or ""
    raw_content, file_type = extract_input_content(input_target)
    
    return {
        "input_raw_text": raw_content,
        "file_type": file_type,
        "review_iteration": 0,
        "max_review_iterations": state.get("max_review_iterations", load_qa_rules()["max_review_iterations"]),
        "feedback_history": [],
        "logs": [{"node": "parse_input", "status": f"Đã đọc input thành công (loại: {file_type}, độ dài: {len(raw_content)} chars)"}]
    }


def requirement_analyst_node(state: QAWorkflowState) -> Dict[str, Any]:
    """Node 1: Phân tích nghiệp vụ, bóc tách AC và đánh giá tính kiểm thử."""
    raw_content = state["input_raw_text"]
    analysis = analyze_requirements(
        raw_content=raw_content,
        custom_app_name=state.get("custom_app_name"),
        custom_version=state.get("custom_version"),
        custom_jira_link=state.get("custom_jira_link"),
        provider=state.get("llm_provider"),
        model_name=state.get("llm_model_name"),
        base_url=state.get("llm_base_url"),
        api_key=state.get("llm_api_key")
    )
    
    if analysis.needs_user_clarification:
        status_msg = f"⚠️ Yêu cầu có {len(analysis.clarification_questions)} điểm chưa rõ cần User làm rõ trước khi viết test case."
    else:
        status_msg = f"Đã bóc tách {len(analysis.acceptance_criteria)} ACs, {len(analysis.ambiguities_and_gaps)} gaps, {len(analysis.edge_cases)} edge cases"

    return {
        "requirement_analysis": analysis,
        "logs": [{"node": "requirement_analyst", "status": status_msg}]
    }

def scenario_designer_node(state: QAWorkflowState) -> Dict[str, Any]:
    """Node 2: Thiết kế Ma trận Kịch bản kiểm thử (BVA, Equivalence Partitioning)."""
    analysis = state["requirement_analysis"]
    scenarios = design_test_scenarios(
        analysis=analysis,
        provider=state.get("llm_provider"),
        model_name=state.get("llm_model_name"),
        base_url=state.get("llm_base_url"),
        api_key=state.get("llm_api_key")
    )
    
    return {
        "scenarios": scenarios,
        "logs": [{"node": "scenario_designer", "status": f"Đã thiết kế {len(scenarios)} kịch bản kiểm thử"}]
    }


def testcase_generator_node(state: QAWorkflowState) -> Dict[str, Any]:
    """Node 3: Sinh danh sách Test Case chi tiết theo chuẩn 14 cột của Excel."""
    analysis = state["requirement_analysis"]
    scenarios = state["scenarios"]
    
    latest_feedback = None
    if state.get("review_result") and not state["review_result"].passed:
        latest_feedback = state["review_result"].feedback_summary
        if state["review_result"].issues:
            issues_txt = "\n".join([f"- [{i.target_tc_id or 'General'}] {i.description} -> Fix: {i.suggested_fix}" for i in state["review_result"].issues])
            latest_feedback += f"\n\nChi tiết lỗi:\n{issues_txt}"
            
    gen = generate_test_cases(
        analysis=analysis,
        scenarios=scenarios,
        review_feedback=state.get("review_result"),
        provider=state.get("llm_provider"),
        model_name=state.get("llm_model_name"),
        base_url=state.get("llm_base_url"),
        api_key=state.get("llm_api_key")
    )
    
    return {
        "test_cases": gen.test_cases,
        "pending_clarifications": gen.clarification_questions,
        "logs": [{"node": "testcase_generator", "status": f"Đã sinh {len(gen.test_cases)} test cases chi tiết (Lần lặp: {state.get('review_iteration', 0) + 1}), {len(gen.clarification_questions)} câu hỏi cần làm rõ"}]
    }


def reviewer_linter_node(state: QAWorkflowState) -> Dict[str, Any]:
    """Node 4: Gatekeeper kiểm định chất lượng (Linter + Semantic Review)."""
    analysis = state["requirement_analysis"]
    test_cases = state["test_cases"]
    current_iter = state.get("review_iteration", 0) + 1
    
    review_res = review_and_lint_test_suite(
        analysis=analysis,
        test_cases=test_cases,
        provider=state.get("llm_provider"),
        model_name=state.get("llm_model_name"),
        base_url=state.get("llm_base_url"),
        api_key=state.get("llm_api_key"),
        scenarios=state.get("scenarios"),
        raw_content=state.get("input_raw_text", "")
    )
    feedback_history = state.get("feedback_history", [])
    feedback_history.append(f"Iteration {current_iter}: Score {review_res.score}/100, Passed={review_res.passed}")
    
    return {
        "review_result": review_res,
        "review_iteration": current_iter,
        "feedback_history": feedback_history,
        "logs": [{"node": "reviewer_linter", "status": f"Review hoàn tất: Điểm {review_res.score}/100, Passed={review_res.passed}, {len(review_res.issues)} issues"}]
    }


def export_excel_node(state: QAWorkflowState) -> Dict[str, Any]:
    """Node 5: Xuất Test Cases ra sheet mới trong Template Testsuite.xlsx."""
    analysis = state["requirement_analysis"]
    test_cases = state["test_cases"]
    template_path = state.get("template_excel_path") or "EF_TestCases.xlsx"
    target_sheet = state.get("custom_sheet_name") or sanitize_sheet_name(analysis.feature_name)
    
    output_path = state.get("output_excel_path")
    saved_path = export_test_cases_to_excel(
        analysis=analysis,
        test_cases=test_cases,
        template_path=template_path,
        output_path=output_path,
        target_sheet_name=target_sheet,
        pending_clarifications=state.get("pending_clarifications") or []
    )
    
    return {
        "output_excel_path": saved_path,
        "generated_sheet_name": target_sheet,
        "logs": [{"node": "export_excel", "status": f"Đã xuất thành công {len(test_cases)} test cases vào sheet '{target_sheet}' file '{saved_path}'"}]
    }


def should_continue_after_analysis(state: QAWorkflowState) -> str:
    """Kiểm tra xem yêu cầu có cần User làm rõ trước khi tiếp tục hay không."""
    analysis = state.get("requirement_analysis")
    if analysis and analysis.needs_user_clarification:
        return "needs_clarification"
    return "design_scenarios"


def should_continue_review(state: QAWorkflowState) -> str:
    """Điều hướng có lặp lại để sửa lỗi hay xuất kết quả."""
    review_res = state.get("review_result")
    current_iter = state.get("review_iteration", 0)
    max_iter = state.get("max_review_iterations", load_qa_rules()["max_review_iterations"])
    
    if review_res and review_res.passed:
        return "export_excel"
    elif current_iter >= max_iter:
        return "export_excel"
    else:
        return "generate_testcases"

def build_qa_agentic_graph() -> StateGraph:
    """Xây dựng StateGraph cho QA Workflow."""
    builder = StateGraph(QAWorkflowState)
    
    builder.add_node("parse_input", parse_input_node)
    builder.add_node("analyze_requirement", requirement_analyst_node)
    builder.add_node("design_scenarios", scenario_designer_node)
    builder.add_node("generate_testcases", testcase_generator_node)
    builder.add_node("review_and_lint", reviewer_linter_node)
    builder.add_node("export_excel", export_excel_node)
    
    builder.set_entry_point("parse_input")
    builder.add_edge("parse_input", "analyze_requirement")
    builder.add_conditional_edges(
        "analyze_requirement",
        should_continue_after_analysis,
        {
            "design_scenarios": "design_scenarios",
            "needs_clarification": END
        }
    )
    builder.add_edge("design_scenarios", "generate_testcases")
    builder.add_edge("generate_testcases", "review_and_lint")
    
    builder.add_conditional_edges(
        "review_and_lint",
        should_continue_review,
        {
            "export_excel": "export_excel",
            "generate_testcases": "generate_testcases"
        }
    )
    builder.add_edge("export_excel", END)
    
    return builder.compile()
