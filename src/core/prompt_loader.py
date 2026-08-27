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

DOMAIN_PACK_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("fintech-banking",      ("fintech", "banking", "ngân hàng", "payment", "thanh toán", "napas",
                              "vietqr", "core banking", "wallet", "ví điện tử", "casa", "ledger", "sổ cái")),
    ("ecommerce-retail",     ("ecommerce", "e-commerce", "retail", "shop", "cart", "giỏ hàng",
                              "đơn hàng", "tồn kho", "inventory", "voucher", "khuyến mãi", "checkout")),
    ("healthcare",           ("healthcare", "hospital", "medical", "y tế", "bệnh án", "bệnh viện",
                              "patient", "bệnh nhân", "phi", "hl7", "fhir", "ehr")),
    ("logistics-supplychain",("logistics", "supply chain", "vận chuyển", "giao hàng", "delivery",
                              "fleet", "warehouse", "kho vận", "tracking", "parcel", "cod")),
    ("saas-b2b",             ("saas", "b2b", "enterprise", "multi-tenant", "multitenant", "tenant",
                              "subscription", "thuê bao", "seat", "workspace")),
]
DEFAULT_DOMAIN_PACK = "api-platform"


def resolve_domain_pack(domain: str, feature_name: str = "") -> str:
    """Chọn domain pack theo từ khóa; mặc định 'api-platform' nếu không khớp."""
    haystack = f"{domain} {feature_name}".lower()
    for pack_name, keywords in DOMAIN_PACK_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return pack_name
    return DEFAULT_DOMAIN_PACK


def load_domain_pack(domain: str, feature_name: str = "") -> str:
    """Đọc prompts/domains/<pack>.md; trả về "" nếu file không tồn tại."""
    pack_name = resolve_domain_pack(domain, feature_name)
    return load_prompt(f"domains/{pack_name}")


def load_composite(base_name: str, *extra_names: str) -> str:
    """Ghép nội dung base_name và các extra_names (vd: rubric dùng chung), bỏ qua phần rỗng."""
    parts = [load_prompt(base_name)]
    for name in extra_names:
        parts.append(load_prompt(name))
    return "\n\n---\n\n".join(p for p in parts if p)
