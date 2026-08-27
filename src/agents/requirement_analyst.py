from typing import Optional
from src.core.models import RequirementAnalysis
from src.core.llm import invoke_structured_llm
from src.core.prompt_loader import load_prompt, load_domain_pack
from src.core.clarification import apply_clarification_gate


def analyze_requirements(
    raw_content: str,
    custom_app_name: Optional[str] = None,
    custom_version: Optional[str] = None,
    custom_jira_link: Optional[str] = None,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> RequirementAnalysis:
    """
    Phân tích yêu cầu với bộ 7 Kỹ năng Chuyên sâu của Senior QA Banking Architect.
    Prompt được nạp động từ file Markdown: prompts/01_requirement_analyst.md.
    """
    system_prompt = load_prompt("01_requirement_analyst")
    domain_pack = load_domain_pack("", raw_content[:4000])

    user_prompt = f"""DƯỚI ĐÂY LÀ TÀI LIỆU YÊU CẦU ĐẦU VÀO CẦN PHÂN TÍCH:

{raw_content}

---
METADATA GHI ĐÈ (Nếu có):
- App Name Override: {custom_app_name or 'Tự động phát hiện từ nội dung'}
- Version Override: {custom_version or 'Tự động phát hiện từ nội dung'}
- Jira / Doc Link Override: {custom_jira_link or 'Tự động phát hiện từ nội dung'}

================================================================================
DOMAIN PACK (QUY TẮC NGHIỆP VỤ ĐẶC THÙ - THAM KHẢO ĐỂ NHẬN DIỆN DOMAIN & BẤT BIẾN):
================================================================================
{domain_pack}

YÊU CẦU THỰC HIỆN:
Áp dụng BỘ 7 KỸ NĂNG PHÂN TÍCH YÊU CẦU CHUYÊN SÂU (Explicit Grounding, 360-degree Boundary Discovery, Multi-Stakeholder Analysis, Invariants, Testability, Traceability, RBT Matrix) để xuất ra Báo cáo Phân tích Yêu cầu chuẩn xác, không suy diễn sai lệch và bao phủ 100% nghiệp vụ.
"""
    result: RequirementAnalysis = invoke_structured_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=RequirementAnalysis,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1
    )
    
    if custom_app_name:
        result.app_name = custom_app_name
    if custom_version:
        result.version = custom_version
    if custom_jira_link:
        result.jira_or_doc_link = custom_jira_link
        
    return apply_clarification_gate(result, raw_content)
