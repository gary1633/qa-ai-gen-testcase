"""Phiên hội thoại tạo test case (Conversational QA Session).

Một phiên giữ toàn bộ ngữ cảnh của MỘT yêu cầu: tài liệu nguồn, câu trả lời làm rõ, thông tin bổ
sung, feedback của User và bộ test case hiện tại. User có thể gửi thêm tài liệu / câu trả lời /
feedback BẤT CỨ LÚC NÀO (kể cả khi Agent đang chạy): tin nhắn vào hộp thư `inbox` của phiên và được
worker đang chạy hấp thụ ngay tại điểm kiểm tra kế tiếp (xem `src/core/conversation.py`).
"""
import tempfile
import threading
from dataclasses import dataclass, field, fields
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, get_type_hints

from pydantic import TypeAdapter

from src.core.clarification import ASKED_QUESTION_PREFIX
from src.core.models import ClarificationAnswer, RequirementAnalysis, ReviewResult, TestCase, TestScenario

STAGE_ANALYSIS = "analysis"
STAGE_TESTCASES = "testcases"

USER_CLARIFICATION_HEADING = "## [Thông tin Bổ sung / Làm rõ từ User (User Clarifications & Overrides)]:"


def remote_upload_dir() -> str:
    """Thư mục DUY NHẤT chứa file User tải lên qua kênh từ xa (Slack/Web) — cũng là `local_file_root`
    của các phiên đó, nên không file nào khác trên server có thể bị đọc qua nội dung tin nhắn."""
    path = Path(tempfile.gettempdir()) / "qa_agentic_uploads"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


@dataclass
class SourceDocument:
    label: str
    content: str
    jira_keys: List[str] = field(default_factory=list)
    jira_links: List[str] = field(default_factory=list)


@dataclass
class UserTurn:
    """Một lượt nhắn của User. `sources`: tài liệu đính kèm (đường dẫn file, mã/link Jira); `text`: lời
    nhắn tự do (câu trả lời, feedback, thông tin bổ sung). Ở lượt ĐẦU của một yêu cầu, `text` + `sources`
    được gộp thành tài liệu yêu cầu gốc (giống `-e`/` | `: nguồn text phụ là ghi chú làm rõ)."""
    text: str = ""
    sources: List[str] = field(default_factory=list)
    delete_sources_after_read: bool = False


@dataclass
class SessionOptions:
    llm_provider: Optional[str] = None
    llm_model_name: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    custom_app_name: Optional[str] = None
    custom_version: Optional[str] = None
    custom_jira_link: Optional[str] = None
    custom_sheet_name: Optional[str] = None
    template_excel_path: Optional[str] = None
    output_excel_path: Optional[str] = None
    max_review_iterations: Optional[int] = None
    # Kênh từ xa (Slack/Web): chỉ đọc file nằm trong thư mục upload này; None = kênh tin cậy (CLI).
    local_file_root: Optional[str] = None

    @property
    def llm_kwargs(self) -> Dict[str, Optional[str]]:
        return {
            "provider": self.llm_provider,
            "model_name": self.llm_model_name,
            "base_url": self.llm_base_url,
            "api_key": self.llm_api_key,
        }


