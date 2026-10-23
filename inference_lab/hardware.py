"""Hardware discovery: CPU, RAM, GPU/VRAM, driver, Docker.

Every probe records the exact command it ran (or the Python call it made) and the raw
output, so the UI can show "what was executed" next to "what was found".
Probes never raise: a missing tool becomes a probe with status "not_found".
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import psutil

# The only external commands hardware discovery may run. No shell, fixed arguments.
NVIDIA_SMI_QUERY = [
    "nvidia-smi",
    "--query-gpu=index,name,memory.total,memory.used,driver_version,utilization.gpu",
    "--format=csv,noheader,nounits",
]
DOCKER_VERSION = ["docker", "version", "--format", "{{.Client.Version}}|{{.Server.Version}}"]


@dataclass
class Probe:
    name: str
    status: str  # "ok" | "not_found" | "error"
    command: str  # human-readable command or Python call that produced the data
    raw: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


def _run(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
    """Run an allowlisted command without a shell. Returns (returncode, combined output)."""
    if shutil.which(cmd[0]) is None:
        return 127, f"{cmd[0]}: command not found"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]}: timed out after {timeout}s"
    except OSError as e:  # pragma: no cover - platform specific
        return 126, str(e)


def probe_cpu() -> Probe:
    t = time.perf_counter()
    model = platform.processor() or ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    data = {
        "model": model or "unknown",
        "architecture": platform.machine(),
        "logical_cores": os.cpu_count() or 0,
        "physical_cores": psutil.cpu_count(logical=False) or 0,
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }
    return Probe("cpu", "ok", "python: os.cpu_count(), psutil.cpu_count(logical=False), /proc/cpuinfo",
                 raw=str(data), data=data, duration_ms=(time.perf_counter() - t) * 1000)


def probe_memory() -> Probe:
    t = time.perf_counter()
    vm = psutil.virtual_memory()
    data = {"total_gb": round(vm.total / 1024**3, 2), "available_gb": round(vm.available / 1024**3, 2)}
    return Probe("memory", "ok", "python: psutil.virtual_memory()", raw=str(vm), data=data,
                 duration_ms=(time.perf_counter() - t) * 1000)


def parse_nvidia_smi(output: str) -> list[dict[str, Any]]:
    """Parse `nvidia-smi --query-gpu=... --format=csv,noheader,nounits` output."""
    gpus = []
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            gpus.append({
                "index": int(parts[0]),
                "name": parts[1],
                "vram_total_mb": int(float(parts[2])),
                "vram_used_mb": int(float(parts[3])),
                "driver_version": parts[4],
                "utilization_pct": int(float(parts[5])) if parts[5] not in ("[N/A]", "N/A") else None,
            })
        except ValueError:
            continue
    return gpus


def probe_gpu() -> Probe:
    t = time.perf_counter()
    cmd = " ".join(NVIDIA_SMI_QUERY)
    rc, out = _run(NVIDIA_SMI_QUERY)
    dur = (time.perf_counter() - t) * 1000
    if rc == 127:
        return Probe("gpu", "not_found", cmd, raw=out, data={"gpus": [], "reason": "nvidia-smi not installed"},
                     duration_ms=dur)
    if rc != 0:
        return Probe("gpu", "error", cmd, raw=out, data={"gpus": [], "reason": f"exit code {rc}"}, duration_ms=dur)
    gpus = parse_nvidia_smi(out)
    return Probe("gpu", "ok" if gpus else "not_found", cmd, raw=out, data={"gpus": gpus}, duration_ms=dur)


def probe_docker() -> Probe:
    t = time.perf_counter()
    rc, out = _run(DOCKER_VERSION)
    dur = (time.perf_counter() - t) * 1000
    cmd = " ".join(DOCKER_VERSION)
    if rc == 127:
        return Probe("docker", "not_found", cmd, raw=out, data={"client": None, "daemon_running": False},
                     duration_ms=dur)
    client, _, server = out.partition("|")
    # Without a daemon, `docker version` prints the client version and an error, exit code 1.
    client_version = client.strip().splitlines()[0] if client.strip() else None
    daemon = rc == 0 and bool(server.strip())
    data = {"client": client_version, "server": server.strip() if daemon else None, "daemon_running": daemon}
    return Probe("docker", "ok" if daemon else "error", cmd, raw=out, data=data, duration_ms=dur)


def probe_python_ml() -> Probe:
    """Which inference libraries are importable, and does torch see CUDA?"""
    t = time.perf_counter()
    data: dict[str, Any] = {}
    for mod in ("torch", "transformers", "tokenizers", "vllm"):
        try:
            m = __import__(mod)
            data[mod] = getattr(m, "__version__", "installed")
        except Exception:  # noqa: BLE001 - any import failure means "not available"
            data[mod] = None
    if data.get("torch"):
        import torch

        data["torch_cuda_available"] = bool(torch.cuda.is_available())
        data["torch_cuda_version"] = torch.version.cuda
    return Probe("python_ml", "ok", "python: import torch, transformers, tokenizers, vllm; torch.cuda.is_available()",
                 raw=str(data), data=data, duration_ms=(time.perf_counter() - t) * 1000)


def probe_hub() -> Probe:
    """Can this machine reach the Hugging Face Hub API? (one small documented GET)"""
    import httpx

    from .config import load_settings

    url = f"{load_settings().hf_endpoint}/api/models?limit=1"
    t = time.perf_counter()
    try:
        r = httpx.get(url, timeout=4.0)
        ok = r.status_code == 200
        return Probe("hub", "ok" if ok else "error", f"GET {url}", raw=f"HTTP {r.status_code}",
                     data={"reachable": ok, "http_status": r.status_code}, duration_ms=(time.perf_counter() - t) * 1000)
    except httpx.HTTPError as e:
        return Probe("hub", "error", f"GET {url}", raw=f"{type(e).__name__}: {e}"[:500],
                     data={"reachable": False, "error": type(e).__name__}, duration_ms=(time.perf_counter() - t) * 1000)


def capabilities(probes: dict[str, Probe]) -> dict[str, bool]:
    """Derive what this machine can do from probe results. Deterministic."""
    gpus = probes["gpu"].data.get("gpus", [])
    ml = probes["python_ml"].data
    docker = probes["docker"].data
    return {
        "cpu_inference": bool(ml.get("torch") and ml.get("transformers")),
        "nvidia_gpu": bool(gpus),
        "cuda_torch": bool(ml.get("torch_cuda_available")),
        "docker": bool(docker.get("daemon_running")),
        "vllm_docker": bool(gpus) and bool(docker.get("daemon_running")),
        "vllm_python": bool(ml.get("vllm")),
        "hub_access": bool(probes["hub"].data.get("reachable")) if "hub" in probes else False,
    }


def scan() -> dict[str, Any]:
    probes = {p.name: p for p in (probe_cpu(), probe_memory(), probe_gpu(), probe_docker(),
                                         probe_python_ml(), probe_hub())}
    return {
        "probes": {k: asdict(v) for k, v in probes.items()},
        "capabilities": capabilities(probes),
        "summary": {
            "cpu_model": probes["cpu"].data["model"],
            "logical_cores": probes["cpu"].data["logical_cores"],
            "ram_total_gb": probes["memory"].data["total_gb"],
            "gpu_count": len(probes["gpu"].data.get("gpus", [])),
            "vram_total_gb": round(sum(g["vram_total_mb"] for g in probes["gpu"].data.get("gpus", [])) / 1024, 2),
        },
    }


def hardware_fingerprint(scan_result: dict[str, Any]) -> dict[str, Any]:
    """The subset of a scan that matters for comparing experiments."""
    s = scan_result["summary"]
    gpus = scan_result["probes"]["gpu"]["data"].get("gpus", [])
    return {
        "cpu_model": s["cpu_model"],
        "logical_cores": s["logical_cores"],
        "ram_total_gb": s["ram_total_gb"],
        "gpus": [g["name"] for g in gpus],
        "driver": gpus[0]["driver_version"] if gpus else None,
    }
