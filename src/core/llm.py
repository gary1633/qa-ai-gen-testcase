import os
import re
import time
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, Type, TypeVar
from pydantic import BaseModel
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

T = TypeVar("T", bound=BaseModel)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "config.yaml"


def load_config() -> Dict[str, Any]:
    """Đọc file cấu hình config.yaml mặc định"""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_qa_rules() -> Dict[str, Any]:
    """Đọc block qa_rules từ config.yaml, có giá trị mặc định an toàn."""
    rules = load_config().get("qa_rules") or {}
    return {
        "min_review_score": int(rules.get("min_review_score", 95)),
        "max_review_iterations": int(rules.get("max_review_iterations", 3)),
        "strict_assertion_required": bool(rules.get("strict_assertion_required", True)),
        "banned_vague_words": list(rules.get("banned_vague_words") or []),
    }


def detect_provider(provider: Optional[str] = None, model_name: Optional[str] = None) -> str:
    """Tự động nhận diện provider từ tên model hoặc biến môi trường"""
    if provider:
        return provider.lower()
    
    env_provider = os.getenv("LLM_PROVIDER")
    if env_provider:
        return env_provider.lower()
        
    config_provider = load_config().get("model", {}).get("provider")
    if config_provider:
        return config_provider.lower()

    if model_name:
        m = model_name.lower()
        if "gpt" in m or "o1" in m or "o3" in m:
            return "openai"
        if "claude" in m:
            return "anthropic"
        if "gemini" in m:
            return "google"
        if "deepseek" in m:
            return "deepseek"
        if "qwen" in m or "llama" in m or "mistral" in m:
            return "ollama"

    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "google"

    return "google"


def get_llm(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.1,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    request_timeout: Optional[float] = None
) -> BaseChatModel:
    """
    Universal LLM Factory khởi tạo Chat Model cho bất kỳ Provider nào.
    """
    config = load_config().get("model", {})
    target_timeout = request_timeout or config.get("request_timeout_seconds") or 120
    target_provider = detect_provider(provider, model_name)
    
    # 1. GOOGLE GEMINI
    if target_provider in ["google", "gemini"]:
        from langchain_google_genai import ChatGoogleGenerativeAI
        target_model = model_name or os.getenv("GEMINI_MODEL_NAME") or config.get("name") or "gemini-3.6-flash"
        target_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        return ChatGoogleGenerativeAI(
            model=target_model,
            temperature=temperature,
            google_api_key=target_key,
            max_output_tokens=8192,
            timeout=target_timeout,
        )

    # 2. OPENAI
    elif target_provider in ["openai"]:
        from langchain_openai import ChatOpenAI
        target_model = model_name or os.getenv("OPENAI_MODEL_NAME") or config.get("name") or "gpt-4o"
        target_key = api_key or os.getenv("OPENAI_API_KEY")
        target_base_url = base_url or os.getenv("OPENAI_BASE_URL")
        return ChatOpenAI(
            model=target_model,
            temperature=temperature,
            api_key=target_key,
            base_url=target_base_url,
            max_tokens=8192,
            timeout=target_timeout,
        )

    # 3. ANTHROPIC CLAUDE
    elif target_provider in ["anthropic", "claude"]:
        from langchain_anthropic import ChatAnthropic
        target_model = model_name or os.getenv("ANTHROPIC_MODEL_NAME") or config.get("name") or "claude-3-5-sonnet-20241022"
        target_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        return ChatAnthropic(
            model=target_model,
            temperature=temperature,
            api_key=target_key,
            max_tokens=8192,
            timeout=target_timeout,
        )

    # 4. DEEPSEEK
    elif target_provider in ["deepseek"]:
        from langchain_openai import ChatOpenAI
        target_model = model_name or os.getenv("DEEPSEEK_MODEL_NAME") or config.get("name") or "deepseek-chat"
        target_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        target_base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        return ChatOpenAI(
            model=target_model,
            temperature=temperature,
            api_key=target_key,
            base_url=target_base_url,
            max_tokens=8192,
            timeout=target_timeout,
        )

    # 5. OPENROUTER
    elif target_provider in ["openrouter"]:
        from langchain_openai import ChatOpenAI
        target_model = model_name or os.getenv("OPENROUTER_MODEL_NAME") or config.get("name") or "google/gemini-2.0-flash-001"
        target_key = api_key or os.getenv("OPENROUTER_API_KEY")
        return ChatOpenAI(
            model=target_model,
            temperature=temperature,
            api_key=target_key,
            base_url="https://openrouter.ai/api/v1",
            max_tokens=8192,
            timeout=target_timeout,
        )

    # 6. OLLAMA / LOCAL LLM
    elif target_provider in ["ollama", "local"]:
        from langchain_openai import ChatOpenAI
        target_model = model_name or os.getenv("OLLAMA_MODEL_NAME") or config.get("name") or "qwen2.5:14b"
        target_base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return ChatOpenAI(
            model=target_model,
            temperature=temperature,
            api_key="ollama",
            base_url=target_base_url,
            max_tokens=8192,
            timeout=target_timeout,
        )

    # 7. CUSTOM / VLLM / AZURE / OTHER OPENAI-COMPATIBLE
    else:
        from langchain_openai import ChatOpenAI
        target_model = model_name or os.getenv("LLM_MODEL") or config.get("name") or "custom-model"
        target_key = api_key or os.getenv("LLM_API_KEY", "custom-key")
        target_base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
        return ChatOpenAI(
            model=target_model,
            temperature=temperature,
            api_key=target_key,
            base_url=target_base_url,
            max_tokens=8192,
            timeout=target_timeout,
        )


