"""Remove secrets before any text can reach an AI provider."""

from __future__ import annotations

import os
import re

_PATTERNS = [
    re.compile(r"hf_[A-Za-z0-9]{20,}"),                    # Hugging Face tokens
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),                 # sk- style API keys (Anthropic, OpenAI, ...)
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    re.compile(r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)\S+"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


def redact(text: str) -> str:
    out = text
    for name in ("HF_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HUGGING_FACE_HUB_TOKEN"):
        v = os.environ.get(name)
        if v and len(v) >= 8:
            out = out.replace(v, "[REDACTED]")
    for p in _PATTERNS:
        out = p.sub(lambda m: (m.group(1) if m.groups() and m.group(1) else "") + "[REDACTED]", out)
    return out
