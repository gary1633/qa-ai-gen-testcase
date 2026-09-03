import re
from typing import Tuple, Optional
from pathlib import Path
from src.integrations.jira_connector import extract_jira_key
from src.core.prompt_loader import DOMAIN_PACK_KEYWORDS
from src.utils.file_parsers import is_safe_local_file


GREETINGS_OR_CASUAL = {
    "hi", "hello", "alo", "hey", "chao", "chào", "chao bot", "chào bot", "bot oi", "bot ơi",
    "xin chao", "xin chào", "test", "testing", "check", "help", "who are you", "ban la ai",
    "bạn là ai", "test thử", "test thu", "123", "abc", "xyz", "ok", "oke", "alo bot",
    "ping", "pong", "start", "huong dan", "hướng dẫn", "giúp tôi", "giup toi", "có ai không",
    "co ai khong", "hi bot", "hello bot"
}

META_COMMAND_PATTERNS = [
    r'^(hãy\s+)?(làm|viết|tạo|generate|sinh|design)\s+(test\s*case|testcase|kich\s*ban|kịch\s*bản)(\s+(hộ|giúp|cho|giup|ho))?(\s+(mình|tôi|minh|toi|em))?(\s+(với|nhe|nhé|nha|di|đi))?$',
    r'^(làm|viết|tạo|sinh)\s+test(\s+(hộ|giúp|cho|giup|ho))?(\s+(mình|tôi|minh|toi|em))?(\s+(với|nhe|nhé|nha|di|đi))?$',
    r'^(test\s+case|testcase)(\s+(cho\s+tôi|giúp\s+tôi|hộ\s+tôi))?$',
]

NONSENSE_PATTERNS = [
    r'^[a-z0-9\s.,!?:;@#$%^&*()_+\-=\[\]{}|\'\"]{1,10}$',  # Quá ngắn dưới 10 ký tự không phải Jira
    r'^(.)\1{4,}$',                                        # Ký tự lặp lại như "aaaaa", "zzzzz", "....."
    r'^[qwertyuiopasdfghjklzxcvbnm]{5,20}$',              # Keystroke mash
    r'^(test\s*)+$',                                       # "test test test"
]

SPEC_INDICATORS = [
    "acceptance criteria", "ac:", "ac1", "ac2", "ac 1", "ac 2", "user story", "given", "when",
    "then", "mô tả", "mục tiêu", "yêu cầu", "endpoint", "request", "response", "payload", "curl",
    "quy định", "post /", "get /", "put /", "patch /", "delete /", "status code", "mã lỗi",
    "http 200", "http 400", "http 500",
] + [kw for _, keywords in DOMAIN_PACK_KEYWORDS for kw in keywords]


def validate_requirement_input(raw_input: str, file_path: Optional[str] = None) -> Tuple[bool, str, str]:
    """
    Kiểm tra chất lượng và tính hợp lệ của input yêu cầu kiểm thử.
    Chống spam, câu hỏi vô nghĩa, chào hỏi hoặc câu lệnh không có nội dung requirement.
    
    Returns:
        (is_valid, error_reason, suggested_guide)
    """
    # 1. Nếu có file đính kèm hợp lệ trên đĩa
    if file_path and is_safe_local_file(file_path):
        suffix = Path(file_path).suffix.lower()
        if suffix in [".docx", ".pdf", ".md", ".txt", ".json", ".yaml", ".yml"]:
            return True, "", ""
        return False, f"Định dạng file {suffix} không được hỗ trợ.", get_help_guide()

    if not raw_input:
        return False, "Nội dung yêu cầu trống.", get_help_guide()

    text_clean = raw_input.strip()
    text_lower = text_clean.lower()

    # 2. Kiểm tra nếu là Jira Ticket Key hoặc Jira URL (vd: VWCBT-3648)
    jira_key = extract_jira_key(text_clean)
    if jira_key:
        return True, "", ""

    # 3. Kiểm tra các câu chào / casual chat / test ngắn
    if text_lower in GREETINGS_OR_CASUAL:
        return False, "Đây là tin nhắn chào hỏi hoặc lệnh thử nghiệm, chưa có nội dung yêu cầu nghiệp vụ.", get_help_guide()

    # 4. Kiểm tra câu lệnh yêu cầu chung chung mà không kèm nội dung (Meta Commands)
    for pattern in META_COMMAND_PATTERNS:
        if re.match(pattern, text_lower):
            return False, "Bạn vừa gửi câu lệnh yêu cầu viết test case nhưng chưa đính kèm nội dung User Story, PRD hoặc mã Jira cần kiểm thử.", get_help_guide()

    # 5. Kiểm tra chuỗi vô nghĩa / spam / phím gõ linh tinh
    for pattern in NONSENSE_PATTERNS:
        if re.match(pattern, text_lower):
            return False, "Nội dung có dấu hiệu là chuỗi ký tự ngẫu nhiên hoặc spam.", get_help_guide()

    # 6. Kiểm tra độ dài và mật độ thông tin yêu cầu
    if len(text_clean) < 30:
        has_spec_indicator = any(kw in text_lower for kw in SPEC_INDICATORS)
        if not has_spec_indicator:
            return False, f"Yêu cầu quá ngắn ({len(text_clean)} ký tự) và thiếu tiêu chí nghiệp vụ (Acceptance Criteria / Rules / API Spec).", get_help_guide()

    words = text_clean.split()
    if len(words) < 6 and not any(kw in text_lower for kw in SPEC_INDICATORS):
        return False, "Yêu cầu chưa rõ ràng hoặc thiếu thông tin nghiệp vụ tối thiểu.", get_help_guide()

    return True, "", ""


def get_help_guide() -> str:
    """Trả về thông điệp hướng dẫn chuẩn khi người dùng gửi yêu cầu chưa hợp lệ."""
    return """👋 *Chào bạn! Tôi là QA Agentic Workflow Bot.*

⚠️ *Yêu cầu hiện tại chưa đủ thông tin nghiệp vụ để phân tích và sinh Test Case.*

📋 *Để sinh bộ Test Suite chuẩn 14 cột (kèm ISTQB & Banking RBT Matrix), vui lòng cung cấp một trong các hình thức sau:*

1️⃣ **Link hoặc Mã Jira Ticket:**
   • Ví dụ: `VWCBT-3648` hoặc `https://galaxyfinx.atlassian.net/browse/VWCBT-3648`

2️⃣ **File tài liệu đính kèm:**
   • Kéo thả hoặc upload file `.docx` (PRD/SRS), `.pdf`, `.md`, hoặc OpenAPI Spec `.json` / `.yaml`.

3️⃣ **Nội dung User Story & Acceptance Criteria chi tiết:**
   • *Ví dụ mẫu:*
     > **Tên tính năng:** Chuyển tiền nhanh Napas 24/7 qua Mobile App
     > **Mô tả:** Là khách hàng cá nhân, tôi muốn chuyển tiền đến STK ngân hàng khác.
     > **Acceptance Criteria (AC):**
     > - AC1: Số tiền tối thiểu 10,000 VND, tối đa 499,999,999 VND/giao dịch.
     > - AC2: Hệ thống kiểm tra số dư khả dụng và tính phí theo biểu phí hiện hành.
     > - AC3: Giao dịch trên 10 triệu VND bắt buộc xác thực sinh trắc học (QĐ 2345)."""
