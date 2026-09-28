"""Conservative display cleanup; source records remain unchanged."""
VERSION = "2026-09-28-2"
NAVIGATION_MARKERS = (
    "accept additional cookies", "reject additional cookies", "skip to main content",
    "navigation menu", "访问我的专属空间", "抱歉，没听清", "cloudflare ray id",
    "enable javascript and cookies",
    "services and information benefits births", "get emails about this page",
    "is this page useful?", "sign up for emails or print this page",
)
COUNTRIES = {"China": "中国", "China (People’s Republic of)": "中国", "United States": "美国", "United Kingdom": "英国", "Canada": "加拿大"}
LANGUAGES = {"eng": "en", "zho": "zh", "chi": "zh", "fra": "fr", "fre": "fr",
             "deu": "de", "ger": "de", "spa": "es", "ita": "it", "por": "pt",
             "jpn": "ja", "kor": "ko", "nld": "nl", "dut": "nl", "rus": "ru"}
LANGUAGES.update(dict(zip(
    ('ell','dan','pol','ces','est','fin','hun','bul','hrv','lav','lit','mlt','ron','slk','slv','swe','gle'),
    ('el','da','pl','cs','et','fi','hu','bg','hr','lv','lt','mt','ro','sk','sl','sv','ga'),
)))


def clean_summary(text: str, extraction_status: str = "extracted") -> tuple[str, str]:
    if extraction_status in {"non_body", "mixed_source", "ocr_required", "manual_review"}:
        return "", "withheld_body_status"
    if any(marker in text.lower() for marker in NAVIGATION_MARKERS):
        return "", "navigation_review"
    return text, "available" if text.strip() else "missing"


def country(value: str) -> str:
    return COUNTRIES.get(value, value)


def language(value: str) -> str:
    return LANGUAGES.get(value.lower(), value.lower())
