import json
import re

from inference_lab.config import REPO_ROOT
from inference_lab.i18n import missing_keys, normalize, resources, t


def test_backend_key_parity():
    assert missing_keys() in ({}, {"en": [], "zh-TW": []}) or not any(missing_keys().values())
    en, zh = resources("en"), resources("zh-TW")
    assert set(en) == set(zh)
    for k in en:
        assert sorted(re.findall(r"\{(\w+)\}", en[k])) == sorted(re.findall(r"\{(\w+)\}", zh[k])), k


def test_default_is_english():
    assert normalize(None) == "en" and normalize("fr") == "en" and normalize("zh-TW") == "zh-TW"
    assert normalize("zh-tw") in ("zh-TW", "en")


def test_frontend_locales_parity():
    root = REPO_ROOT / "frontend" / "src" / "locales"
    flat = lambda o, p="": {k2: v2 for k, v in o.items() for k2, v2 in (flat(v, f"{p}{k}.").items() if isinstance(v, dict) else [(f"{p}{k}", v)])}  # noqa: E731
    en = flat(json.loads((root / "en.json").read_text(encoding="utf-8")))
    zh = flat(json.loads((root / "zh-TW.json").read_text(encoding="utf-8")))
    assert set(en) == set(zh) and all(str(v).strip() for v in zh.values())


def test_traditional_not_simplified():
    zh_text = json.dumps(resources("zh-TW"), ensure_ascii=False) + (REPO_ROOT / "frontend/src/locales/zh-TW.json").read_text(encoding="utf-8")
    # Common Simplified-only characters that should never appear in Taiwan Traditional Chinese UI text.
    for ch in "这们为说检请过还时实测试执运务应":
        assert ch not in zh_text, f"Simplified character {ch!r} found"


def test_suggestions_localized():
    assert t("zh-TW", "suggest.queueing_serial.cause") != t("en", "suggest.queueing_serial.cause")
