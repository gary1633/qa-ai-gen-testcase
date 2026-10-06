"""Web GUI cho người dùng không quen CLI/Slack: một trang chat duy nhất dùng chung engine hội thoại
(`src/core/conversation.py`) với Slack Bot và CLI.

Mỗi trình duyệt có một mã (`X-Client-Id`, lưu ở localStorage) và danh sách hội thoại của riêng mình.
User gửi yêu cầu, câu trả lời, tài liệu hoặc feedback bất cứ lúc nào; worker của phiên chạy nền và đẩy
sự kiện (tiến trình / câu hỏi / kết quả / lỗi) vào nhật ký sự kiện, trang web lấy về bằng polling.
Hội thoại được lưu vào `HistoryStore` (SQLite) nên tìm lại và tiếp tục được sau khi server khởi động lại.
Khi đặt `WEB_ACCESS_PASSWORD` (bắt buộc khi đưa lên Internet), mọi request phải qua HTTP Basic Auth.
"""
import base64
import binascii
import os
import re
import secrets
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from src.agents.reviewer import gate_failure_reasons
from src.core.conversation import SuiteOutcome, run_session
from src.core.guardrail import validate_requirement_input
from src.core.session import QASession, SessionOptions, UserTurn, remote_upload_dir
from src.integrations.web_history import HistoryStore
from src.utils.excel_exporter import sanitize_filename

