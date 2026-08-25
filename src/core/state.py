from typing import TypedDict, List, Optional, Dict, Any
from src.core.models import (
    RequirementAnalysis,
    TestScenario,
    TestCase,
    ReviewResult,
)


class QAWorkflowState(TypedDict, total=False):
    # Input data
    input_file_path: Optional[str]
    input_raw_text: str
    file_type: str  # 'md', 'txt', 'docx', 'pdf'
    
    # Per-User LLM Model Configuration
    llm_provider: Optional[str]      # 'google', 'openai', 'anthropic', 'deepseek', 'ollama', 'openrouter', 'custom'
    llm_model_name: Optional[str]    # 'gemini-2.0-flash', 'gpt-4o', 'claude-3-5-sonnet-20241022', etc.
    llm_base_url: Optional[str]      # Custom endpoint URL
    llm_api_key: Optional[str]       # Custom API Key
    
    # Metadata overrides if provided
    custom_app_name: Optional[str]
    custom_version: Optional[str]
    custom_jira_link: Optional[str]
    custom_sheet_name: Optional[str]
    
    # Agent Artifacts
    requirement_analysis: Optional[RequirementAnalysis]
    scenarios: List[TestScenario]
    test_cases: List[TestCase]
    review_result: Optional[ReviewResult]
    
    # Workflow Loop & Quality Control
    review_iteration: int
    max_review_iterations: int
    feedback_history: List[str]
    
    # Final Output
    template_excel_path: str
    output_excel_path: Optional[str]
    generated_sheet_name: Optional[str]
    
    # Execution trace / logs for visual CLI
    logs: List[Dict[str, Any]]
