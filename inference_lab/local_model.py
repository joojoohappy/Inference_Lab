"""Inspect a model that is already on disk, without loading it and without torch.

Parameter counts come from the safetensors headers (8-byte little-endian header length, then a
JSON table of tensor names, dtypes and shapes). This is the same information the Hub shows,
read directly from the files.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

from .inference import model_dir_for

MAX_HEADER = 100 * 1024 * 1024


def read_safetensors_header(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        if n > MAX_HEADER:
            raise ValueError("safetensors header too large")
        return json.loads(f.read(n))


def count_parameters(model_dir: Path) -> tuple[int, dict[str, int]]:
    total, by_dtype = 0, {}
    for p in sorted(model_dir.glob("*.safetensors")):
        for name, meta in read_safetensors_header(p).items():
            if name == "__metadata__":
                continue
            n = math.prod(meta["shape"]) if meta["shape"] else 1
            total += n
            by_dtype[meta["dtype"]] = by_dtype.get(meta["dtype"], 0) + n
    return total, by_dtype


def inspect_local(ref: str) -> dict[str, Any]:
    d = model_dir_for(ref)
    cfg_path = d / "config.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"{ref} is not on disk at {d}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    tok_cfg_path = d / "tokenizer_config.json"
    tok_cfg = json.loads(tok_cfg_path.read_text(encoding="utf-8")) if tok_cfg_path.exists() else {}
    vocab = None
    if (d / "tokenizer.json").exists():
        vocab = len(json.loads((d / "tokenizer.json").read_text(encoding="utf-8")).get("model", {}).get("vocab", {}))
    params, by_dtype = count_parameters(d)
    files = sorted(p.name for p in d.iterdir() if p.is_file())
    size = sum((d / f).stat().st_size for f in files)
    return {
        "id": ref,
        "source": "local_files",
        "path": str(d),
        "architectures": cfg.get("architectures"),
        "model_type": cfg.get("model_type"),
        "parameters": params,
        "parameter_dtypes": by_dtype,
        "dominant_dtype": max(by_dtype, key=by_dtype.get) if by_dtype else None,
        "weight_formats": sorted({f.rsplit(".", 1)[-1] for f in files if f.endswith((".safetensors", ".bin", ".gguf"))}),
        "has_safetensors": any(f.endswith(".safetensors") for f in files),
        "has_tokenizer": vocab is not None or (d / "tokenizer.model").exists(),
        "tokenizer_vocab_size": vocab,
        "has_chat_template": bool(tok_cfg.get("chat_template")) or (d / "chat_template.jinja").exists(),
        "needs_remote_code": bool(cfg.get("auto_map")),
        "repo_size_bytes": size,
        "files": files,
        "config": {k: cfg.get(k) for k in ("num_hidden_layers", "n_layer", "num_attention_heads", "n_head",
                                            "num_key_value_heads", "hidden_size", "n_embd", "n_positions",
                                            "max_position_embeddings", "vocab_size", "torch_dtype", "dtype")
                   if cfg.get(k) is not None},
        "license": None,
        "model_card": (d / "LAB_MODEL_CARD.md").read_text(encoding="utf-8") if (d / "LAB_MODEL_CARD.md").exists()
        else ((d / "README.md").read_text(encoding="utf-8")[:4000] if (d / "README.md").exists() else None),
    }


def list_local_models() -> list[str]:
    from .config import load_settings

    out = []
    for d in sorted(load_settings().ensure().models_dir.iterdir()):
        if (d / "config.json").exists():
            out.append("lab/tiny-random" if d.name == "lab__tiny-random" else d.name.replace("__", "/", 1))
    return out
