"""Bridge to the llm-inference-bench project (llmbench) that lives next to this repo.

llmbench's edge track already ships what a Windows-on-ARM laptop needs to run a real model:
llama.cpp builds for the CPU and for the Adreno GPU (OpenCL), and Qwen3-4B GGUF files.
Inference Lab reuses those files as-is instead of downloading its own copies:

  <llmbench>/tools/llama-cpu/llama-server(.exe)      CPU backend
  <llmbench>/tools/llama-adreno/llama-server(.exe)   Adreno GPU backend (OpenCL)
  <llmbench>/models/*.gguf                           model weights

The llmbench folder is found from INFERENCE_LAB_LLMBENCH_DIR, else a sibling folder of this
repo (../llmbench/llm-inference-bench or ../llm-inference-bench), else ~/llmbench/llm-inference-bench.
Nothing in the llmbench folder is modified.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT

BACKENDS = {"cpu": "llama-cpu", "adreno": "llama-adreno"}
GGUF_REF = re.compile(r"^gguf:([A-Za-z0-9._-]{1,120})$")
_EXE = "llama-server.exe" if sys.platform == "win32" else "llama-server"


def _candidates() -> list[Path]:
    env = os.environ.get("INFERENCE_LAB_LLMBENCH_DIR")
    if env:
        return [Path(env).expanduser()]
    parent = REPO_ROOT.parent
    return [parent / "llmbench" / "llm-inference-bench", parent / "llm-inference-bench",
            Path.home() / "llmbench" / "llm-inference-bench"]


def find_root() -> Path | None:
    for c in _candidates():
        if (c / "src" / "llmbench").is_dir() or (c / "tools").is_dir():
            return c.resolve()
    return None


def server_binary(backend: str, root: Path | None = None) -> Path | None:
    if backend not in BACKENDS:
        raise ValueError(f"backend must be one of {sorted(BACKENDS)}")
    root = root or find_root()
    if not root:
        return None
    exe = root / "tools" / BACKENDS[backend] / _EXE
    return exe if exe.is_file() else None


def list_models(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or find_root()
    if not root or not (root / "models").is_dir():
        return []
    return [{"ref": f"gguf:{p.stem}", "file": str(p), "size_bytes": p.stat().st_size}
            for p in sorted((root / "models").glob("*.gguf"))]


def resolve_model(ref: str, root: Path | None = None) -> Path:
    m = GGUF_REF.match(ref)
    if not m:
        raise ValueError("llama.cpp models are referenced as gguf:<file name without .gguf>")
    root = root or find_root()
    if not root:
        raise FileNotFoundError("llmbench folder not found; set INFERENCE_LAB_LLMBENCH_DIR")
    path = (root / "models" / f"{m.group(1)}.gguf").resolve()
    if path.parent != (root / "models").resolve():
        raise ValueError("model path escapes the llmbench models folder")
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    return path


def probe() -> dict[str, Any]:
    root = find_root()
    return {
        "root": str(root) if root else None,
        "llama_server_cpu": str(server_binary("cpu", root) or "") or None,
        "llama_server_adreno": str(server_binary("adreno", root) or "") or None,
        "models": list_models(root),
    }
