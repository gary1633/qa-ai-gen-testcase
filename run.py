#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os
import argparse
from typing import List, Optional, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markup import escape
from dotenv import load_dotenv

load_dotenv()

from src.core.llm import detect_provider
from src.core.session import QASession, SessionOptions, UserTurn, STAGE_ANALYSIS
from src.core.conversation import SuiteOutcome, run_session
from src.utils.file_parsers import is_safe_local_file
from src.core.guardrail import validate_requirement_input
from src.agents.reviewer import gate_failure_reasons
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
    if review_res.passed:
        status_text = "PASSED - ĐẠT CHUẨN XUẤT EXCEL"
    else:
        reasons = "; ".join(gate_failure_reasons(review_res)) or "chưa xác định lý do"
        status_text = f"FAILED - CẦN TỐI ƯU LẠI ({reasons})"

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
def resolve_active_llm(args: argparse.Namespace) -> tuple:
    """Xác định Provider/Model LLM đang hoạt động từ args/env (logic dùng chung cho banner & mỗi nhóm xử lý)."""
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
    return active_provider, active_model


class CLIReporter:
    """Hiển thị tiến trình / câu hỏi / kết quả của phiên hội thoại ra terminal (Rich)."""

    def __init__(self, label_prefix: str = ""):
        self.label_prefix = label_prefix
        self._shown: List[str] = []

    @staticmethod
    def _plain(line: str) -> str:
        return escape(line.replace("*", "").replace("_", " ").strip())

    def progress(self, lines: List[str], new: bool = False) -> None:
        if new:
            self._shown = []
        for line in lines:
            if line not in self._shown and not line.startswith("• ⚪"):
                console.print(f"[cyan]{self.label_prefix}{self._plain(line)}[/cyan]")
                self._shown.append(line)

    def notify(self, text: str) -> None:
        console.print(f"[bold blue]{self.label_prefix}{escape(text)}[/bold blue]")

    def ask(self, session: QASession, questions: List[str], stage: str) -> None:
        if session.analysis and stage == STAGE_ANALYSIS:
            display_requirement_summary(session.analysis)
        q_list = "\n".join(f"  [bold yellow]{i}.[/bold yellow] {escape(q)}" for i, q in enumerate(questions, 1))
        console.print(Panel(
            f"[bold red]⚠️ YÊU CẦU CÓ ĐIỂM CHƯA RÕ RÀNG / THIẾU THÔNG TIN QUAN TRỌNG:[/bold red]\n\n"
            f"Để đúng bản chất nghiệp vụ và không suy diễn sai lệch, Agent cần bạn làm rõ:\n\n{q_list}\n",
            title=f"[bold red]❓ {self.label_prefix}Câu Hỏi Cần User Làm Rõ[/bold red]",
            border_style="red"
        ))

    def deliver(self, session: QASession, outcome: SuiteOutcome) -> None:
        if not outcome.updated:
            display_requirement_summary(session.analysis)
            display_rbt_risk_matrix(session.analysis.product_risks)
            if session.scenarios:
                display_scenario_matrix(session.scenarios)
        if session.review_result:
            display_review_results(session.review_result)
        if outcome.updated:
            changes = "\n".join(f"  • {escape(c)}" for c in outcome.change_summary) or "  • Không có thay đổi nào được áp dụng."
            console.print(Panel(changes, title=f"[bold cyan]✏️ {self.label_prefix}Thay đổi trong lượt cập nhật này[/bold cyan]", border_style="cyan"))
        if session.open_questions:
            q_txt = "\n".join(f"  [bold yellow]{i}.[/bold yellow] {escape(q)}" for i, q in enumerate(session.open_questions, 1))
            console.print(Panel(
                f"[bold red]⚠️ CÒN {len(session.open_questions)} ĐIỂM CHƯA CÓ DỮ KIỆN - AGENT KHÔNG TỰ BỊA:[/bold red]\n\n{q_txt}\n\n"
                f"[dim]Các test case bị ảnh hưởng đã được tô vàng và ghi chú PENDING CLARIFICATION; câu hỏi cũng nằm trong "
                f"sheet 'Cần làm rõ (Pending)' của file Excel.[/dim]",
                title=f"[bold red]❓ {self.label_prefix}Câu Hỏi Cần Làm Rõ (Sinh Test Case)[/bold red]",
                border_style="red"
            ))
        title = "♻️ ĐÃ CẬP NHẬT BỘ TEST CASE" if outcome.updated else "🎉 HOÀN THÀNH TOÀN BỘ QUY TRÌNH GENERATE TESTCASES!"
        console.print(Panel.fit(
            f"[bold green]{self.label_prefix}{title}[/bold green]\n\n"
            f"📁 [bold white]File Test Suite:[/bold white] [bold cyan]{session.output_excel_path}[/bold cyan] "
            f"({len(session.test_cases)} test cases)",
            border_style="green"
        ))

    def fail(self, session: QASession, text: str) -> None:
        console.print(f"[bold red]❌ {self.label_prefix}Lỗi xử lý: {escape(text)}[/bold red]")