@dataclass
class QASession:
    key: str
    options: SessionOptions = field(default_factory=SessionOptions)

    # Ngữ cảnh yêu cầu
    documents: List[SourceDocument] = field(default_factory=list)
    answers: List[ClarificationAnswer] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    asked_questions: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    open_stage: str = ""

    # Kết quả hiện tại
    analysis: Optional[RequirementAnalysis] = None
    scenarios: List[TestScenario] = field(default_factory=list)
    test_cases: List[TestCase] = field(default_factory=list)
    review_result: Optional[ReviewResult] = None
    output_excel_path: Optional[str] = None
    sheet_name: Optional[str] = None
    suite_ready: bool = False
    last_change_summary: List[str] = field(default_factory=list)
    error: Optional[str] = None
    epoch: int = 0  # Tăng mỗi khi bắt đầu một yêu cầu hoàn toàn mới trong cùng phiên.

    # Việc chờ áp dụng lên bộ test case hiện có
    pending_requirement_changes: List[str] = field(default_factory=list)
    pending_feedback: List[str] = field(default_factory=list)
    needs_reanalysis: bool = False
    regenerate: bool = False

    # Hộp thư (thread-safe)
    inbox: List[UserTurn] = field(default_factory=list)
    running: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def submit(self, turn: UserTurn) -> bool:
        """Đưa lượt nhắn vào hộp thư. True = chưa có worker, caller PHẢI khởi chạy `run_session`;
        False = worker đang chạy sẽ tự hấp thụ lượt nhắn này ở điểm kiểm tra kế tiếp."""
        with self._lock:
            self.inbox.append(turn)
            if self.running:
                return False
            self.running = True
            return True

    def has_inbox(self) -> bool:
        with self._lock:
            return bool(self.inbox)

    def take_turns(self) -> List[UserTurn]:
        with self._lock:
            turns, self.inbox = self.inbox, []
            return turns

    def release(self) -> bool:
        """Kết thúc worker nếu hộp thư rỗng; False nếu vừa có lượt nhắn mới (worker phải xử lý tiếp)."""
        with self._lock:
            if self.inbox:
                return False
            self.running = False
            return True

    @property
    def awaiting_user(self) -> bool:
        return bool(self.open_questions)

    @property
    def jira_keys(self) -> List[str]:
        return [k for d in self.documents for k in d.jira_keys]

    @property
    def jira_links(self) -> List[str]:
        return [link for d in self.documents for link in d.jira_links]

    @property
    def has_pending_changes(self) -> bool:
        return bool(self.pending_requirement_changes or self.pending_feedback)

    def reset_requirement(self) -> None:
        """Bắt đầu một yêu cầu hoàn toàn mới trong cùng phiên (giữ options & hộp thư)."""
        self.documents, self.answers, self.notes = [], [], []
        self.asked_questions, self.open_questions, self.open_stage = [], [], ""
        self.analysis, self.scenarios, self.test_cases = None, [], []
        self.review_result, self.output_excel_path, self.sheet_name = None, None, None
        self.suite_ready, self.last_change_summary, self.error = False, [], None
        self.pending_requirement_changes, self.pending_feedback = [], []
        self.needs_reanalysis = self.regenerate = False
        self.epoch += 1

    def record_questions(self, questions: List[str], stage: str) -> None:
        self.open_questions = list(dict.fromkeys(questions))
        self.open_stage = stage if self.open_questions else ""
        for q in self.open_questions:
            if q not in self.asked_questions:
                self.asked_questions.append(q)

    def compose_requirement(self) -> str:
        """Gộp tài liệu + câu trả lời làm rõ + thông tin bổ sung thành MỘT tài liệu đầu vào cho Agent.
        Khối làm rõ dùng đúng tiêu đề User Clarifications mà các prompt coi là HIỆU LỰC CAO NHẤT."""
        clarifications = [
            f"{ASKED_QUESTION_PREFIX}{' '.join(a.question.split())}\n  User trả lời: {a.answer}" for a in self.answers
        ]
        clarifications += [f"- {n}" for n in self.notes]
        if len(self.documents) == 1 and not clarifications:
            return self.documents[0].content
        parts: List[str] = []
        if len(self.documents) > 1:
            parts.append("# TỔNG HỢP TÀI LIỆU YÊU CẦU (TÀI LIỆU GỐC + TÀI LIỆU USER BỔ SUNG TRONG HỘI THOẠI)")
            parts.extend(f"## [Tài liệu {i} - {d.label}]\n{d.content}" for i, d in enumerate(self.documents, 1))
        else:
            parts.extend(d.content for d in self.documents)
        if clarifications:
            parts.append(USER_CLARIFICATION_HEADING + "\n" + "\n".join(clarifications))
        return "\n\n---\n\n".join(parts)

    def snapshot(self) -> Dict[str, Any]:
        """Trạng thái hội thoại dạng JSON (không gồm options / hộp thư / khóa) để lưu và khôi phục phiên."""
        return {name: adapter.dump_python(getattr(self, name), mode="json") for name, adapter in _state_adapters().items()}

    @classmethod
    def restore(cls, key: str, options: SessionOptions, data: Dict[str, Any]) -> "QASession":
        session = cls(key=key, options=options)
        for name, adapter in _state_adapters().items():
            if name in data:
                setattr(session, name, adapter.validate_python(data[name]))
        return session


# Trường runtime không lưu: options do kênh cấp lại khi khôi phục; hộp thư/worker/khóa chỉ sống trong tiến trình.
_RUNTIME_FIELDS = frozenset({"key", "options", "inbox", "running", "_lock"})


@lru_cache(maxsize=None)
def _state_adapters() -> Dict[str, TypeAdapter]:
    hints = get_type_hints(QASession)
    return {f.name: TypeAdapter(hints[f.name]) for f in fields(QASession) if f.name not in _RUNTIME_FIELDS}


class SessionStore:
    """Kho phiên theo key hội thoại (Slack `channel:thread_ts`, `dm:channel`, nhóm batch...)."""

    def __init__(self) -> None:
        self._sessions: Dict[str, QASession] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[QASession]:
        with self._lock:
            return self._sessions.get(key)

    def get_or_create(self, key: str, options: Optional[SessionOptions] = None) -> QASession:
        with self._lock:
            session = self._sessions.get(key)
            if session is None:
                session = QASession(key=key, options=options or SessionOptions())
                self._sessions[key] = session
            return session

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
