"""Hugging Face Hub model inspection through the public HTTP API.

Endpoint: GET {HF_ENDPOINT}/api/models/{repo_id}?blobs=true. This is the request the official
`huggingface_hub` client makes in HfApi.model_info(files_metadata=True) (hf_api.py). Endpoint
reference: https://huggingface.co/spaces/huggingface/openapi (moved from huggingface.co/docs/hub/api).
Nothing here executes remote code. A model that needs `trust_remote_code` is flagged, not loaded.
"""

from __future__ import annotations

import fnmatch
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import load_settings

# Hub repo ids: optional "namespace/" + name. Letters, digits, '-', '_', '.'; no '--' or '..'.
_PART = r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,94}[A-Za-z0-9])?"
MODEL_ID_RE = re.compile(rf"^(?:{_PART}/)?{_PART}$")
ALLOWED_HOSTS = {"huggingface.co", "www.huggingface.co", "hf.co"}

SAFE_WEIGHT_SUFFIXES = (".safetensors",)
DOWNLOAD_PATTERNS = ["*.safetensors", "*.json", "tokenizer.model", "*.txt", "*.jinja"]
PICKLE_WEIGHT_SUFFIXES = (".bin", ".pt", ".pth", ".ckpt", ".pkl")


class InvalidModelId(ValueError):
    pass


class HubUnavailable(RuntimeError):
    """The Hub could not be reached (offline, proxy, DNS). Not the model's fault."""


def normalize_model_ref(ref: str) -> str:
    """Accept a model id or a huggingface.co model URL; return a validated model id."""
    ref = (ref or "").strip()
    if not ref or len(ref) > 200:
        raise InvalidModelId("empty or too long")
    if "://" in ref:
        u = urlparse(ref)
        if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS or u.username or u.port:
            raise InvalidModelId("only https://huggingface.co/<org>/<model> URLs are accepted")
        parts = [p for p in u.path.split("/") if p]
        if not parts or parts[0] in {"datasets", "spaces", "api", "docs"}:
            raise InvalidModelId("URL is not a model page")
        ref = "/".join(parts[:2]) if len(parts) >= 2 and parts[1] not in {"tree", "blob", "resolve"} else parts[0]
    if ".." in ref or "--" in ref or not MODEL_ID_RE.match(ref):
        raise InvalidModelId(f"not a valid Hugging Face model id: {ref!r}")
    return ref


def _headers() -> dict[str, str]:
    # The token is read from the environment only for Hub requests. It is never logged,
    # stored in experiment records, or passed to the AI tutor.
    tok = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _get_json(client: httpx.Client, url: str) -> tuple[int, Any]:
    try:
        r = client.get(url, headers=_headers(), follow_redirects=True)
    except httpx.HTTPError as e:
        raise HubUnavailable(f"{type(e).__name__}: {e}") from e
    if r.status_code == 200:
        try:
            return 200, r.json()
        except ValueError:
            return 200, None
    return r.status_code, None


