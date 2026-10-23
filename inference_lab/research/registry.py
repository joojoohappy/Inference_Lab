"""Research Archive: structured citation records (research/registry.yaml).

Rules: every record has a primary-source URL; nothing is invented. `verification` states how
the record was checked; records that could not be fetched from the build environment say so.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PATH = Path(__file__).resolve().parent / "registry.yaml"
REQUIRED = ("id", "title", "authors", "kind", "url", "concepts", "related_missions", "verification",
            "beginner", "engineering", "contributions", "practical", "limitations")
LOCALIZED = ("beginner", "engineering", "contributions", "practical", "limitations")


@lru_cache(maxsize=1)
def load() -> list[dict[str, Any]]:
    recs = yaml.safe_load(PATH.read_text(encoding="utf-8"))
    for r in recs:
        missing = [k for k in REQUIRED if k not in r]
        if missing:
            raise ValueError(f"{r.get('id')}: missing {missing}")
        for k in LOCALIZED:
            if not (isinstance(r[k], dict) and r[k].get("en") and r[k].get("zh-TW")):
                raise ValueError(f"{r['id']}.{k}: needs en and zh-TW")
        if not str(r["url"]).startswith("https://"):
            raise ValueError(f"{r['id']}: url must be https")
    return recs


def get(rid: str) -> dict[str, Any] | None:
    return next((r for r in load() if r["id"] == rid), None)
