"""Memory estimates for running a model. These are heuristics, not measurements.

Every estimate returns the assumptions it used so the UI can show them.
"""

from __future__ import annotations

from typing import Any

BYTES_PER_PARAM = {"float32": 4, "fp32": 4, "F32": 4, "bfloat16": 2, "bf16": 2, "BF16": 2, "float16": 2,
                   "fp16": 2, "F16": 2, "int8": 1, "I8": 1, "int4": 0.5, "U8": 1}

# Runtime overhead on top of raw weights (CUDA context, allocator fragmentation, activations).
# Engineering heuristic, not an established constant. Real usage must be measured.
RUNTIME_OVERHEAD_FRACTION = 0.20
RUNTIME_OVERHEAD_FIXED_GB = 0.5


def weights_gb(params: int, dtype: str = "bfloat16") -> float:
    return params * BYTES_PER_PARAM.get(dtype, 2) / 1024**3


def kv_cache_bytes_per_token(config: dict[str, Any], dtype: str = "bfloat16") -> int | None:
    """2 (K and V) x layers x kv_heads x head_dim x bytes. Returns None if the config lacks fields."""
    layers = config.get("num_hidden_layers") or config.get("n_layer")
    heads = config.get("num_attention_heads") or config.get("n_head")
    hidden = config.get("hidden_size") or config.get("n_embd")
    if not (layers and heads and hidden):
        return None
    kv_heads = config.get("num_key_value_heads") or heads
    head_dim = config.get("head_dim") or hidden // heads
    return int(2 * layers * kv_heads * head_dim * BYTES_PER_PARAM.get(dtype, 2))


def estimate(params: int | None, config: dict[str, Any] | None, dtype: str = "bfloat16",
             context_tokens: int = 2048, batch: int = 1) -> dict[str, Any]:
    assumptions = [
        f"weights stored as {dtype} ({BYTES_PER_PARAM.get(dtype, 2)} bytes per parameter)",
        f"KV cache sized for batch={batch} x {context_tokens} tokens",
        f"runtime overhead heuristic: +{int(RUNTIME_OVERHEAD_FRACTION * 100)}% of weights + "
        f"{RUNTIME_OVERHEAD_FIXED_GB} GB",
        "activations for long prompts and framework-specific pre-allocation are not modelled",
    ]
    if not params:
        return {"known": False, "assumptions": assumptions, "reason": "parameter count unavailable"}
    w = weights_gb(params, dtype)
    kv_tok = kv_cache_bytes_per_token(config or {}, dtype)
    kv = (kv_tok * context_tokens * batch / 1024**3) if kv_tok else None
    total = w * (1 + RUNTIME_OVERHEAD_FRACTION) + RUNTIME_OVERHEAD_FIXED_GB + (kv or 0)
    return {
        "known": True,
        "kind": "ESTIMATE",
        "params": params,
        "dtype": dtype,
        "weights_gb": round(w, 3),
        "kv_cache_bytes_per_token": kv_tok,
        "kv_cache_gb": round(kv, 3) if kv is not None else None,
        "total_gb": round(total, 3),
        "assumptions": assumptions,
    }


def assess_compatibility(est: dict[str, Any], hw_summary: dict[str, Any], capabilities: dict[str, bool]) -> dict[str, Any]:
    """Deterministic verdict: can this machine plausibly run the model, and how?"""
    reasons: list[str] = []
    if not est.get("known"):
        return {"verdict": "unknown", "reasons": ["memory estimate unavailable"], "paths": []}
    need = est["total_gb"]
    paths = []
    vram = hw_summary.get("vram_total_gb") or 0
    ram = hw_summary.get("ram_total_gb") or 0
    if capabilities.get("nvidia_gpu"):
        if need <= vram * 0.9:
            paths.append("gpu_transformers")
            if capabilities.get("vllm_docker") or capabilities.get("vllm_python"):
                paths.append("gpu_vllm")
            reasons.append(f"estimated {need:.2f} GB fits in {vram:.1f} GB VRAM with 10% headroom")
        else:
            reasons.append(f"estimated {need:.2f} GB exceeds 90% of {vram:.1f} GB VRAM")
    else:
        reasons.append("no NVIDIA GPU detected; vLLM GPU serving is not available")
    if capabilities.get("cpu_inference") and need <= ram * 0.6:
        paths.append("cpu_transformers")
        reasons.append(f"estimated {need:.2f} GB fits in 60% of {ram:.1f} GB RAM for CPU inference (slow for large models)")
    elif not capabilities.get("cpu_inference"):
        reasons.append("torch/transformers not installed; CPU inference unavailable")
    else:
        reasons.append(f"estimated {need:.2f} GB is too large for comfortable CPU inference in {ram:.1f} GB RAM")
    verdict = "fits_gpu" if any(p.startswith("gpu") for p in paths) else ("cpu_only" if paths else "too_large")
    return {"verdict": verdict, "reasons": reasons, "paths": paths}