INDEX_HTML = Path(__file__).resolve().parent / "web" / "index.html"
DEFAULT_HISTORY_DIR = os.path.join("outputs", "web_history")
ALLOWED_UPLOAD_SUFFIXES = {".docx", ".pdf", ".md", ".markdown", ".txt", ".json", ".yaml", ".yml"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_SEARCH_TEXT_CHARS = 20000
CLIENT_ID_REGEX = re.compile(r"^[A-Za-z0-9-]{8,64}$")
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
QUEUED_NOTICE = "📝 Đã nhận! Agent đang xử lý — thông tin này sẽ được áp dụng ngay ở bước kế tiếp, không cần gửi lại."
UNTITLED = "Yêu cầu mới"
AUTH_CHALLENGE = {"WWW-Authenticate": 'Basic realm="QA Agent", charset="UTF-8"'}


class WebConversation:
    """Một hội thoại trên web: phiên QA + nhật ký sự kiện (lưu xuống lịch sử); đồng thời là `SessionReporter`."""

    def __init__(
        self,
        session_id: str,
        owner: str,
        history: HistoryStore,
        snapshot: Optional[Dict[str, Any]] = None,
        events: Optional[List[dict]] = None,
        title: str = "",
        search_text: str = "",
    ):
        self.session_id = session_id
        self.owner = owner
        self.history = history
        options = SessionOptions(local_file_root=remote_upload_dir(), output_excel_path=history.excel_path(session_id))
        key = f"web:{session_id}"
        self.session = QASession.restore(key, options, snapshot) if snapshot else QASession(key=key, options=options)
        self._events: List[dict] = list(events or [])
        self._lock = threading.Lock()
        self._title = title
        self._search_text = search_text
        self._progress_run = max((e.get("run", 0) for e in self._events if e["type"] == "progress"), default=0)
        self._deliveries = sum(1 for e in self._events if e["type"] == "result")

    @classmethod
    def from_history(cls, record: Dict[str, Any], history: HistoryStore) -> "WebConversation":
        return cls(
            record["id"], record["owner"], history,
            snapshot=record["snapshot"], events=record["events"],
            title=record["title"], search_text=record["search_text"],
        )

    # --- Nhật ký sự kiện & lưu lịch sử ---
    def emit(self, event_type: str, **data) -> None:
        with self._lock:
            data.update(type=event_type, id=len(self._events))
            self._events.append(data)
            self.history.append_event(self.session_id, data)

    def events_after(self, after: int) -> List[dict]:
        with self._lock:
            return self._events[max(after, 0):]

    @property
    def title(self) -> str:
        analysis = self.session.analysis
        return (analysis.feature_name if analysis and analysis.feature_name else self._title) or UNTITLED

    def status(self) -> str:
        s = self.session
        if s.awaiting_user:
            return "awaiting"
        if s.error:
            return "error"
        if s.suite_ready:
            return "ready"
        return "draft"

    def record_user_message(self, text: str, file_names: List[str]) -> None:
        if not self._title:
            first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
            self._title = (first_line[:80] or (file_names[0] if file_names else ""))
        self._search_text = "\n".join([self._search_text, text, *file_names]).strip()[-MAX_SEARCH_TEXT_CHARS:]
        self.emit("user", text=text, files=file_names)
        self._save(with_snapshot=False)

    def _save(self, with_snapshot: bool = True) -> None:
        """Lưu tiêu đề/trạng thái (và bản chụp phiên). Bản chụp CHỈ chụp trong luồng worker (ask/deliver/fail/
        notify) — nơi duy nhất thay đổi trạng thái phiên — nên không đọc trạng thái đang bị sửa dở."""
        analysis = self.session.analysis
        search_text = self._search_text
        if analysis:
            search_text = f"{analysis.feature_name}\n{analysis.banking_domain}\n{search_text}"
        self.history.save_conversation(
            self.session_id, self.owner, self.title, self.status(), search_text,
            snapshot=self.session.snapshot() if with_snapshot else None,
        )

    # --- SessionReporter (luôn được gọi từ luồng worker) ---
    def progress(self, lines: List[str], new: bool = False) -> None:
        if new or not self._progress_run:
            self._progress_run += 1
        self.emit("progress", run=self._progress_run, lines=list(lines))

    def notify(self, text: str) -> None:
        self.emit("notice", text=text)
        self._save()

    def ask(self, session: QASession, questions: List[str], stage: str) -> None:
        self.emit(
            "ask",
            feature=session.analysis.feature_name if session.analysis else "",
            questions=list(questions),
        )
        self._save()

    def deliver(self, session: QASession, outcome: SuiteOutcome) -> None:
        analysis, review = session.analysis, session.review_result
        issues = []
        if review and not review.passed:
            issues = [i for i in review.issues if i.severity in ("Critical", "Major")] or list(review.issues)
        self._deliveries += 1
        has_file = bool(session.output_excel_path and os.path.exists(session.output_excel_path))
        self.emit(
            "result",
            updated=outcome.updated,
            iterations=outcome.iterations,
            feature=analysis.feature_name,
            domain=analysis.banking_domain,
            app=analysis.app_name,
            version=analysis.version,
            ac_count=len(analysis.acceptance_criteria),
            tc_count=len(session.test_cases),
            score=review.score if review else None,
            passed=review.passed if review else None,
            gate_reasons=gate_failure_reasons(review) if review and not review.passed else [],
            risks=[] if outcome.updated else [
                {"id": r.risk_id, "level": r.risk_level, "score": r.risk_score, "title": r.risk_title}
                for r in analysis.product_risks[:4]
            ],
            issues=[
                {"tc": i.target_tc_id or "All Suite", "severity": i.severity, "type": i.issue_type,
                 "description": i.description, "fix": i.suggested_fix}
                for i in issues[:6]
            ],
            issue_total=len(issues),
            changes=list(outcome.change_summary),
            open_questions=list(session.open_questions),
            download=f"/api/sessions/{self.session_id}/download?v={self._deliveries}" if has_file else None,
            file_name=download_file_name(session) if has_file else None,
        )
        self._save()

    def fail(self, session: QASession, text: str) -> None:
        self.emit("error", text=text)
        self._save()

    def state(self) -> dict:
        s = self.session
        return {
            "running": s.running,
            "awaiting": s.awaiting_user,
            "suite_ready": s.suite_ready,
            "has_request": bool(s.documents),
            "title": self.title,
        }


def download_file_name(session: QASession) -> str:
    feature = session.analysis.feature_name if session.analysis else "TestSuite"
    return f"Testsuite_{sanitize_filename(feature)}.xlsx"


class ConversationStore:
    """Hội thoại đang mở trong tiến trình; hội thoại cũ được nạp lại từ lịch sử khi được truy cập."""

    def __init__(self, history: HistoryStore) -> None:
        self.history = history
        self._items: Dict[str, WebConversation] = {}
        self._lock = threading.Lock()

    def create(self, owner: str) -> WebConversation:
        conv = WebConversation(uuid.uuid4().hex, owner, self.history)
        with self._lock:
            self._items[conv.session_id] = conv
        return conv

    def get(self, session_id: str) -> WebConversation:
        with self._lock:
            conv = self._items.get(session_id)
            if conv is None:
                record = self.history.load(session_id)
                if record is None:
                    raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")
                conv = WebConversation.from_history(record, self.history)
                self._items[session_id] = conv
        return conv

    def is_running(self, session_id: str) -> bool:
        with self._lock:
            conv = self._items.get(session_id)
        return bool(conv and conv.session.running)


def _client_id(value: Optional[str]) -> str:
    if not value or not CLIENT_ID_REGEX.match(value):
        raise HTTPException(status_code=400, detail="Thiếu mã trình duyệt (X-Client-Id). Vui lòng tải lại trang.")
    return value


def _save_upload(upload: UploadFile) -> str:
    """Lưu file vào thư mục upload riêng (giữ tên gốc để Agent dẫn nguồn), giới hạn loại & dung lượng."""
    name = Path(upload.filename or "document.txt").name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"File '{name}' không được hỗ trợ. Chỉ nhận: {', '.join(sorted(ALLOWED_UPLOAD_SUFFIXES))}.",
        )
    stem = re.sub(r"[^\w.-]+", "_", Path(name).stem)[:60] or "document"
    fd, path = tempfile.mkstemp(prefix=f"{stem}__", suffix=suffix, dir=remote_upload_dir())
    size = 0
    with os.fdopen(fd, "wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                os.remove(path)
                raise HTTPException(status_code=400, detail=f"File '{name}' vượt quá {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
            out.write(chunk)
    return path


def _basic_auth_password(header: str) -> str:
    """Mật khẩu trong header `Authorization: Basic ...` (tên đăng nhập bị bỏ qua); chuỗi rỗng nếu không hợp lệ."""
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic":
        return ""
    try:
        return base64.b64decode(encoded.strip(), validate=True).decode("utf-8").partition(":")[2]
    except (binascii.Error, UnicodeDecodeError):
        return ""


def create_web_app(history_dir: Optional[str] = None, access_password: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="QA Agentic Workflow - Web GUI", docs_url=None, redoc_url=None)
    history = HistoryStore(history_dir or os.getenv("WEB_HISTORY_DIR") or DEFAULT_HISTORY_DIR)
    store = ConversationStore(history)
    password = (access_password or os.getenv("WEB_ACCESS_PASSWORD") or "").encode("utf-8")

    if password:
        @app.middleware("http")
        async def require_password(request: Request, call_next):
            given = _basic_auth_password(request.headers.get("authorization", "")).encode("utf-8")
            if not secrets.compare_digest(given, password):
                return PlainTextResponse("Cần mật khẩu để dùng QA Agent.", status_code=401, headers=AUTH_CHALLENGE)
            return await call_next(request)

    app.state.conversations = store

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(INDEX_HTML, media_type="text/html")

    @app.get("/api/conversations")
    def list_conversations(q: str = "", x_client_id: Optional[str] = Header(None)):
        items = history.list_conversations(_client_id(x_client_id), q)
        for item in items:
            item["running"] = store.is_running(item["id"])
        return {"conversations": items}

    @app.post("/api/sessions")
    def create_session(x_client_id: Optional[str] = Header(None)):
        return {"session_id": store.create(_client_id(x_client_id)).session_id}

    @app.get("/api/sessions/{session_id}/events")
    def get_events(session_id: str, after: int = 0):
        conv = store.get(session_id)
        return {"events": conv.events_after(after), "state": conv.state()}

    @app.post("/api/sessions/{session_id}/messages")
    def post_message(session_id: str, text: str = Form(""), files: List[UploadFile] = File(default=[])):
        conv = store.get(session_id)
        text = text.strip()
        if not text and not files:
            raise HTTPException(status_code=400, detail="Vui lòng nhập nội dung hoặc đính kèm tài liệu.")
        paths: List[str] = []
        try:
            for upload in files:
                paths.append(_save_upload(upload))
        except HTTPException:
            for p in paths:
                os.remove(p)
            raise

        conv.record_user_message(text, [Path(f.filename or "").name for f in files])
        if not conv.session.documents and not paths:
            # Guardrail chống spam / câu vô nghĩa chỉ áp cho yêu cầu MỚI, không áp cho câu trả lời/feedback.
            is_valid, reason, guide = validate_requirement_input(text)
            if not is_valid:
                conv.emit("guide", reason=reason, guide=guide)
                return {"accepted": False, "state": conv.state()}

        session = conv.session
        if session.submit(UserTurn(text=text, sources=paths, delete_sources_after_read=True)):
            threading.Thread(target=run_session, args=(session, conv), daemon=True).start()
        else:
            conv.emit("notice", text=QUEUED_NOTICE)
        return {"accepted": True, "state": conv.state()}

    @app.get("/api/sessions/{session_id}/download")
    def download(session_id: str):
        session = store.get(session_id).session
        path: Optional[str] = session.output_excel_path
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Chưa có file Test Suite cho cuộc trò chuyện này.")
        return FileResponse(path, media_type=XLSX_MEDIA_TYPE, filename=download_file_name(session))

    return app
