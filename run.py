#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os
import argparse
from typing import Any, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from dotenv import load_dotenv

load_dotenv()

from src.core.workflow import build_qa_agentic_graph
from src.core.state import QAWorkflowState
from src.core.llm import detect_provider
from src.integrations.jira_connector import JiraConnector, extract_jira_key
from src.utils.file_parsers import is_safe_local_file, merge_multiple_sources
from src.core.guardrail import validate_requirement_input, get_help_guide
console = Console()


def print_banner(provider: str, model: str):
    console.print(Panel.fit(
        f"[bold cyan]QA AGENTIC WORKFLOW v1.2 (ISTQB & RBT Testing Enabled)[/bold cyan]\n"
        f"[dim]Phân tích Yêu cầu -> Đánh giá Rủi ro (RBT) -> Thiết kế Kịch bản ISTQB -> Sinh Test Case -> QA Linter -> Xuất Excel Template[/dim]\n"
        f"Active Provider: [bold green]{provider.upper()}[/bold green] | Model: [bold yellow]{model}[/bold yellow]",
        border_style="cyan"
    ))


def display_requirement_summary(analysis):
    table = Table(title=f"📋 Báo cáo Phân tích Yêu cầu: [bold yellow]{analysis.feature_name}[/bold yellow]", border_style="blue")
    table.add_column("Mục Phân Tích", style="cyan", width=25)
    table.add_column("Chi Tiết", style="white")

    table.add_row("Phân hệ Ngân hàng", analysis.banking_domain)
    table.add_row("Mục tiêu nghiệp vụ", analysis.business_overview or analysis.business_objective)
    table.add_row("Tổng số AC bóc tách", str(len(analysis.acceptance_criteria)))
    table.add_row("Rủi ro cao / Trọng yếu (RBT)", str(len([r for r in analysis.product_risks if r.risk_level in ["Critical", "High"]])))
    table.add_row("Điểm bất biến (Invariants)", "\n".join([f"• {inv}" for inv in analysis.banking_invariants]))
    
    if analysis.ambiguities_and_gaps:
        gaps = "\n".join([f"[yellow]• {g}[/yellow]" for g in analysis.ambiguities_and_gaps])
        table.add_row("Điểm mơ hồ / Gaps", gaps)

    if analysis.needs_user_clarification and analysis.clarification_questions:
        questions = "\n".join([f"[bold red]• {q}[/bold red]" for q in analysis.clarification_questions])
        table.add_row("Câu hỏi cần User làm rõ", questions)

    console.print(table)


def display_rbt_risk_matrix(product_risks):
    if not product_risks:
        return
    table = Table(title="🛡️ Ma trận Đánh giá Rủi ro Kiểm thử (Risk-Based Testing Matrix)", border_style="red")
    table.add_column("Mã Risk", style="cyan", width=12)
    table.add_column("Mức độ", style="bold", width=12)
    table.add_column("Danh mục", style="magenta", width=18)
    table.add_column("Tên Rủi ro & Mô tả", style="white", width=45)
    table.add_column("Trọng tâm Kiểm thử (Mitigation)", style="green", width=40)

    for r in product_risks:
        level_style = "red" if r.risk_level == "Critical" else ("yellow" if r.risk_level == "High" else "blue")
        table.add_row(
            r.risk_id,
            f"[{level_style}]{r.risk_level}[/{level_style}]",
            r.risk_category,
            f"[bold]{r.risk_title}[/bold]\n[dim]{getattr(r, 'risk_description', '')}[/dim]",
            r.mitigation_test_focus
        )
    console.print(table)


def display_scenario_matrix(scenarios):
    table = Table(title=f"🎯 Ma trận Kịch bản Kiểm thử ({len(scenarios)} kịch bản)", border_style="green")
    table.add_column("ID", style="cyan", width=8)
    table.add_column("Nhóm Lớn (Group Feature)", style="magenta", width=26)
    table.add_column("Nhóm Con (Functional)", style="yellow", width=22)
    table.add_column("Tiêu đề Kịch bản", style="white", width=40)
    table.add_column("Kỹ thuật ISTQB", style="blue", width=18)
    table.add_column("Priority", style="bold", width=10)

    for s in scenarios:
        p_style = "red" if s.priority == "Critical" else ("yellow" if s.priority == "High" else "white")
        table.add_row(
            s.scenario_id,
            s.group_feature,
            s.group_functional,
            s.scenario_title,
            s.testing_technique,
            f"[{p_style}]{s.priority}[/{p_style}]"
        )
    console.print(table)