def parse_cli_turn(line: str) -> UserTurn:
    """Một dòng nhập trong hội thoại CLI: đường dẫn file (có thể nhiều, cách nhau dấu phẩy) -> tài liệu
    bổ sung; còn lại là lời nhắn tự do (câu trả lời / feedback / mã Jira kèm ghi chú)."""
    parts = [p.strip().strip("'\"").replace("\\ ", " ") for p in line.split(",")]
    if parts and all(p and is_safe_local_file(p) for p in parts):
        return UserTurn(sources=parts)
    return UserTurn(text=line)


def process_requirement_group(raw_sources: List[str], args: argparse.Namespace, group_label: Optional[str] = None) -> dict:
    """
    Chạy phiên hội thoại tạo test case cho MỘT nhóm nguồn ĐỘC LẬP: Guardrail -> pipeline đầy đủ ->
    (tương tác, khi stdin là terminal) Agent hỏi lại khi thiếu thông tin; User trả lời, gửi thêm tài
    liệu (đường dẫn file / mã Jira) hoặc feedback bất cứ lúc nào và bộ test case được cập nhật ngay trong
    phiên, không cần chạy lại lệnh.

    `raw_sources` là danh sách các nguồn (file/Jira ticket/raw text) CHỈ thuộc về nhóm này; được gộp
    nguyên trạng bởi merge_multiple_sources() - việc gán tài liệu bổ sung vào đúng ticket tường minh 100%
    theo cấu trúc argv. Mỗi nhóm có phiên riêng, không rò rỉ trạng thái giữa các nhóm khi chạy --batch.

    Không raise exception ra ngoài: mọi lỗi được trả về qua khóa "error", để main() cách ly lỗi từng
    nhóm khi chạy --batch.
    """
    result: dict = {
        "feature_name": None,
        "output_excel_path": None,
        "review_passed": None,
        "review_score": None,
        "error": None,
        # Chỉ dùng khi đây là nhóm DUY NHẤT (không --batch): main() sys.exit() với đúng mã này
        # (guardrail invalid/lỗi -> exit 1; còn chờ làm rõ mà không tương tác được -> exit 0).
        "exit_code": None,
    }
    label_prefix = f"[{group_label}] " if group_label else ""
    try:
        active_provider, active_model = resolve_active_llm(args)

        # Guardrail Check chống spam / input vô nghĩa khi chỉ nhập text ngắn
        if len(raw_sources) == 1 and not is_safe_local_file(raw_sources[0]):
            is_valid, reason, guide = validate_requirement_input(raw_sources[0])
            if not is_valid:
                console.print(f"\n[bold red]⚠️ {label_prefix}Yêu cầu không hợp lệ:[/bold red] {reason}\n")
                console.print(Panel(guide, title="[bold yellow]Hướng dẫn Cung cấp Requirement Chuẩn[/bold yellow]", border_style="yellow"))
                result["error"] = reason
                result["exit_code"] = 1
                return result

        session = QASession(key=f"cli:{group_label or 'main'}", options=SessionOptions(
            llm_provider=active_provider,
            llm_model_name=active_model,
            llm_base_url=args.base_url,
            llm_api_key=args.api_key,
            custom_app_name=args.app,
            custom_version=args.version,
            custom_jira_link=args.jira,
            custom_sheet_name=args.sheet,
            template_excel_path=args.template,
            output_excel_path=args.output,
            max_review_iterations=args.max_iter,
        ))
        reporter = CLIReporter(label_prefix)

        console.print(f"[cyan]📁 {label_prefix}Đang tổng hợp và phân tích [bold yellow]{len(raw_sources)} nguồn tài liệu / ghi chú[/bold yellow]...[/cyan]")
        for idx, s in enumerate(raw_sources, 1):
            console.print(f"   [dim]{idx}. {escape(s[:120])}...[/dim]" if len(s) > 120 else f"   [dim]{idx}. {escape(s)}[/dim]")
        console.print(f"\n[bold green]🚀 {label_prefix}Bắt đầu thực thi Agentic Workflow (RBT Enabled)...[/bold green]\n")

        session.submit(UserTurn(sources=list(raw_sources)))
        run_session(session, reporter)

        while sys.stdin.isatty() and session.documents:
            if session.awaiting_user:
                console.print("[bold yellow]👉 Trả lời câu hỏi (tự do, từng phần hoặc gộp), gửi thêm tài liệu (đường dẫn file / mã Jira) hoặc feedback. Enter / 'exit' để kết thúc:[/bold yellow]")
            elif session.suite_ready:
                console.print("[bold yellow]👉 Feedback / tài liệu bổ sung (đường dẫn file / mã Jira) để cập nhật bộ test case ngay. Enter / 'exit' để kết thúc:[/bold yellow]")
            else:
                console.print("[bold yellow]👉 Bổ sung thông tin để chạy lại. Enter / 'exit' để kết thúc:[/bold yellow]")
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line or line.lower() in ("exit", "quit"):
                break
            session.submit(parse_cli_turn(line))
            run_session(session, reporter)

        if session.analysis:
            result["feature_name"] = session.analysis.feature_name
        if session.suite_ready:
            result["output_excel_path"] = session.output_excel_path
            if session.review_result:
                result["review_passed"] = session.review_result.passed
                result["review_score"] = session.review_result.score
        elif session.error:
            result["error"] = session.error
            result["exit_code"] = 1
        else:
            result["error"] = "Yêu cầu cần được làm rõ thêm nhưng không nhận được phản hồi (không ở chế độ tương tác hoặc User đã dừng)."
            result["exit_code"] = 0
    except Exception as e:
        console.print(f"[bold red]❌ {label_prefix}Lỗi xử lý: {escape(str(e))}[/bold red]")
        result["error"] = str(e)
        result["exit_code"] = 1
    return result


