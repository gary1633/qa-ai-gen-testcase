"""Engine hội thoại tạo test case dùng chung cho Slack Bot và CLI.

Luồng: lượt nhắn của User -> `QASession.submit()` -> `run_session()` (worker) hấp thụ hộp thư, phân
loại tin nhắn (câu trả lời / tài liệu mới / thay đổi yêu cầu / feedback test case / yêu cầu mới) rồi:
- Chưa có bộ test case (hoặc User yêu cầu làm lại toàn bộ): chạy LangGraph pipeline đầy đủ; Agent
  dừng lại HỎI User khi thiếu thông tin (Clarification Gate), câu trả lời được gộp vào User
  Clarifications và pipeline chạy lại.
- Đã có bộ test case: phân tích lại yêu cầu nếu nghiệp vụ thay đổi (có thể hỏi thêm), rồi CẬP NHẬT
  TĂNG DẦN bộ test case hiện có (sửa/thêm/xóa đúng TC bị ảnh hưởng), review lại, xuất đè file Excel.
Tin nhắn đến giữa chừng được hấp thụ tại các điểm kiểm tra giữa các bước; thông tin làm thay đổi yêu
cầu trong lúc đang sinh lần đầu sẽ khởi động lại pipeline với dữ kiện mới.
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from src.core.session import (
    QASession, SourceDocument, UserTurn, STAGE_ANALYSIS, STAGE_TESTCASES,
)
from src.core.workflow import build_qa_agentic_graph
from src.core.llm import load_qa_rules
from src.agents.requirement_analyst import analyze_requirements
from src.agents.reviewer import review_and_lint_test_suite
from src.agents.testcase_reviser import revise_test_cases
from src.agents.turn_interpreter import interpret_user_turn, UserTurnInterpretation
from src.utils.excel_exporter import export_test_cases_to_excel
from src.utils.file_parsers import merge_multiple_sources, is_safe_local_file
from src.integrations.jira_connector import extract_jira_key

GENERIC_CLARIFICATION_QUESTION = (
    "Yêu cầu hiện chưa đủ rõ để viết test case. Vui lòng mô tả rõ hơn quy tắc nghiệp vụ, "
    "dữ liệu đầu vào và kết quả mong đợi."
)
SYNC_REQUIREMENT_INSTRUCTION = (
    "Yêu cầu/tài liệu vừa được cập nhật (xem khối tài liệu & User Clarifications). Đồng bộ bộ test case: "
    "sửa các test case bị ảnh hưởng, thêm test case cho AC/quy tắc mới, xóa test case không còn đúng."
)


@dataclass
class SuiteOutcome:
    updated: bool  # False: bộ test case vừa được tạo (lại) từ đầu; True: cập nhật tăng dần bộ hiện có
    iterations: int = 0
    change_summary: List[str] = field(default_factory=list)


class SessionReporter(Protocol):
    def progress(self, lines: List[str], new: bool = False) -> None: ...
    def notify(self, text: str) -> None: ...
    def ask(self, session: QASession, questions: List[str], stage: str) -> None: ...
    def deliver(self, session: QASession, outcome: SuiteOutcome) -> None: ...
    def fail(self, session: QASession, text: str) -> None: ...


class _Restart(Exception):
    """Thông tin mới đến giữa chừng làm kết quả đang chạy lỗi thời -> chạy lại với dữ kiện mới."""


def run_session(session: QASession, reporter: SessionReporter) -> None:
    """Worker của phiên: xử lý mọi lượt nhắn trong hộp thư cho tới khi hết việc. Không raise ra ngoài;
    lỗi được ghi vào `session.error` và báo qua `reporter.fail`."""
    while True:
        try:
            for turn in session.take_turns():
                _apply_turn(session, turn, reporter)
            _advance(session, reporter)
        except _Restart:
            continue
        except Exception as e:
            session.error = str(e)
            reporter.fail(session, str(e))
        if session.release():
            return


# ----------------------------------------------------------------------------------------------
# Hấp thụ lượt nhắn
# ----------------------------------------------------------------------------------------------
def _read_sources(sources: List[str], delete_after: bool, local_file_root: Optional[str]) -> SourceDocument:
    content, file_type, meta = merge_multiple_sources(sources, local_file_root)
    if delete_after:
        for src in sources:
            if is_safe_local_file(src, local_file_root):
                try:
                    os.remove(src)
                except OSError:
                    pass
    names = meta.get("source_names") or []
    label = ", ".join(names) if names else file_type
    return SourceDocument(
        label=label,
        content=content,
        jira_keys=list(meta.get("jira_keys") or []),
        jira_links=list(meta.get("jira_links") or []),
    )


def _apply_turn(session: QASession, turn: UserTurn, reporter: SessionReporter) -> None:
    if session.documents:
        _apply_followup(session, turn, reporter)
    else:
        _start_requirement(session, turn, reporter)


def _start_requirement(session: QASession, turn: UserTurn, reporter: SessionReporter) -> None:
    sources = ([turn.text.strip()] if turn.text.strip() else []) + list(turn.sources)
    if not sources:
        return
    doc = _read_sources(sources, turn.delete_sources_after_read, session.options.local_file_root)
    if not doc.content or len(doc.content.strip()) < 5:
        session.error = "Nội dung yêu cầu quá ngắn hoặc không hợp lệ."
        reporter.fail(
            session,
            "Nội dung yêu cầu quá ngắn hoặc không hợp lệ. Vui lòng cung cấp nội dung User Story/PRD "
            "hoặc đính kèm file (.docx, .pdf, .md)!",
        )
        return
    session.error = None
    session.documents = [doc]


def _interpret(session: QASession, text: str, reporter: SessionReporter) -> UserTurnInterpretation:
    try:
        return interpret_user_turn(
            message=text,
            open_questions=session.open_questions,
            feature_name=session.analysis.feature_name if session.analysis else "",
            test_case_count=len(session.test_cases),
            **session.options.llm_kwargs,
        )
    except Exception as e:
        # Không đánh rơi lời nhắn của User: ghi nhận nguyên văn như thông tin bổ sung (hiệu lực cao
        # nhất trong User Clarifications) để Agent vẫn áp dụng được ở bước kế tiếp.
        reporter.notify(f"⚠️ Không phân loại được tin nhắn ({e}). Đã ghi nhận nguyên văn như thông tin bổ sung cho yêu cầu.")
        return UserTurnInterpretation(requirement_updates=[text])


def _match_question(open_questions: List[str], question: str) -> Optional[str]:
    norm = " ".join(question.split()).casefold()
    for q in open_questions:
        q_norm = " ".join(q.split()).casefold()
        if q_norm == norm or (len(norm) >= 30 and (q_norm.startswith(norm[:60]) or norm.startswith(q_norm[:60]))):
            return q
    return None


def _mark_requirement_change(session: QASession, instruction: str) -> None:
    session.needs_reanalysis = True
    if session.suite_ready:
        session.pending_requirement_changes.append(instruction)


def _apply_followup(session: QASession, turn: UserTurn, reporter: SessionReporter) -> None:
    text = turn.text.strip()
    interp: Optional[UserTurnInterpretation] = _interpret(session, text, reporter) if text else None

    if interp and interp.starts_new_request:
        reporter.notify("🆕 Đây là một yêu cầu mới, khác tính năng đang làm -> bắt đầu bộ test case mới.")
        session.reset_requirement()
        _start_requirement(session, turn, reporter)
        return

    root = session.options.local_file_root
    new_docs: List[SourceDocument] = [_read_sources([src], turn.delete_sources_after_read, root) for src in turn.sources]
    jira_key = extract_jira_key(text) if text else None
    if jira_key and jira_key.upper() not in {k.upper() for k in session.jira_keys}:
        jira_doc = _read_sources([jira_key], False, root)
        if jira_doc.jira_links:  # Chỉ nhận khi lấy được nội dung ticket thật từ Jira.
            new_docs.append(jira_doc)
    new_docs = [d for d in new_docs if d.content.strip()]
    if new_docs:
        session.documents.extend(new_docs)
        _mark_requirement_change(session, "Tài liệu mới User vừa bổ sung: " + "; ".join(d.label for d in new_docs))

    if interp is None:
        if new_docs:
            reporter.notify("📥 Đã nhận tài liệu bổ sung: " + ", ".join(d.label for d in new_docs) + ". Sẽ cập nhật lại bộ test case.")
        return

    for ans in interp.answers:
        matched = _match_question(session.open_questions, ans.question)
        if matched:
            session.open_questions.remove(matched)
            ans.question = matched
        session.answers.append(ans)
        _mark_requirement_change(session, f"User trả lời câu hỏi làm rõ \"{ans.question}\": {ans.answer}")
    if not session.open_questions:
        session.open_stage = ""
    for update in interp.requirement_updates:
        session.notes.append(update)
        _mark_requirement_change(session, f"Thông tin/yêu cầu cập nhật từ User: {update}")
    session.pending_feedback.extend(f"Feedback của User lên bộ test case: {fb}" for fb in interp.testcase_feedback)
    if interp.regenerate_all:
        session.regenerate = True

    if interp.reply:
        reporter.notify(f"🧠 {interp.reply}")
    elif interp.is_empty and not new_docs:
        reporter.notify(
            "💬 Mình chưa thấy câu trả lời, tài liệu hay feedback nào cần áp dụng. Bạn có thể trả lời câu hỏi "
            "đang mở, gửi thêm tài liệu hoặc mô tả chỉnh sửa cần làm trên bộ test case."
        )


def _checkpoint(session: QASession, reporter: SessionReporter, restart_on_requirement_change: bool) -> None:
    """Hấp thụ tin nhắn đến giữa chừng. Khởi động lại nếu User chuyển sang yêu cầu mới, hoặc (khi đang
    sinh bộ test case từ đầu) nếu yêu cầu vừa thay đổi khiến kết quả đang chạy lỗi thời."""
    if not session.has_inbox():
        return
    epoch = session.epoch
    for turn in session.take_turns():
        _apply_turn(session, turn, reporter)
    if session.epoch != epoch:
        raise _Restart()
    if restart_on_requirement_change and (session.needs_reanalysis or session.regenerate):
        reporter.notify("🔄 Đã nhận thông tin mới giữa chừng -> chạy lại với dữ kiện mới nhất.")
        raise _Restart()


# ----------------------------------------------------------------------------------------------
# Thực thi
# ----------------------------------------------------------------------------------------------
def _waiting_for_analysis_answers(session: QASession) -> bool:
    return session.open_stage == STAGE_ANALYSIS and bool(session.open_questions) and not session.needs_reanalysis


def _advance(session: QASession, reporter: SessionReporter) -> None:
    while session.documents:
        if _waiting_for_analysis_answers(session):
            return
        if session.regenerate or not session.suite_ready:
            _generate_suite(session, reporter)
            if not session.suite_ready or session.regenerate:
                return
            continue
        if session.needs_reanalysis or session.has_pending_changes:
            if session.needs_reanalysis and not _reanalyze(session, reporter):
                return
            if session.has_pending_changes:
                _revise_suite(session, reporter)
            continue
        return


def _graph_state(session: QASession) -> dict:
    opts = session.options
    keys = session.jira_keys
    state = {
        "input_file_path": None,
        "input_raw_text": session.compose_requirement(),
        "llm_provider": opts.llm_provider,
        "llm_model_name": opts.llm_model_name,
        "llm_base_url": opts.llm_base_url,
        "llm_api_key": opts.llm_api_key,
        "custom_app_name": opts.custom_app_name,
        "custom_version": opts.custom_version,
        "custom_jira_link": ", ".join(session.jira_links) or opts.custom_jira_link,
        "custom_sheet_name": session.sheet_name or opts.custom_sheet_name or (f"{keys[0]}_Test" if keys else None),
        "prior_clarification_questions": list(session.asked_questions),
        "template_excel_path": opts.template_excel_path,
        "output_excel_path": session.output_excel_path or opts.output_excel_path,
        "logs": [],
    }
    if opts.max_review_iterations:
        state["max_review_iterations"] = opts.max_review_iterations
    return state


def _max_iterations(session: QASession) -> int:
    return session.options.max_review_iterations or load_qa_rules()["max_review_iterations"]


def _generate_suite(session: QASession, reporter: SessionReporter) -> None:
    """Chạy LangGraph pipeline đầy đủ trên toàn bộ ngữ cảnh hiện tại của phiên."""
    saved = (session.regenerate, session.needs_reanalysis, list(session.pending_requirement_changes))
    epoch = session.epoch
    session.regenerate = False
    session.needs_reanalysis = False
    session.pending_requirement_changes = []  # Đã nằm trọn trong tài liệu gộp của lần chạy này.
    session.error = None
    try:
        _run_graph(session, reporter)
    except _Restart:
        # Cùng yêu cầu, có thông tin mới -> lần chạy lại vẫn phải là "làm lại toàn bộ" nếu đang như vậy.
        if session.epoch == epoch:
            session.regenerate = session.regenerate or saved[0]
        raise
    except Exception:
        # Lỗi giữa chừng: giữ nguyên việc đang chờ để lượt nhắn kế tiếp của User chạy lại được.
        session.regenerate = session.regenerate or saved[0]
        session.needs_reanalysis = session.needs_reanalysis or saved[1]
        session.pending_requirement_changes = saved[2] + session.pending_requirement_changes
        raise


def _run_graph(session: QASession, reporter: SessionReporter) -> None:
    max_iter = _max_iterations(session)
    steps = [
        "• ⏳ *[1/5] Node 1: Đang phân tích nghiệp vụ & Bóc tách rủi ro (RBT Matrix)...*",
        "• ⚪ [2/5] Node 2: Thiết kế kịch bản kiểm thử",
        "• ⚪ [3/5] Node 3: Sinh Test Case chi tiết theo Template phiếu kiểm thử",
        "• ⚪ [4/5] Node 4: QA Quality Gate Reviewer & Linter",
        "• ⚪ [5/5] Node 5: Xuất Excel theo Template phiếu kiểm thử",
    ]
    reporter.progress(steps, new=True)

    state = _graph_state(session)
    acc = dict(state)
    for output in build_qa_agentic_graph().stream(state):
        for node_name, node_state in output.items():
            acc.update(node_state)
            if node_name == "analyze_requirement":
                analysis = node_state["requirement_analysis"]
                if analysis.needs_user_clarification:
                    steps[0] = f"• ❓ *[1/5] Node 1: Tạm dừng - Cần làm rõ {len(analysis.clarification_questions)} điểm trong yêu cầu*"
                else:
                    steps[0] = f"• ✅ *[1/5] Node 1: Phân tích xong* ({len(analysis.acceptance_criteria)} ACs, {len(analysis.product_risks)} Rủi ro RBT - _{analysis.banking_domain}_)"
                    steps[1] = "• ⏳ *[2/5] Node 2: Đang thiết kế ma trận kịch bản kiểm thử...*"
            elif node_name == "design_scenarios":
                steps[1] = f"• ✅ *[2/5] Node 2: Thiết kế xong {len(node_state['scenarios'])} kịch bản*"
                steps[2] = "• ⏳ *[3/5] Node 3: Đang sinh Test Case chi tiết...*"
            elif node_name == "generate_testcases":
                iteration = acc.get("review_iteration", 0) + 1
                steps[2] = f"• ✅ *[3/5] Node 3: Đã sinh {len(node_state['test_cases'])} Test Cases chi tiết* (Lần {iteration})"
                steps[3] = f"• ⏳ *[4/5] Node 4: QA Quality Gate & Linter đang thẩm định (Vòng {iteration}/{max_iter})...*"
            elif node_name == "review_and_lint":
                review = node_state["review_result"]
                iteration = node_state["review_iteration"]
                if review.passed:
                    steps[3] = f"• ✅ *[4/5] Node 4: QA Quality Gate: ĐẠT {review.score}/100 (PASSED ✅)*"
                elif iteration < max_iter:
                    steps[3] = f"• 🔄 *[4/5] Node 4: Điểm {review.score}/100 -> Tự động sửa {len(review.issues)} lỗi (Vòng {iteration + 1}/{max_iter})...*"
                else:
                    steps[3] = f"• ⚠️ *[4/5] Node 4: QA Gate hoàn tất ({review.score}/100)*"
                if review.passed or iteration >= max_iter:
                    steps[4] = "• ⏳ *[5/5] Node 5: Đang xuất file Excel...*"
            elif node_name == "export_excel":
                steps[4] = "• ✅ *[5/5] Node 5: Đã xuất file Excel thành công!*"
            reporter.progress(steps)
        _checkpoint(session, reporter, restart_on_requirement_change=True)

    analysis = acc["requirement_analysis"]
    if analysis.needs_user_clarification:
        if session.suite_ready:
            session.regenerate = True  # Giữ ý định "làm lại toàn bộ" tới khi User trả lời xong.
        else:
            session.analysis = analysis
        questions = analysis.clarification_questions or [GENERIC_CLARIFICATION_QUESTION]
        session.record_questions(questions, STAGE_ANALYSIS)
        reporter.ask(session, questions, STAGE_ANALYSIS)
        return

    session.analysis = analysis
    session.scenarios = acc.get("scenarios") or []
    session.test_cases = acc.get("test_cases") or []
    session.review_result = acc.get("review_result")
    session.output_excel_path = acc.get("output_excel_path")
    session.sheet_name = acc.get("generated_sheet_name")
    session.suite_ready = True
    session.last_change_summary = []
    session.record_questions(acc.get("pending_clarifications") or [], STAGE_TESTCASES)
    reporter.deliver(session, SuiteOutcome(updated=False, iterations=acc.get("review_iteration", 0)))


def _reanalyze(session: QASession, reporter: SessionReporter) -> bool:
    """Phân tích lại yêu cầu sau khi có tài liệu/câu trả lời/thông tin mới. False nếu Agent phải hỏi thêm."""
    reporter.progress(["• ⏳ *Đang phân tích lại yêu cầu với thông tin mới...*"], new=True)
    opts = session.options
    analysis = analyze_requirements(
        raw_content=session.compose_requirement(),
        custom_app_name=opts.custom_app_name,
        custom_version=opts.custom_version,
        custom_jira_link=", ".join(session.jira_links) or opts.custom_jira_link,
        prior_clarification_questions=list(session.asked_questions) or None,
        **opts.llm_kwargs,
    )
    session.needs_reanalysis = False
    if analysis.needs_user_clarification:
        questions = analysis.clarification_questions or [GENERIC_CLARIFICATION_QUESTION]
        reporter.progress([f"• ❓ *Tạm dừng - Cần làm rõ thêm {len(questions)} điểm trước khi cập nhật bộ test case*"])
        session.record_questions(questions, STAGE_ANALYSIS)
        reporter.ask(session, questions, STAGE_ANALYSIS)
        return False
    session.analysis = analysis
    reporter.progress([f"• ✅ *Đã phân tích lại yêu cầu* ({len(analysis.acceptance_criteria)} ACs, {len(analysis.product_risks)} Rủi ro RBT)"])
    return True


def _revise_suite(session: QASession, reporter: SessionReporter) -> None:
    """Cập nhật tăng dần bộ test case hiện có theo các thay đổi đang chờ, review lại, xuất đè Excel."""
    saved = (list(session.pending_requirement_changes), list(session.pending_feedback))
    instructions = list(session.pending_feedback)
    if session.pending_requirement_changes:
        instructions = [SYNC_REQUIREMENT_INSTRUCTION] + session.pending_requirement_changes + instructions
    session.pending_requirement_changes, session.pending_feedback = [], []
    session.error = None
    try:
        _run_revision(session, reporter, instructions)
    except _Restart:
        raise
    except Exception:
        session.pending_requirement_changes = saved[0] + session.pending_requirement_changes
        session.pending_feedback = saved[1] + session.pending_feedback
        raise


def _run_revision(session: QASession, reporter: SessionReporter, instructions: List[str]) -> None:
    llm = session.options.llm_kwargs
    raw_content = session.compose_requirement()
    max_iter = _max_iterations(session)

    steps = [
        f"• ⏳ *Đang cập nhật bộ test case ({len(session.test_cases)} TC) theo {len(instructions)} yêu cầu mới...*",
        "• ⚪ QA Quality Gate Reviewer & Linter",
        "• ⚪ Xuất lại file Excel",
    ]
    reporter.progress(steps, new=True)
    revision = revise_test_cases(
        analysis=session.analysis, test_cases=session.test_cases, instructions=instructions,
        raw_content=raw_content, open_questions=session.open_questions, **llm,
    )
    test_cases, questions, changes = revision.test_cases, revision.clarification_questions, list(revision.change_summary)
    steps[0] = f"• ✅ *Đã cập nhật bộ test case* ({len(test_cases)} TC, {len(changes)} thay đổi)"

    iteration = 0
    while True:
        _checkpoint(session, reporter, restart_on_requirement_change=False)
        iteration += 1
        steps[1] = f"• ⏳ *QA Quality Gate & Linter đang thẩm định (Vòng {iteration}/{max_iter})...*"
        reporter.progress(steps)
        review = review_and_lint_test_suite(
            analysis=session.analysis, test_cases=test_cases, raw_content=raw_content, **llm,
        )
        blocking = [i for i in review.issues if i.severity in ("Critical", "Major")]
        if review.passed or iteration >= max_iter or not blocking:
            break
        steps[1] = f"• 🔄 *Điểm {review.score}/100 -> Tự động sửa {len(blocking)} lỗi (Vòng {iteration + 1}/{max_iter})...*"
        reporter.progress(steps)
        fix = revise_test_cases(
            analysis=session.analysis, test_cases=test_cases,
            instructions=[
                f"QA Reviewer [{i.target_tc_id or 'All Suite'}] {i.issue_type} ({i.severity}): {i.description} -> Khắc phục: {i.suggested_fix}"
                for i in blocking
            ],
            raw_content=raw_content, open_questions=questions, **llm,
        )
        test_cases, questions = fix.test_cases, fix.clarification_questions
        changes.extend(fix.change_summary)

    steps[1] = (
        f"• ✅ *QA Quality Gate: ĐẠT {review.score}/100 (PASSED ✅)*" if review.passed
        else f"• ⚠️ *QA Gate hoàn tất ({review.score}/100)*"
    )
    steps[2] = "• ⏳ *Đang xuất lại file Excel...*"
    reporter.progress(steps)
    output_path = export_test_cases_to_excel(
        analysis=session.analysis,
        test_cases=test_cases,
        template_path=session.options.template_excel_path,
        output_path=session.output_excel_path,
        target_sheet_name=session.sheet_name,
        pending_clarifications=questions,
    )
    steps[2] = "• ✅ *Đã xuất lại file Excel!*"
    reporter.progress(steps)

    session.test_cases = test_cases
    session.review_result = review
    session.output_excel_path = output_path
    session.last_change_summary = changes
    session.record_questions(questions, STAGE_TESTCASES)
    reporter.deliver(session, SuiteOutcome(updated=True, iterations=iteration, change_summary=changes))