def display_review_results(review_res):
    color = "green" if review_res.passed else "red"
    status_text = "PASSED - ĐẠT CHUẨN XUẤT EXCEL" if review_res.passed else "FAILED - CẦN TỐI ƯU LẠI"
    
    panel = Panel(
        f"[bold {color}]Kết quả Review & Linter: {status_text} (Điểm: {review_res.score}/100)[/bold {color}]\n\n"
        f"[dim]{review_res.feedback_summary}[/dim]",
        title="🔍 QA Quality Gate, Traceability & Linter Report",
        border_style=color
    )
    console.print(panel)

    # 1. Hiển thị Ma trận Truy vết 2 Chiều (Traceability Matrix)
    if hasattr(review_res, "traceability_matrix") and review_res.traceability_matrix:
        t_table = Table(title=f"📋 Ma Trận Truy Vết Yêu Cầu 2 Chiều (Traceability Matrix - {len(review_res.traceability_matrix)} ACs)", border_style="cyan")
        t_table.add_column("Mã AC", style="bold cyan", width=10)
        t_table.add_column("Tiêu chí Chấp nhận", style="white", width=35)
        t_table.add_column("Rủi ro", style="bold", width=10)
        t_table.add_column("Test Cases Bao phủ", style="green", width=25)
        t_table.add_column("Trạng thái", style="bold", width=12)
        t_table.add_column("Góc độ Kiểm thử", style="dim white", width=30)

        for item in review_res.traceability_matrix:
            st_color = "green" if item.coverage_status == "COVERED" else ("yellow" if item.coverage_status == "PARTIAL" else "red")
            r_color = "red" if item.risk_level in ["Critical", "High"] else "yellow"
            t_table.add_row(
                item.ac_id,
                item.ac_title,
                f"[{r_color}]{item.risk_level}[/{r_color}]",
                ", ".join(item.covered_test_cases) if item.covered_test_cases else "N/A",
                f"[{st_color}]{item.coverage_status}[/{st_color}]",
                item.coverage_notes
            )
        console.print(t_table)

    # 2. Hiển thị Danh sách Issues
    if review_res.issues:
        table = Table(title=f"Danh sách {len(review_res.issues)} vấn đề phát hiện cần chỉnh sửa", border_style="yellow")
        table.add_column("Target TC", style="cyan", width=12)
        table.add_column("Mức độ", style="bold", width=10)
        table.add_column("Loại vấn đề", style="magenta", width=25)
        table.add_column("Mô tả chi tiết", style="white", width=45)
        table.add_column("Đề xuất sửa đổi", style="green", width=35)

        for issue in review_res.issues:
            s_color = "red" if issue.severity in ["Critical", "Major"] else "yellow"
            table.add_row(
                issue.target_tc_id or "All Suite",
                f"[{s_color}]{issue.severity}[/{s_color}]",
                issue.issue_type,
                issue.description,
                issue.suggested_fix
            )
        console.print(table)
