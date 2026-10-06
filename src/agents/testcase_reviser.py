import json
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from src.core.models import RequirementAnalysis, TestCase
from src.core.llm import invoke_structured_llm
from src.core.prompt_loader import load_composite, load_domain_pack
from src.agents.testcase_generator import finalize_test_suite


class TestSuiteRevision(BaseModel):
    updated_test_cases: List[TestCase] = Field(default_factory=list, description="Bản đầy đủ của các test case cần sửa, giữ đúng testcase_id hiện tại")
    added_test_cases: List[TestCase] = Field(default_factory=list, description="Test case mới cần thêm (testcase_id để trống, hệ thống tự đánh số)")
    removed_testcase_ids: List[str] = Field(default_factory=list, description="Mã các test case cần xóa")
    change_summary: List[str] = Field(default_factory=list, description="Mô tả ngắn gọn từng thay đổi, nêu mã TC hiện tại")
    clarification_questions: List[str] = Field(default_factory=list, description="Câu hỏi làm rõ CÒN MỞ sau lượt cập nhật; không bịa dữ liệu thay cho việc hỏi")


class TestSuiteRevisionResult(BaseModel):
    test_cases: List[TestCase] = Field(default_factory=list)
    clarification_questions: List[str] = Field(default_factory=list)
    change_summary: List[str] = Field(default_factory=list)


def _normalize_id(tc_id: str) -> str:
    digits = "".join(ch for ch in (tc_id or "") if ch.isdigit())
    return f"TC {int(digits):02d}" if digits else (tc_id or "").strip().upper()


def apply_revision(test_cases: List[TestCase], revision: TestSuiteRevision) -> List[TestCase]:
    """Áp các thao tác sửa/xóa/thêm lên bộ test case hiện tại, giữ nguyên thứ tự; test case mới được
    chèn ngay sau test case cuối cùng cùng nhóm con (hoặc cùng nhóm lớn), nếu không có thì nối cuối."""
    removed = {_normalize_id(i) for i in revision.removed_testcase_ids}
    updates: Dict[str, TestCase] = {_normalize_id(tc.testcase_id): tc for tc in revision.updated_test_cases}

    suite: List[TestCase] = []
    unmatched_updates = dict(updates)
    for tc in test_cases:
        key = _normalize_id(tc.testcase_id)
        if key in removed:
            unmatched_updates.pop(key, None)
            continue
        replacement = unmatched_updates.pop(key, None)
        suite.append(replacement if replacement is not None else tc)

    # Bản "sửa" trỏ tới mã không tồn tại thực chất là test case mới.
    additions = list(unmatched_updates.values()) + list(revision.added_test_cases)
    for new_tc in additions:
        insert_at = len(suite)
        for attr in ("group_functional", "group_feature"):
            positions = [i for i, tc in enumerate(suite) if getattr(tc, attr) and getattr(tc, attr) == getattr(new_tc, attr)]
            if positions:
                insert_at = positions[-1] + 1
                break
        suite.insert(insert_at, new_tc)
    return suite


def revise_test_cases(
    analysis: RequirementAnalysis,
    test_cases: List[TestCase],
    instructions: List[str],
    raw_content: str = "",
    open_questions: Optional[List[str]] = None,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> TestSuiteRevisionResult:
    """Cập nhật TĂNG DẦN bộ test case hiện có theo các yêu cầu trong hội thoại (feedback, câu trả lời
    làm rõ, tài liệu/yêu cầu mới, lỗi reviewer) thay vì sinh lại toàn bộ từ đầu.
    Prompt: prompts/05_testcase_reviser.md + prompts/shared/severity_priority_rubric.md."""
    system_prompt = load_composite("05_testcase_reviser", "shared/severity_priority_rubric")
    domain_pack = load_domain_pack(analysis.banking_domain, analysis.feature_name, analysis.scope_text)
    ac_text = "\n".join(
        f"- [{ac.ac_id}] {ac.title}: {ac.description} (Rules: {', '.join(ac.business_rules) if ac.business_rules else 'N/A'})"
        for ac in analysis.acceptance_criteria
    ) or "(Chưa bóc tách AC)"
    risk_text = "\n".join(f"- [{r.risk_id}] {r.risk_level}: {r.risk_title}" for r in analysis.product_risks) or "(Không có)"
    suite_json = json.dumps(
        [tc.model_dump(exclude={"test_status"}) for tc in test_cases], ensure_ascii=False, indent=1
    )
    instructions_text = "\n".join(f"{i}. {item}" for i, item in enumerate(instructions, 1))
    questions_text = "\n".join(f"- {q}" for q in (open_questions or [])) or "(Không có)"

    user_prompt = f"""TÍNH NĂNG: {analysis.feature_name}
PHÂN HỆ: {analysis.banking_domain}

TIÊU CHÍ NGHIỆM THU HIỆN TẠI:
{ac_text}

MA TRẬN RỦI RO RBT:
{risk_text}

================================================================================
DOMAIN PACK (CHECKLIST TỔNG QUÁT — KHÔNG PHẢI NGUỒN GIÁ TRỊ):
================================================================================
{domain_pack}

================================================================================
TÀI LIỆU GỐC + TÀI LIỆU BỔ SUNG + LÀM RÕ TỪ USER (NGUỒN SỰ THẬT):
================================================================================
{raw_content or "(Không có tài liệu gốc)"}

================================================================================
BỘ TEST CASE HIỆN TẠI ({len(test_cases)} test case, JSON):
================================================================================
{suite_json}

CÁC CÂU HỎI LÀM RÕ ĐANG MỞ TRƯỚC LƯỢT NÀY:
{questions_text}

================================================================================
YÊU CẦU CẬP NHẬT TRONG LƯỢT NÀY (BẮT BUỘC XỬ LÝ HẾT):
================================================================================
{instructions_text}
"""
    revision: TestSuiteRevision = invoke_structured_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=TestSuiteRevision,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1,
    )
    finalized = finalize_test_suite(apply_revision(test_cases, revision), revision.clarification_questions)
    return TestSuiteRevisionResult(
        test_cases=finalized.test_cases,
        clarification_questions=finalized.clarification_questions,
        change_summary=revision.change_summary,
    )