def print_batch_summary(summaries: List[Tuple[str, dict]]) -> None:
    """In bảng tổng kết kết quả của TẤT CẢ các nhóm khi chạy --batch với > 1 nhóm."""
    table = Table(title=f"📦 Tổng Kết Batch ({len(summaries)} Nhóm/Ticket)", border_style="cyan")
    table.add_column("Nhóm / Nguồn", style="cyan", width=42)
    table.add_column("Tính năng (Feature)", style="white", width=26)
    table.add_column("File Excel Xuất Ra", style="green", width=38)
    table.add_column("QA Gate", style="bold", width=18)

    success_count = 0
    for label, res in summaries:
        if res.get("error"):
            output_col = f"[bold red]FAILED[/bold red]: {res['error']}"
            gate_col = "[dim]N/A[/dim]"
        else:
            success_count += 1
            output_col = res.get("output_excel_path") or "[yellow]N/A[/yellow]"
            if res.get("review_score") is not None:
                gate_color = "green" if res.get("review_passed") else "red"
                gate_status = "PASSED" if res.get("review_passed") else "FAILED"
                gate_col = f"[{gate_color}]{gate_status} ({res['review_score']}/100)[/{gate_color}]"
            else:
                gate_col = "[yellow]N/A[/yellow]"
        table.add_row(label, res.get("feature_name") or "N/A", output_col, gate_col)
    console.print(table)

    status_color = "green" if success_count == len(summaries) else "yellow"
    console.print(f"\n[bold {status_color}]✅ {success_count}/{len(summaries)} nhóm hoàn thành thành công.[/bold {status_color}]\n")


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
    parser.add_argument("--template", default=None, help="Đường dẫn file template Excel (Mặc định: excel.template_path trong configs/config.yaml)")
    parser.add_argument("--output", default=None, help="Đường dẫn file Excel đích (Mặc định tạo file mới riêng biệt trong thư mục outputs/)")
    parser.add_argument("--max-iter", type=int, default=3, help="Số lần lặp tối đa để sửa lỗi review")
    parser.add_argument(
        "-e", "--extra", "--clarification", "--notes",
        dest="extra_info",
        default=None,
        help="Nhập thông tin bổ sung, giải thích làm rõ hoặc ghi chú nghiệp vụ kèm theo (User Clarifications)"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        default=False,
        help=(
            "Bật chế độ HÀNG LOẠT: sinh NHIỀU Test Suite độc lập trong 1 lệnh. Mỗi tham số vị trí "
            "(cách nhau bởi khoảng trắng) = 1 NHÓM/TICKET ĐỘC LẬP -> 1 Test Suite riêng. Dùng dấu "
            "PHẨY (,) BÊN TRONG một tham số để gộp thêm tài liệu bổ sung CHỈ thuộc về CHÍNH ticket đó "
            "(vd: 'VWCBT-3800,supplement_notes.docx'). Ví dụ 3 nhóm: --batch "
            "\"VWCBT-3800,supplement_notes.docx\" \"VWCBT-3801,extra_context.pdf,clarification.md\" VWCBT-3802 "
            "=> nhóm 1 = VWCBT-3800 + tài liệu riêng của nó, nhóm 2 = VWCBT-3801 + 2 tài liệu riêng, "
            "nhóm 3 = VWCBT-3802 độc lập. -e/--extra/--notes khi dùng CHUNG với --batch là ghi chú "
            "ÁP DỤNG CHUNG cho MỌI ticket trong batch; tài liệu CHỈ riêng cho 1 ticket PHẢI đính kèm "
            "qua cú pháp gộp dấu phẩy ở trên, KHÔNG dùng -e/--extra cho việc đó. Khi có > 1 nhóm, "
            "KHÔNG được dùng --output/--sheet (chỉ dành cho 1 file); hệ thống tự đặt tên file/sheet "
            "riêng biệt cho từng nhóm."
        )
    )

    args = parser.parse_args()
    active_provider, active_model = resolve_active_llm(args)

    print_banner(active_provider, active_model)

    if args.batch and getattr(args, "extra_info", None):
        console.print(
            "[yellow]⚠️  --batch kèm -e/--extra/--notes: nội dung này sẽ được áp dụng CHUNG cho "
            "TẤT CẢ ticket trong batch. Nếu tài liệu bổ sung chỉ dành riêng cho MỘT ticket cụ thể, "
            "vui lòng đính kèm bằng cú pháp gộp dấu phẩy ngay trong đúng nhóm đó của ticket, "
            "vd: 'VWCBT-3800,file_rieng.docx'.[/yellow]"
        )
    if args.batch and args.jira:
        console.print(
            "[cyan]ℹ️  --batch kèm --jira: ticket này được xử lý như 1 nhóm độc lập thêm vào batch "
            "(flag --jira KHÔNG hỗ trợ đính kèm thêm tài liệu riêng qua dấu phẩy). Để đính kèm tài "
            "liệu riêng cho từng ticket, hãy dùng cú pháp tham số vị trí \"TICKET,doc1,doc2\" thay vì "
            "--jira.[/cyan]"
        )

    groups: List[List[str]] = []
    if args.batch:
        for item in args.inputs:
            parts = [p.strip() for p in item.split(",") if p.strip()]
            if parts:
                groups.append(parts)
        if args.jira:
            groups.append([args.jira])
        if getattr(args, "extra_info", None):
            for g in groups:
                g.append(args.extra_info)
    else:
        raw_sources: List[str] = list(args.inputs)
        if args.jira:
            raw_sources.append(args.jira)
        if getattr(args, "extra_info", None):
            raw_sources.append(args.extra_info)
        groups = [raw_sources]

    if not any(groups):
        console.print("[yellow]Chưa cung cấp file hoặc mã Jira đầu vào. Đang khởi động chế độ nhập trực tiếp (Interactive Prompt)...[/yellow]")
        console.print("[cyan]Vui lòng dán nội dung User Story / Yêu cầu (hoặc kéo thả file / nhập mã Jira) và nhấn Enter:[/cyan]")
        user_input = input("> ").strip()
        if not user_input:
            console.print("[red]Lỗi: Không có nội dung yêu cầu đầu vào. Kết thúc chương trình.[/red]")
            sys.exit(1)
        groups = [[user_input]]

    if args.batch and len(groups) > 1 and (args.output or args.sheet):
        console.print(
            "[bold red]❌ Lỗi: --output/--sheet không thể dùng cùng với --batch khi có nhiều hơn 1 "
            "nhóm (mỗi nhóm cần đường dẫn/tên sheet riêng biệt). Hãy bỏ --output/--sheet để hệ thống "
            "tự đặt tên file (outputs/Testsuite_<feature>.xlsx) và tên sheet riêng cho từng nhóm.[/bold red]"
        )
        sys.exit(1)

    multi = len(groups) > 1
    summaries: List[Tuple[str, dict]] = []
    for idx, raw_sources in enumerate(groups, 1):
        label = f"Nhóm {idx}/{len(groups)}: {', '.join(s[:40] for s in raw_sources)}" if multi else None
        res = process_requirement_group(raw_sources, args, label)
        summaries.append((label or (raw_sources[0] if raw_sources else f"Nhóm {idx}"), res))
        if not multi and res.get("exit_code") is not None:
            sys.exit(res["exit_code"])

    if multi:
        print_batch_summary(summaries)
        sys.exit(0 if all(r.get("error") is None for _, r in summaries) else 1)


if __name__ == "__main__":
    main()