def _extract_retry_seconds(error_str: str) -> int:
    """Trích xuất thời gian chờ từ thông báo lỗi Rate Limit 429"""
    match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
    if match:
        return max(5, min(int(float(match.group(1))) + 2, 40))
    match_delay = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)s?", error_str)
    if match_delay:
        return max(5, min(int(match_delay.group(1)) + 2, 40))
    return 20


def invoke_structured_llm(
    system_prompt: str,
    user_prompt: str,
    schema: Type[T],
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.1,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_retries: int = 4,
    request_timeout: Optional[float] = None
) -> T:
    """
    Gọi LLM với Structured Output ép kiểu theo Pydantic schema trên bất kỳ Provider nào.
    Tích hợp cơ chế tự động xử lý Rate Limit 429 (Resource Exhausted), Timeout mạng và Fallback thông minh.
    Mỗi request LLM có giới hạn thời gian chờ (`request_timeout`, mặc định lấy từ `configs/config.yaml` -> `model.request_timeout_seconds`,
    hoặc 120s nếu không cấu hình) để KHÔNG BAO GIỜ treo vô thời hạn khi provider không phản hồi.
    """
    active_model = model_name or os.getenv("GEMINI_MODEL_NAME") or "gemini-3.6-flash"
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    for attempt in range(1, max_retries + 1):
        try:
            llm = get_llm(
                provider=provider,
                model_name=active_model,
                temperature=temperature,
                base_url=base_url,
                api_key=api_key,
                request_timeout=request_timeout
            )
            structured_llm = llm.with_structured_output(schema)
            result = structured_llm.invoke(messages)
            return result

        except Exception as e:
            err_str = str(e)
            exc_name = type(e).__name__.lower()
            is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate limit" in err_str.lower()
            is_timeout = (
                isinstance(e, TimeoutError)
                or "timeout" in exc_name
                or "timeout" in err_str.lower()
                or "timed out" in err_str.lower()
                or "deadline exceeded" in err_str.lower()
            )

            # Nếu chạm giới hạn Free Tier ngày của gemini-3.7-flash -> Fallback ngay sang gemini-3.6-flash
            if is_429 and ("gemini-3.7-flash" in active_model or "GenerateRequestsPerDay" in err_str):
                print(f"⚠️ [Rate Limit] Model '{active_model}' chạm hạn mức Free Tier. Tự động chuyển sang 'gemini-3.6-flash'...")
                active_model = "gemini-3.6-flash"
                time.sleep(2)
                continue

            if is_429 and attempt < max_retries:
                wait_time = _extract_retry_seconds(err_str)
                print(f"⏳ [Rate Limit 429] Đạt ngưỡng giới hạn request của AI. Tự động chờ {wait_time}s rồi thử lại (Lần {attempt}/{max_retries})...")
                time.sleep(wait_time)
            elif is_timeout and attempt < max_retries:
                print(f"⏳ [Timeout] Provider '{active_model}' không phản hồi trong thời gian cho phép. Tự động thử lại (Lần {attempt}/{max_retries})...")
                time.sleep(3)
            else:
                raise e
