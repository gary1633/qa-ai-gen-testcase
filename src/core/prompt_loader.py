import re
from pathlib import Path
from functools import lru_cache
from typing import List, Tuple

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

DOMAIN_PACK_KEYWORDS: List[Tuple[str, Tuple[str, ...]]] = [
    ("fintech-banking",      ("fintech", "banking", "ngân hàng", "core banking", "payment", "payments", "thanh toán",
                              "chuyển tiền", "chuyển khoản", "napas", "vietqr", "citad", "swift", "wallet",
                              "ví điện tử", "casa", "ledger", "sổ cái", "khoản vay", "cho vay", "vay", "loan", "loans",
                              "lending", "giải ngân", "dư nợ", "thu nợ", "thấu chi", "overdraft", "tín dụng",
                              "thẻ tín dụng", "thẻ ghi nợ", "thẻ trả trước", "thẻ atm", "phát hành thẻ", "khóa thẻ",
                              "credit card", "debit card", "prepaid card", "cards", "card issuing",
                              "tiết kiệm", "tiền gửi", "deposit", "deposits", "savings")),
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

# Domain pack ngân hàng = lõi chung (prompts/domains/fintech-banking.md) + các module sản phẩm
# (prompts/domains/banking/<module>.md) khớp với nội dung in-scope của yêu cầu.
BANKING_PACK = "fintech-banking"
BANKING_MODULE_KEYWORDS: List[Tuple[str, Tuple[str, ...]]] = [
    ("payments",  ("payment", "payments", "thanh toán", "chuyển tiền", "chuyển khoản", "transfer", "napas", "vietqr",
                   "qr", "citad", "swift", "ví điện tử", "wallet", "hoàn tiền", "refund", "đảo giao dịch",
                   "reversal", "thu hộ", "chi hộ", "biểu phí")),
    ("overdraft", ("thấu chi", "overdraft", "od")),
    ("lending",   ("khoản vay", "cho vay", "vay", "loan", "loans", "lending", "giải ngân", "disbursement",
                   "thu nợ", "trả nợ", "lịch trả nợ", "nhóm nợ", "tín chấp", "thế chấp")),
    ("cards",     ("thẻ", "card", "cards", "pos", "atm", "pin", "3ds", "3-d secure", "chargeback", "mcc", "visa",
                   "mastercard", "jcb", "sao kê")),
    ("deposits",  ("tiết kiệm", "tiền gửi", "deposit", "deposits", "savings", "đáo hạn", "tái tục", "sổ tiết kiệm")),
]


def keyword_regex(keywords: Tuple[str, ...]) -> "re.Pattern[str]":
    """Khớp nguyên từ/cụm từ (không khớp chuỗi con: 'phi' không khớp 'phiếu', 'cod' không khớp 'code')."""
    alternatives = "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


_DOMAIN_PACK_PATTERNS = [(name, keyword_regex(kws)) for name, kws in DOMAIN_PACK_KEYWORDS]
_BANKING_MODULE_PATTERNS = [(name, keyword_regex(kws)) for name, kws in BANKING_MODULE_KEYWORDS]


def resolve_domain_pack(domain: str, feature_name: str = "") -> str:
    """Chọn domain pack theo từ khóa; mặc định 'api-platform' nếu không khớp."""
    haystack = f"{domain} {feature_name}"
    for pack_name, pattern in _DOMAIN_PACK_PATTERNS:
        if pattern.search(haystack):
            return pack_name
    return DEFAULT_DOMAIN_PACK


def resolve_banking_modules(*texts: str) -> List[str]:
    """Các module sản phẩm ngân hàng (payments/overdraft/lending/cards/deposits) được nhắc tới trong nội dung."""
    haystack = " ".join(t for t in texts if t)
    return [name for name, pattern in _BANKING_MODULE_PATTERNS if pattern.search(haystack)]


def load_domain_pack(domain: str, feature_name: str = "", context: str = "") -> str:
    """
    Đọc prompts/domains/<pack>.md. Với pack ngân hàng: ghép thêm prompts/domains/banking/<module>.md
    cho từng module sản phẩm khớp trong domain/feature_name/context (nội dung in-scope của yêu cầu).
    """
    pack_name = resolve_domain_pack(domain, feature_name)
    parts = [load_prompt(f"domains/{pack_name}")]
    if pack_name == BANKING_PACK:
        parts.extend(load_prompt(f"domains/banking/{module}") for module in resolve_banking_modules(domain, feature_name, context))
    return "\n\n---\n\n".join(p for p in parts if p)


def load_composite(base_name: str, *extra_names: str) -> str:
    """Ghép nội dung base_name và các extra_names (vd: rubric dùng chung), bỏ qua phần rỗng."""
    parts = [load_prompt(base_name)]
    for name in extra_names:
        parts.append(load_prompt(name))
    return "\n\n---\n\n".join(p for p in parts if p)
