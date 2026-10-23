"""Backend localization (reports, diagnostics, error explanations).

Resources live in inference_lab/locales/<lang>.json as flat "dotted.key": "text {placeholder}".
English is the default and the fallback. Code, flags, model ids and paths are never translated.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SUPPORTED = ("en", "zh-TW")
DEFAULT = "en"
_DIR = Path(__file__).resolve().parent / "locales"


@lru_cache(maxsize=None)
def resources(lang: str) -> dict[str, str]:
    return json.loads((_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def normalize(lang: str | None) -> str:
    return lang if lang in SUPPORTED else DEFAULT


def t(lang: str | None, key: str, **kw: Any) -> str:
    lang = normalize(lang)
    text = resources(lang).get(key) or resources(DEFAULT).get(key) or key
    try:
        return text.format(**kw)
    except (KeyError, IndexError):
        return text


def missing_keys() -> dict[str, list[str]]:
    base = set(resources(DEFAULT))
    return {lang: sorted(base - set(resources(lang))) for lang in SUPPORTED if lang != DEFAULT}
