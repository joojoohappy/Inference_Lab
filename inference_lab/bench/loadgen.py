"""Closed-loop load generator for OpenAI-compatible /v1/completions endpoints (vLLM, SGLang,
or the Inference Lab mini server).

Methodology (see docs/EXPERIMENT_WORKFLOW.md):
  1. warm-up requests are sent and discarded (first requests pay one-time costs);
  2. each trial runs `concurrency` workers that each send the next request as soon as the
     previous one finishes, until `num_requests` complete;
  3. every request is streamed so TTFT is observed on the wire;
  4. trials repeat so run-to-run spread is visible;
  5. resource usage (server RSS/CPU, GPU memory) is sampled during trials.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import httpx
import psutil

from ..hardware import NVIDIA_SMI_QUERY, _run, parse_nvidia_smi
from .metrics import RequestSample, aggregate_trials, summarize

DEFAULT_PROMPT = "Explain what a KV cache does during text generation."


@dataclass
class BenchConfig:
    base_url: str
    model: str
    prompt: str = DEFAULT_PROMPT
    max_tokens: int = 32
    concurrency: int = 1
    num_requests: int = 16
    warmup_requests: int = 2
    trials: int = 3
    timeout_s: float = 60.0
    ignore_eos: bool = True  # fixed output length makes runs comparable

    def validate(self) -> "BenchConfig":
        if not self.base_url.startswith(("http://127.0.0.1", "http://localhost")):
            raise ValueError("benchmarks target local servers only (http://127.0.0.1 or http://localhost)")
        checks = [(1 <= self.max_tokens <= 2048, "max_tokens"), (1 <= self.concurrency <= 256, "concurrency"),
                  (1 <= self.num_requests <= 5000, "num_requests"), (0 <= self.warmup_requests <= 100, "warmup"),
                  (1 <= self.trials <= 20, "trials"), (1 <= self.timeout_s <= 900, "timeout_s"),
                  (0 < len(self.prompt) <= 20000, "prompt")]
        for ok, name in checks:
            if not ok:
                raise ValueError(f"{name} out of range")
        return self


class ResourceSampler:
    """Samples server process RSS/CPU and GPU memory in a background thread."""

    def __init__(self, pid: int | None, interval_s: float = 0.25) -> None:
        self.pid, self.interval = pid, interval_s
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        proc = None
        if self.pid:
            try:
                proc = psutil.Process(self.pid)
                proc.cpu_percent(None)
            except psutil.Error:
                proc = None
        while not self._stop.is_set():
            s: dict[str, Any] = {"t": time.time()}
            if proc:
                try:
                    s["rss_mb"] = proc.memory_info().rss / 1024**2
                    s["cpu_pct"] = proc.cpu_percent(None)
                except psutil.Error:
                    pass
            rc, out = _run(NVIDIA_SMI_QUERY, timeout=2)
            if rc == 0:
                s["gpu"] = [{"vram_used_mb": g["vram_used_mb"], "util_pct": g["utilization_pct"]}
                            for g in parse_nvidia_smi(out)]
            self.samples.append(s)
            self._stop.wait(self.interval)

    def __enter__(self) -> "ResourceSampler":
        self._t.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._t.join(timeout=5)

    def summary(self) -> dict[str, Any]:
        rss = [s["rss_mb"] for s in self.samples if "rss_mb" in s]
        cpu = [s["cpu_pct"] for s in self.samples if "cpu_pct" in s]
        vram = [sum(g["vram_used_mb"] for g in s["gpu"]) for s in self.samples if s.get("gpu")]
        return {
            "samples": len(self.samples),
            "server_rss_mb_peak": max(rss) if rss else None,
            "server_cpu_pct_mean": sum(cpu) / len(cpu) if cpu else None,
            "gpu_vram_used_mb_peak": max(vram) if vram else None,
            "gpu_sampled": bool(vram),
        }


async def _one(client: httpx.AsyncClient, cfg: BenchConfig) -> RequestSample:
    body = {"model": cfg.model, "prompt": cfg.prompt, "max_tokens": cfg.max_tokens, "temperature": 0.0,
            "stream": True, "ignore_eos": cfg.ignore_eos, "stream_options": {"include_usage": True}}
    start = time.perf_counter()
    ttft = None
    chunks = 0
    usage_tokens = None
    try:
        async with client.stream("POST", cfg.base_url + "/v1/completions", json=body, timeout=cfg.timeout_s) as r:
            if r.status_code != 200:
                await r.aread()
                return RequestSample(start, None, None, 0, error=f"http_{r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                if obj.get("usage"):
                    usage_tokens = obj["usage"].get("completion_tokens")
                for ch in obj.get("choices") or []:
                    if ch.get("text"):
                        chunks += 1
                        if ttft is None:
                            ttft = time.perf_counter() - start
        end = time.perf_counter()
        return RequestSample(start, end, ttft, usage_tokens if usage_tokens is not None else chunks)
    except httpx.TimeoutException:
        return RequestSample(start, None, ttft, chunks, error="timeout")
    except httpx.HTTPError as e:
        return RequestSample(start, None, ttft, chunks, error=type(e).__name__)


async def _trial(cfg: BenchConfig, n: int) -> tuple[list[RequestSample], float]:
    samples: list[RequestSample] = []
    remaining = n
    lock = asyncio.Lock()
    limits = httpx.Limits(max_connections=cfg.concurrency + 2)
    async with httpx.AsyncClient(limits=limits) as client:

        async def worker() -> None:
            nonlocal remaining
            while True:
                async with lock:
                    if remaining <= 0:
                        return
                    remaining -= 1
                samples.append(await _one(client, cfg))

        t0 = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(min(cfg.concurrency, n))))
        return samples, time.perf_counter() - t0


def run_benchmark(cfg: BenchConfig, server_pid: int | None = None,
                  log: Callable[[str], None] = lambda _: None,
                  progress: Callable[[float], None] = lambda _: None) -> dict[str, Any]:
    cfg.validate()
    started = time.time()
    if cfg.warmup_requests:
        log(f"warm-up: {cfg.warmup_requests} request(s), results discarded")
        warm, _ = asyncio.run(_trial(BenchConfig(**{**asdict(cfg), "concurrency": 1}), cfg.warmup_requests))
        bad = [s for s in warm if not s.ok]
        if len(bad) == len(warm):
            log(f"warm-up failed: every request errored ({bad[0].error}); aborting")
            return {"config": asdict(cfg), "started_at": started, "aborted": "warmup_failed",
                    "warmup_errors": [s.error for s in bad], "trials": []}
    trials, raw = [], []
    with ResourceSampler(server_pid) as sampler:
        for i in range(cfg.trials):
            log(f"trial {i + 1}/{cfg.trials}: {cfg.num_requests} requests at concurrency {cfg.concurrency}")
            samples, wall = asyncio.run(_trial(cfg, cfg.num_requests))
            s = summarize(samples, wall)
            log(f"  ok={s['succeeded']} failed={s['failed']} ttft_p50={_f(s['ttft_ms']['p50'])}ms "
                f"e2e_p95={_f(s['e2e_ms']['p95'])}ms out_tps={_f(s['output_throughput_tps'])}")
            trials.append(s)
            raw.append([x.to_row() for x in samples])
            progress((i + 1) / cfg.trials)
    return {
        "config": asdict(cfg),
        "started_at": started,
        "finished_at": time.time(),
        "trials": trials,
        "aggregate": aggregate_trials(trials),
        "resources": sampler.summary(),
        "raw_samples": raw,
        "raw_columns": ["start_s", "end_s", "ttft_s", "output_tokens", "error"],
    }


def _f(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}"
