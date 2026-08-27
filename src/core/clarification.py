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

NEGATION_CUE_REGEX = re.compile(
    r"\b(không|ko|chưa|chẳng|miễn|khỏi|bỏ\s+qua|no|not\s+applicable|n/?a)\b",
    re.IGNORECASE,
)
ONLY_UI_REGEX = re.compile(r"chỉ\s+(có\s+)?ui\b|ui\s+only|thuần\s+ui", re.IGNORECASE)

MISSING_API_REQUEST_QUESTION = (
    "Tài liệu chưa có sample API REQUEST cụ thể (method, endpoint, request body/payload). "
    "Vui lòng cung cấp request mẫu thật, hoặc cho biết tính năng này không có API "
    "(trả lời tự do theo ý bạn, ví dụ \"không có API\", \"tính năng này thuần UI\"... đều được, không cần đúng khuôn mẫu)."
)
MISSING_API_RESPONSE_QUESTION = (
    "Tài liệu chưa có sample API RESPONSE cụ thể (response body, HTTP status code). "
    "Vui lòng cung cấp response mẫu thật, hoặc cho biết tính năng này không có API "
    "(trả lời tự do theo ý bạn, không cần đúng khuôn mẫu)."
)
MISSING_SUCCESS_MESSAGE_QUESTION = (
    "Tài liệu chưa nêu rõ câu thông báo (message) hoặc mã lỗi cho LUỒNG THÀNH CÔNG. "
    "Vui lòng cung cấp chính xác message/mã thành công mong đợi, hoặc cho biết chưa quy định message "
    "(trả lời tự do theo ý bạn, không cần đúng khuôn mẫu)."
)
MISSING_ERROR_MESSAGE_QUESTION = (
    "Tài liệu chưa nêu rõ câu thông báo (message) hoặc mã lỗi cho LUỒNG THẤT BẠI/LỖI. "
    "Vui lòng cung cấp chính xác message/mã lỗi mong đợi, hoặc cho biết chưa quy định message "
    "(trả lời tự do theo ý bạn, không cần đúng khuôn mẫu)."
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


def _is_waived(text: str, topic_regex: re.Pattern, back_window: int = 30, fwd_window: int = 15) -> bool:
    """Chấp nhận câu trả lời TỰ DO của User thay vì bắt buộc đúng khuôn mẫu "KHÔNG CÓ API/MESSAGE":
    coi một chủ đề (api / message) là đã được miễn trừ nếu có từ phủ định (không/ko/chưa/no/n-a...)
    nằm ngay trước hoặc ngay sau lần nhắc tới chủ đề đó, bất kể diễn đạt cụ thể ra sao."""
    for m in topic_regex.finditer(text):
        before = text[max(0, m.start() - back_window):m.start()]
        after = text[m.end():m.end() + fwd_window]
        if NEGATION_CUE_REGEX.search(before) or NEGATION_CUE_REGEX.search(after):
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

    api_waived = _is_waived(text, API_HINT_REGEX) or bool(ONLY_UI_REGEX.search(text))
    if not api_waived:
        is_ui_story = bool(UI_HINT_REGEX.search(text))
        is_api_story = not is_ui_story or bool(API_HINT_REGEX.search(text))
        if is_api_story:
            if not API_REQUEST_REGEX.search(text):
                questions.append(MISSING_API_REQUEST_QUESTION)
            if not API_RESPONSE_REGEX.search(text):
                questions.append(MISSING_API_RESPONSE_QUESTION)

    if not _is_waived(text, MESSAGE_CUE_REGEX):
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
