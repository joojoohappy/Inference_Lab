"""Optional AI providers for the tutor. The app works fully without any of them.

Configure one with environment variables (never in files, never in the UI):

  INFERENCE_LAB_TUTOR=anthropic   uses the official `anthropic` SDK (pip install anthropic)
                                  credentials resolved by the SDK (ANTHROPIC_API_KEY, or an
                                  `ant auth login` profile); model INFERENCE_LAB_TUTOR_MODEL
                                  (default claude-opus-5-5)
  INFERENCE_LAB_TUTOR=local       an OpenAI-compatible chat endpoint you run yourself, e.g. the
                                  vLLM server from Mission 04: INFERENCE_LAB_TUTOR_URL
                                  (default http://127.0.0.1:8000) and INFERENCE_LAB_TUTOR_MODEL

The provider only ever receives text the tutor built (redacted), never tools or a shell.
"""

from __future__ import annotations

import os
from typing import Protocol

import httpx

from .redact import redact


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic  # optional dependency

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("INFERENCE_LAB_TUTOR_MODEL", "claude-opus-5-5")

    def complete(self, system: str, user: str) -> str:
        kwargs = {}
        if self.model in ("claude-opus-5-5", "claude-fable-5-1", "claude-opus-5", "claude-sonnet-5-5"):
            # On a policy decline the API re-runs the request on a fallback model.
            kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            output_config={"effort": "low"},  # short explanations; raise if quality needs it
            system=system,
            messages=[{"role": "user", "content": redact(user)}],
            **kwargs,
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("the AI provider declined this request")
        return "".join(b.text for b in resp.content if b.type == "text").strip()


class LocalOpenAICompatibleProvider:
    """A model the user serves locally. Not a Claude integration."""

    name = "local"

    def __init__(self) -> None:
        self.url = os.environ.get("INFERENCE_LAB_TUTOR_URL", "http://127.0.0.1:8000").rstrip("/")
        if not self.url.startswith(("http://127.0.0.1", "http://localhost")):
            raise ValueError("local tutor provider must be on localhost")
        self.model = os.environ.get("INFERENCE_LAB_TUTOR_MODEL", "")

    def complete(self, system: str, user: str) -> str:
        r = httpx.post(f"{self.url}/v1/chat/completions", timeout=120, json={
            "model": self.model, "max_tokens": 800,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": redact(user)}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


def configured_provider() -> Provider | None:
    kind = os.environ.get("INFERENCE_LAB_TUTOR", "").strip().lower()
    try:
        if kind == "anthropic":
            return AnthropicProvider()
        if kind == "local":
            return LocalOpenAICompatibleProvider()
    except Exception:  # noqa: BLE001 - a broken provider must not break the app
        return None
    return None
