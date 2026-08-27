import re
from typing import List
from src.core.models import RequirementAnalysis

PENDING_CLARIFICATION_MARKER = "PENDING CLARIFICATION"

API_REQUEST_REGEX = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\s+/|request\s+body|\bpayload\b|\brequest\s*:",
    re.IGNORECASE,
)
API_RESPONSE_REGEX = re.compile(
    r"response\s+body|\bresponse\s*:|\bHTTP\s*[1-5]\d{2}\b|\bstatus\s*code\b|trả\s+về",
    re.IGNORECASE,
)

API_HINT_REGEX = re.compile(r"\bapi\b|\bendpoint\b|tích\s+hợp", re.IGNORECASE)
UI_HINT_REGEX = re.compile(
    r"\bui\b|giao\s+diện|màn\s+hình|hiển\s+thị|frontend|front-end|\bscreen\b|\bbutton\b|nút\s+bấm",
    re.IGNORECASE,
)

MESSAGE_CUE_REGEX = re.compile(r"\bmessage\b|\bmsg\b|thông\s+báo|error[_\s]?code|mã\s+lỗi", re.IGNORECASE)
MESSAGE_SUCCESS_CUE_REGEX = re.compile(r"thành\s+công|success|hoàn\s+tất|\bOK\b|\bHTTP\s*200\b", re.IGNORECASE)
MESSAGE_ERROR_CUE_REGEX = re.compile(
    r"thất\s+bại|lỗi|error|từ\s+chối|reject|\bHTTP\s*[45]\d{2}\b|\b[A-Z]{2,}[_-]\d{2,}\b",
    re.IGNORECASE,
)

API_WAIVER_REGEX = re.compile(
    r"(no[_\s]?api|không\s+có\s+api|không\s+áp\s+dụng\s+api|chỉ\s+ui|ui\s+only|thuần\s+ui)",
    re.IGNORECASE,
)
MESSAGE_WAIVER_REGEX = re.compile(
    r"(no[_\s]?message|không\s+có\s+message|không\s+quy\s+định\s+message|"
    r"message\s+theo\s+chuẩn\s+hệ\s+thống)",
    re.IGNORECASE,
)

MISSING_API_REQUEST_QUESTION = (
    "Tài liệu chưa có sample API REQUEST cụ thể (method, endpoint, request body/payload). "
    "Vui lòng cung cấp request mẫu thật, hoặc trả lời \"KHÔNG CÓ API\" nếu tính năng này không có API."
)
MISSING_API_RESPONSE_QUESTION = (
    "Tài liệu chưa có sample API RESPONSE cụ thể (response body, HTTP status code). "
    "Vui lòng cung cấp response mẫu thật, hoặc trả lời \"KHÔNG CÓ API\" nếu tính năng này không có API."
)
MISSING_SUCCESS_MESSAGE_QUESTION = (
    "Tài liệu chưa nêu rõ câu thông báo (message) hoặc mã lỗi cho LUỒNG THÀNH CÔNG. "
    "Vui lòng cung cấp chính xác message/mã thành công mong đợi, hoặc trả lời \"KHÔNG CÓ MESSAGE\" nếu chưa quy định."
)
MISSING_ERROR_MESSAGE_QUESTION = (
    "Tài liệu chưa nêu rõ câu thông báo (message) hoặc mã lỗi cho LUỒNG THẤT BẠI/LỖI. "
    "Vui lòng cung cấp chính xác message/mã lỗi mong đợi, hoặc trả lời \"KHÔNG CÓ MESSAGE\" nếu chưa quy định."
)


def _has_message_cue_near(text: str, outcome_regex: re.Pattern, window: int = 80) -> bool:
    """True nếu có một từ khóa message/thông báo/mã lỗi nằm gần (trong `window` ký tự) một từ khóa
    mô tả kết quả (thành công/thất bại) — tránh chấp nhận message chung chung không rõ áp dụng cho
    luồng nào."""
    for m in MESSAGE_CUE_REGEX.finditer(text):
        ctx = text[max(0, m.start() - window):m.end() + window]
        if outcome_regex.search(ctx):
            return True
    return False


def detect_missing_artifacts(raw_content: str) -> List[str]:
    """Phát hiện xác định (deterministic) các dữ kiện bắt buộc còn thiếu trong tài liệu đầu vào.

    API — mặc định: concept của User Story được ASSUME LÀ CHO API (backend/API-first). Nếu tài liệu
    có yếu tố UI mà KHÔNG tự nhắc tới việc làm API thì bỏ qua nhóm câu hỏi API (coi là UI-only).
    Khi câu chuyện được coi là API (mặc định, hoặc UI có nhắc API): BẮT BUỘC phải rõ CẢ sample
    REQUEST lẫn RESPONSE — thiếu bên nào hỏi riêng bên đó, không chấp nhận có 1 trong 2 là đủ.

    Message — áp dụng chung cho mọi loại tài liệu (kể cả UI): BẮT BUỘC phải rõ CẢ message/mã cho
    luồng THÀNH CÔNG lẫn luồng THẤT BẠI/LỖI — thiếu bên nào hỏi riêng bên đó.
    """
    text = raw_content or ""
    questions: List[str] = []

    if not API_WAIVER_REGEX.search(text):
        is_ui_story = bool(UI_HINT_REGEX.search(text))
        is_api_story = not is_ui_story or bool(API_HINT_REGEX.search(text))
        if is_api_story:
            if not API_REQUEST_REGEX.search(text):
                questions.append(MISSING_API_REQUEST_QUESTION)
            if not API_RESPONSE_REGEX.search(text):
                questions.append(MISSING_API_RESPONSE_QUESTION)

    if not MESSAGE_WAIVER_REGEX.search(text):
        if not _has_message_cue_near(text, MESSAGE_SUCCESS_CUE_REGEX):
            questions.append(MISSING_SUCCESS_MESSAGE_QUESTION)
        if not _has_message_cue_near(text, MESSAGE_ERROR_CUE_REGEX):
            questions.append(MISSING_ERROR_MESSAGE_QUESTION)

    return questions


def apply_clarification_gate(analysis: RequirementAnalysis, raw_content: str) -> RequirementAnalysis:
    """Hợp nhất câu hỏi xác định vào analysis và BẮT BUỘC bật cờ chặn nếu còn dữ kiện thiếu."""
    deterministic = detect_missing_artifacts(raw_content)
    if deterministic:
        merged = list(analysis.clarification_questions)
        for q in deterministic:
            if q not in merged:
                merged.append(q)
        analysis.clarification_questions = merged
        analysis.needs_user_clarification = True
    return analysis