def summarize(info: dict[str, Any], config: dict[str, Any] | None, tok_cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Pure function: turn raw Hub responses into the fields the Model Garage shows."""
    siblings = info.get("siblings") or []
    files = [s.get("rfilename", "") for s in siblings]
    sizes = [s.get("size") for s in siblings if isinstance(s.get("size"), int)]
    weight_files = [f for f in files if f.endswith(SAFE_WEIGHT_SUFFIXES + PICKLE_WEIGHT_SUFFIXES + (".gguf",))]
    formats = sorted({f.rsplit(".", 1)[-1] for f in weight_files})
    safetensors = info.get("safetensors") or {}
    card = info.get("cardData") or {}
    tags = info.get("tags") or []
    cfg = config or info.get("config") or {}
    needs_remote_code = bool(cfg.get("auto_map")) or "custom_code" in tags
    license_ = card.get("license") or next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None)
    param_dtypes = safetensors.get("parameters") or {}
    dominant_dtype = max(param_dtypes, key=param_dtypes.get) if param_dtypes else None
    return {
        "id": info.get("id") or info.get("modelId"),
        "revision": info.get("sha"),
        "task": info.get("pipeline_tag"),
        "library": info.get("library_name"),
        "architectures": cfg.get("architectures"),
        "model_type": cfg.get("model_type"),
        "parameters": safetensors.get("total"),
        "parameter_dtypes": param_dtypes or None,
        "dominant_dtype": dominant_dtype,
        "license": license_,
        "gated": info.get("gated") or False,
        "private": bool(info.get("private")),
        "weight_formats": formats,
        "has_safetensors": any(f.endswith(".safetensors") for f in files),
        "pickle_only": bool(weight_files) and not any(f.endswith((".safetensors", ".gguf")) for f in weight_files),
        "repo_size_bytes": sum(sizes) if sizes else info.get("usedStorage"),
        "file_count": len(files),
        "download_bytes": sum(s["size"] for s in siblings if isinstance(s.get("size"), int)
                              and any(fnmatch.fnmatch(s.get("rfilename", ""), p) for p in DOWNLOAD_PATTERNS)) or None,
        "has_tokenizer": any(f in files for f in ("tokenizer.json", "tokenizer.model", "vocab.json")),
        "has_chat_template": bool(tok_cfg and tok_cfg.get("chat_template")) or "chat_template.jinja" in files,
        "needs_remote_code": needs_remote_code,
        "tags": tags[:30],
        "downloads": info.get("downloads"),
        "likes": info.get("likes"),
        "config": {k: cfg.get(k) for k in ("num_hidden_layers", "n_layer", "num_attention_heads", "n_head",
                                            "num_key_value_heads", "hidden_size", "n_embd", "head_dim",
                                            "max_position_embeddings", "n_positions", "vocab_size",
                                            "torch_dtype") if cfg.get(k) is not None},
        "framework_support": {
            "transformers": info.get("library_name") == "transformers" or "transformers" in tags,
            # vLLM support depends on the architecture; we report the architecture and link the docs
            # instead of guessing a list that goes stale.
            "vllm_check": "https://docs.vllm.ai/en/latest/models/supported_models.html",
        },
    }


def inspect_model(ref: str, timeout: float = 15.0) -> dict[str, Any]:
    model_id = normalize_model_ref(ref)
    base = load_settings().hf_endpoint
    calls = []
    with httpx.Client(timeout=timeout) as client:
        url = f"{base}/api/models/{model_id}?blobs=true"
        calls.append(f"GET {url}")
        status, info = _get_json(client, url)
        if status == 404 or status == 401:
            return {"ok": False, "model_id": model_id, "error": "not_found_or_private", "http_status": status,
                    "calls": calls}
        if status != 200 or not isinstance(info, dict):
            return {"ok": False, "model_id": model_id, "error": "hub_error", "http_status": status, "calls": calls}
        rev = info.get("sha") or "main"
        config = tok_cfg = None
        for name in ("config.json", "tokenizer_config.json"):
            u = f"{base}/{model_id}/resolve/{rev}/{name}"
            calls.append(f"GET {u}")
            st, js = _get_json(client, u)
            if st == 200 and isinstance(js, dict):
                if name == "config.json":
                    config = js
                else:
                    tok_cfg = js
    return {"ok": True, "model_id": model_id, "source": "huggingface_hub_api", "calls": calls,
            "summary": summarize(info, config, tok_cfg)}


def download_plan(summary: dict[str, Any]) -> dict[str, Any]:
    """What a download would fetch. Safetensors only; pickle weights are refused."""
    if summary.get("needs_remote_code"):
        return {"allowed": False, "reason": "requires_remote_code"}
    if summary.get("gated"):
        return {"allowed": False, "reason": "gated_model_requires_accepting_terms_on_hub"}
    if summary.get("pickle_only"):
        return {"allowed": False, "reason": "pickle_weights_only"}
    if not summary.get("has_safetensors"):
        return {"allowed": False, "reason": "no_safetensors_weights"}
    return {
        "allowed": True,
        "allow_patterns": DOWNLOAD_PATTERNS,
        "estimated_bytes": summary.get("download_bytes"),
    }
