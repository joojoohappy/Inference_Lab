"""Start, check, and stop model servers. Only three fixed launch recipes exist:

  * mini:     python -m inference_lab.serving.mini_server   (CPU or GPU, Transformers)
  * vllm:     docker run ... vllm/vllm-openai               (NVIDIA GPU + Docker required)
  * llamacpp: llmbench's llama-server, CPU or Adreno GPU    (GGUF files from llmbench)

Arguments are validated and passed as an argv list (never through a shell).
Servers bind to 127.0.0.1 only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ..config import REPO_ROOT, load_settings
from ..hub import normalize_model_ref
from ..integrations import llmbench
from ..inference import TINY_MODEL_REF

VLLM_IMAGE = os.environ.get("INFERENCE_LAB_VLLM_IMAGE", "vllm/vllm-openai:latest")
PORT_RANGE = range(1024, 65536)


@dataclass
class ServerInfo:
    kind: str
    model: str
    port: int
    argv: list[str]
    pid: int | None = None
    log_path: str = ""
    started_at: float = field(default_factory=time.time)
    container: str | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _validate(model: str, port: int) -> str:
    if port not in PORT_RANGE:
        raise ValueError("port must be between 1024 and 65535")
    return model if model == TINY_MODEL_REF else normalize_model_ref(model)


def mini_argv(model: str, port: int) -> list[str]:
    model = _validate(model, port)
    return [sys.executable, "-m", "inference_lab.serving.mini_server", "--model", model,
            "--host", "127.0.0.1", "--port", str(port)]


def vllm_argv(model: str, port: int, max_model_len: int = 2048, gpu_memory_utilization: float = 0.85,
              container: str = "inference-lab-vllm") -> list[str]:
    model = _validate(model, port)
    if not (256 <= max_model_len <= 131072):
        raise ValueError("max_model_len out of range")
    if not (0.1 <= gpu_memory_utilization <= 0.95):
        raise ValueError("gpu_memory_utilization must be within 0.1..0.95")
    hf_cache = str(Path.home() / ".cache" / "huggingface")
    return ["docker", "run", "--rm", "-d", "--name", container, "--gpus", "all", "--ipc=host",
            "-p", f"127.0.0.1:{port}:8000", "-v", f"{hf_cache}:/root/.cache/huggingface",
            "-e", "HF_TOKEN", VLLM_IMAGE, "--model", model, "--max-model-len", str(max_model_len),
            "--gpu-memory-utilization", str(gpu_memory_utilization)]


def llamacpp_argv(model: str, port: int, backend: str = "cpu", ctx_size: int = 4096, slots: int = 4) -> list[str]:
    """Same flags as llmbench's edge experiments (configs/experiments/edge_*.toml)."""
    if port not in PORT_RANGE:
        raise ValueError("port must be between 1024 and 65535")
    if not (512 <= ctx_size <= 131072) or not (1 <= slots <= 64):
        raise ValueError("ctx_size or slots out of range")
    exe = llmbench.server_binary(backend)
    if exe is None:
        raise FileNotFoundError(f"llama-server for backend '{backend}' not found in the llmbench tools folder")
    path = llmbench.resolve_model(model)
    return [str(exe), "-m", str(path), "--host", "127.0.0.1", "--port", str(port), "--alias", model,
            "-c", str(ctx_size), "-np", str(slots), "--metrics", "--jinja",
            "-ngl", "99" if backend == "adreno" else "0"]


class ServerManager:
    def __init__(self) -> None:
        self.current: ServerInfo | None = None
        self._proc: subprocess.Popen | None = None

    def start_mini(self, model: str = TINY_MODEL_REF, port: int = 8800) -> ServerInfo:
        self.stop()
        argv = mini_argv(model, port)
        log_path = load_settings().ensure().runs_dir / f"mini-server-{port}.log"
        logf = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 - handle owned by the child
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
        self._proc = subprocess.Popen(argv, stdout=logf, stderr=subprocess.STDOUT, cwd=REPO_ROOT, env=env)
        self.current = ServerInfo("mini", model, port, argv, pid=self._proc.pid, log_path=str(log_path))
        return self.current

    def start_llamacpp(self, model: str, port: int = 8080, backend: str = "cpu", **kw: Any) -> ServerInfo:
        self.stop()
        argv = llamacpp_argv(model, port, backend, **kw)
        log_path = load_settings().ensure().runs_dir / f"llamacpp-{backend}-{port}.log"
        logf = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 - handle owned by the child
        self._proc = subprocess.Popen(argv, stdout=logf, stderr=subprocess.STDOUT, cwd=Path(argv[0]).parent)
        self.current = ServerInfo(f"llamacpp-{backend}", model, port, argv, pid=self._proc.pid, log_path=str(log_path))
        return self.current

    def start_vllm(self, model: str, port: int = 8000, **kw: Any) -> ServerInfo:
        self.stop()
        argv = vllm_argv(model, port, **kw)
        if shutil.which("docker") is None:
            raise RuntimeError("docker not installed")
        p = subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip() or p.stdout.strip())
        self.current = ServerInfo("vllm", model, port, argv, container="inference-lab-vllm")
        return self.current

    def process_alive(self) -> bool | None:
        if self._proc is not None:
            return self._proc.poll() is None
        return None

    def health(self, timeout: float = 2.0) -> dict[str, Any]:
        if not self.current:
            return {"running": False}
        out: dict[str, Any] = {"running": True, "server": asdict(self.current), "process_alive": self.process_alive()}
        try:
            r = httpx.get(self.current.base_url + "/health", timeout=timeout)
            out["http_status"] = r.status_code
            out["healthy"] = r.status_code == 200
        except httpx.HTTPError as e:
            out["healthy"] = False
            out["error"] = type(e).__name__
        if self.current.log_path and Path(self.current.log_path).exists():
            out["log_tail"] = Path(self.current.log_path).read_text(encoding="utf-8", errors="replace")[-2000:]
        return out

    def wait_healthy(self, timeout_s: float = 120.0, on_tick=None) -> bool:  # noqa: ANN001
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            h = self.health()
            if on_tick:
                on_tick(h)
            if h.get("healthy"):
                return True
            if h.get("process_alive") is False:
                return False
            time.sleep(0.5)
        return False

    def version(self) -> dict[str, Any] | None:
        if not self.current:
            return None
        try:
            if self.current.kind.startswith("llamacpp"):
                r = httpx.get(self.current.base_url + "/props", timeout=2.0)
                if r.status_code != 200:
                    return None
                props = r.json()
                return {"version": props.get("build_info"), "engine": "llama.cpp",
                        "model_path": props.get("model_path"),
                        "n_ctx": (props.get("default_generation_settings") or {}).get("n_ctx"),
                        "total_slots": props.get("total_slots")}
            r = httpx.get(self.current.base_url + "/version", timeout=2.0)
            return r.json() if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self.current and self.current.kind == "vllm" and self.current.container:
            subprocess.run(["docker", "stop", self.current.container], capture_output=True, timeout=60, check=False)
        self._proc = None
        self.current = None
