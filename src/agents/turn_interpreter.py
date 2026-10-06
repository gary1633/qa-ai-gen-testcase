from typing import List, Optional
from pydantic import BaseModel, Field
from src.core.models import ClarificationAnswer
from src.core.llm import invoke_structured_llm
from src.core.prompt_loader import load_prompt


class UserTurnInterpretation(BaseModel):
    answers: List[ClarificationAnswer] = Field(default_factory=list, description="Câu trả lời cho các câu hỏi đang mở; `question` chép nguyên văn câu hỏi")
    requirement_updates: List[str] = Field(default_factory=list, description="Thông tin nghiệp vụ mới / thay đổi yêu cầu, ghi trung thành với lời User")
    testcase_feedback: List[str] = Field(default_factory=list, description="Yêu cầu chỉnh sửa bộ test case hiện có (sửa/xóa/thêm/đổi priority...)")
    regenerate_all: bool = Field(default=False, description="True CHỈ khi User yêu cầu rõ viết lại toàn bộ bộ test case từ đầu")
    starts_new_request: bool = Field(default=False, description="True CHỈ khi tin nhắn là yêu cầu/ticket hoàn toàn khác tính năng đang làm")
    reply: str = Field(default="", description="1-2 câu xác nhận ngắn gọn Agent đã hiểu gì và sẽ làm gì")

    @property
    def is_empty(self) -> bool:
        return not (self.answers or self.requirement_updates or self.testcase_feedback
                    or self.regenerate_all or self.starts_new_request)


def interpret_user_turn(
    message: str,
    open_questions: List[str],
    feature_name: str = "",
    test_case_count: int = 0,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> UserTurnInterpretation:
    """Phân loại tin nhắn tự do của User giữa hội thoại thành câu trả lời / thay đổi yêu cầu / feedback test case."""
    questions_text = "\n".join(f"{i}. {q}" for i, q in enumerate(open_questions, 1)) or "(Không có câu hỏi nào đang mở)"
    suite_text = f"Đã có {test_case_count} test case" if test_case_count else "Chưa có bộ test case (Agent đang phân tích / sinh lần đầu)"
    user_prompt = f"""TÍNH NĂNG ĐANG LÀM: {feature_name or '(chưa xác định)'}
TRẠNG THÁI BỘ TEST CASE: {suite_text}

CÁC CÂU HỎI ĐANG MỞ AGENT ĐÃ HỎI USER:
{questions_text}

TIN NHẮN MỚI NHẤT CỦA USER:
\"\"\"
{message}
\"\"\"
"""
    return invoke_structured_llm(
        system_prompt=load_prompt("06_turn_interpreter"),
        user_prompt=user_prompt,
        schema=UserTurnInterpretation,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.0,
    )
