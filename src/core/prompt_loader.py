import os
from pathlib import Path
from functools import lru_cache

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


@lru_cache(maxsize=32)
def load_prompt(prompt_name: str, fallback_text: str = "") -> str:
    """
    Tự động đọc nội dung file prompt Markdown từ thư mục prompts/.
    Ví dụ: load_prompt("01_requirement_analyst") sẽ đọc file prompts/01_requirement_analyst.md.
    """
    if not prompt_name.endswith(".md"):
        file_name = f"{prompt_name}.md"
    else:
        file_name = prompt_name

    prompt_path = PROMPTS_DIR / file_name

    if prompt_path.exists():
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception as e:
            print(f"[WARN] Không thể đọc file prompt {prompt_path}: {e}")

    return fallback_text