def main():
    parser = argparse.ArgumentParser(description="Chạy QA Agentic Workflow từ Yêu cầu / Nhiều Jira Tickets / Tài liệu kết hợp đến Test Case Excel")
    parser.add_argument("inputs", nargs="*", help="Danh sách các file Yêu cầu (.md, .txt, .docx, .pdf) hoặc Mã Jira Ticket (vd: VWCBT-3800)")
    
    # Jira Options
    parser.add_argument("--jira", default=None, help="Mã Jira Ticket (vd: VWCBT-3800) hoặc Link Jira URL")
    
    # LLM Options
    parser.add_argument("--provider", default=None, help="LLM Provider: google, openai, anthropic, deepseek, ollama, openrouter, custom")
    parser.add_argument("--model", default=None, help="Tên model (vd: gemini-3.6-flash, gpt-4o, claude-3-5-sonnet-20241022, deepseek-chat, qwen2.5:14b)")
    parser.add_argument("--base-url", default=None, help="Base URL cho Ollama, vLLM, DeepSeek hoặc Custom Endpoint")
    parser.add_argument("--api-key", default=None, help="API Key của LLM")

    # App & Output Options
    parser.add_argument("--app", default=None, help="Tên ứng dụng kiểm tra (ghi đè)")
    parser.add_argument("--version", default=None, help="Phiên bản kiểm tra (ghi đè)")
    parser.add_argument("--sheet", default=None, help="Tên sheet xuất trong Excel (ghi đè)")
    parser.add_argument("--template", default="EF_TestCases.xlsx", help="Đường dẫn file template Excel (Mặc định: EF_TestCases.xlsx)")
    parser.add_argument("--output", default=None, help="Đường dẫn file Excel đích (Mặc định tạo file mới riêng biệt trong thư mục outputs/)")
    parser.add_argument("--max-iter", type=int, default=3, help="Số lần lặp tối đa để sửa lỗi review")
    parser.add_argument(
        "-e", "--extra", "--clarification", "--notes",
        dest="extra_info",
        default=None,
        help="Nhập thông tin bổ sung, giải thích làm rõ hoặc ghi chú nghiệp vụ kèm theo (User Clarifications)"
    )

    args = parser.parse_args()
    active_provider = detect_provider(args.provider, args.model)
    active_model = args.model or os.getenv("LLM_MODEL") or (
        os.getenv("GEMINI_MODEL_NAME", "gemini-3.6-flash") if active_provider == "google" else (
            os.getenv("OPENAI_MODEL_NAME", "gpt-4o") if active_provider == "openai" else (
                os.getenv("ANTHROPIC_MODEL_NAME", "claude-3-5-sonnet-20241022") if active_provider == "anthropic" else (
                    os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-chat") if active_provider == "deepseek" else "custom-model"
                )
            )
        )
    )

    print_banner(active_provider, active_model)

    raw_sources: List[str] = list(args.inputs)
    if args.jira:
        raw_sources.append(args.jira)
    if getattr(args, "extra_info", None):
        raw_sources.append(args.extra_info)

    if not raw_sources:
        console.print("[yellow]Chưa cung cấp file hoặc mã Jira đầu vào. Đang khởi động chế độ nhập trực tiếp (Interactive Prompt)...[/yellow]")
        console.print("[cyan]Vui lòng dán nội dung User Story / Yêu cầu (hoặc kéo thả file / nhập mã Jira) và nhấn Enter:[/cyan]")
        user_input = input("> ").strip()
        if not user_input:
            console.print("[red]Lỗi: Không có nội dung yêu cầu đầu vào. Kết thúc chương trình.[/red]")
            sys.exit(1)
        raw_sources.append(user_input)

    # Guardrail Check chống spam / input vô nghĩa khi chỉ nhập text ngắn
    if len(raw_sources) == 1 and not is_safe_local_file(raw_sources[0]):
        is_valid, reason, guide = validate_requirement_input(raw_sources[0])
        if not is_valid:
            console.print(f"\n[bold red]⚠️ Yêu cầu không hợp lệ:[/bold red] {reason}\n")
            console.print(Panel(guide, title="[bold yellow]Hướng dẫn Cung cấp Requirement Chuẩn[/bold yellow]", border_style="yellow"))
            sys.exit(1)

    while True:
        console.print(f"[cyan]📁 Đang tổng hợp và phân tích [bold yellow]{len(raw_sources)} nguồn tài liệu / ghi chú[/bold yellow]...[/cyan]")
        for idx, s in enumerate(raw_sources, 1):
            console.print(f"   [dim]{idx}. {s[:120]}...[/dim]" if len(s) > 120 else f"   [dim]{idx}. {s}[/dim]")

        merged_text, file_type, meta = merge_multiple_sources(raw_sources)
        jira_links = meta.get("jira_links", [])
        jira_keys = meta.get("jira_keys", [])
        custom_jira_link = ", ".join(jira_links) if jira_links else None
        suggested_sheet = f"{jira_keys[0]}_Test" if jira_keys else None

        initial_state: QAWorkflowState = {
            "input_file_path": None,
            "input_raw_text": merged_text,
            "llm_provider": active_provider,
            "llm_model_name": active_model,
            "llm_base_url": args.base_url,
            "llm_api_key": args.api_key,
            "custom_app_name": args.app,
            "custom_version": args.version,
            "custom_jira_link": custom_jira_link or args.jira,
            "custom_sheet_name": args.sheet or suggested_sheet,
            "template_excel_path": args.template,
            "output_excel_path": args.output,
            "max_review_iterations": args.max_iter,
            "logs": []
        }

        graph = build_qa_agentic_graph()

        console.print("\n[bold green]🚀 Bắt đầu thực thi Agentic Workflow (RBT Enabled)...[/bold green]\n")

        accumulated_state: dict = dict(initial_state)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task_id = progress.add_task("[cyan]Đang khởi chạy các Agent...", total=None)

            for output in graph.stream(initial_state):
                for node_name, node_state in output.items():
                    accumulated_state.update(node_state)
                    if node_name == "parse_input":
                        progress.update(task_id, description=f"[bold blue]Node 0: Trích xuất nội dung ({node_state.get('file_type')})[/bold blue]")
                    elif node_name == "analyze_requirement":
                        progress.update(task_id, description="[bold yellow]Node 1: Requirement Analyst đang phân tích nghiệp vụ & lập Ma trận Rủi ro (RBT)...[/bold yellow]")
                    elif node_name == "design_scenarios":
                        progress.update(task_id, description="[bold magenta]Node 2: Scenario Designer đang thiết kế Ma trận Kịch bản Chuyên sâu (ISTQB)...[/bold magenta]")
                    elif node_name == "generate_testcases":
                        progress.update(task_id, description="[bold cyan]Node 3: Testcase Generator đang sinh Test Case chi tiết 14 cột theo Template...[/bold cyan]")
                    elif node_name == "review_and_lint":
                        progress.update(task_id, description="[bold red]Node 4: QA Gatekeeper đang Linting & Đánh giá chất lượng Test Suite...[/bold red]")
                    elif node_name == "export_excel":
                        progress.update(task_id, description="[bold green]Node 5: Đang đổ dữ liệu vào Excel Template...[/bold green]")

        # Hiển thị kết quả chi tiết từng phần
        if accumulated_state:
            analysis = accumulated_state.get("requirement_analysis")
            if analysis:
                display_requirement_summary(analysis)
                display_rbt_risk_matrix(analysis.product_risks)

                if analysis.needs_user_clarification:
                    q_list = "\n".join([f"  [bold yellow]{i}.[/bold yellow] {q}" for i, q in enumerate(analysis.clarification_questions, 1)])
                    console.print(Panel(
                        f"[bold red]⚠️ YÊU CẦU CÓ ĐIỂM CHƯA RÕ RÀNG / THIẾU THÔNG TIN QUAN TRỌNG:[/bold red]\n\n"
                        f"Để đảm bảo đúng bản chất nghiệp vụ và tránh suy diễn sai lệch, hệ thống đã tạm dừng.\n"
                        f"Vui lòng xác nhận hoặc làm rõ các câu hỏi sau với PO/BA:\n\n"
                        f"{q_list}\n",
                        title="[bold red]❓ Câu Hỏi Cần User Làm Rõ Trước Khi Viết Test Case[/bold red]",
                        border_style="red"
                    ))
                    
                    # Cho phép User nhập thêm thông tin trực tiếp để tiếp tục
                    if sys.stdin.isatty():
                        console.print("[bold yellow]👉 Nhập câu trả lời / thông tin bổ sung làm rõ để tiếp tục (hoặc nhấn Enter / gõ 'exit' để dừng):[/bold yellow]")
                        try:
                            user_clarify = input("> ").strip()
                            if user_clarify and user_clarify.lower() != "exit":
                                raw_sources.append(user_clarify)
                                console.print("\n[bold green]🔄 Đã nhận thông tin bổ sung! Đang tiếp tục phân tích lại với đầy đủ dữ kiện...[/bold green]\n")
                                continue
                        except (EOFError, KeyboardInterrupt):
                            pass
                    sys.exit(0)
            
            if accumulated_state.get("scenarios"):
                display_scenario_matrix(accumulated_state["scenarios"])

            if accumulated_state.get("review_result"):
                display_review_results(accumulated_state["review_result"])

            out_path = accumulated_state.get("output_excel_path")
            if out_path:
                console.print(Panel.fit(
                    f"[bold green]🎉 HOÀN THÀNH TOÀN BỘ QUY TRÌNH GENERATE TESTCASES![/bold green]\n\n"
                    f"📁 [bold white]File Test Suite đã xuất:[/bold white] [bold cyan]{out_path}[/bold cyan]\n"
                    f"📊 [dim]Đã cập nhật biểu đồ tiến độ & công thức tự động trong template Excel.[/dim]",
                    border_style="green"
                ))
            break
if __name__ == "__main__":
    main()
