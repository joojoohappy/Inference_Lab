"""Benchmark statistics. Pure functions, no I/O, easy to test.

Definitions used throughout Inference Lab:
  TTFT  time to first token: request sent -> first generated token received.
  TPOT  time per output token: (end-to-end latency - TTFT) / (output tokens - 1).
  E2E   end-to-end latency: request sent -> last byte received.
  P50 / P95 / P99  percentiles across requests (linear interpolation between closest ranks).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Iterable


def percentile(values: Iterable[float], p: float) -> float | None:
    xs = sorted(v for v in values if v is not None and not math.isnan(v))
    if not xs:
        return None
    if not 0 <= p <= 100:
        raise ValueError("p must be within 0..100")
    k = (len(xs) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def dist(values: list[float | None]) -> dict[str, float | None]:
    xs = [v for v in values if v is not None]
    if not xs:
        return {"n": 0, "mean": None, "p50": None, "p95": None, "p99": None, "min": None, "max": None}
    return {"n": len(xs), "mean": statistics.fmean(xs), "p50": percentile(xs, 50), "p95": percentile(xs, 95),
            "p99": percentile(xs, 99), "min": min(xs), "max": max(xs)}


@dataclass
class RequestSample:
    start: float
    end: float | None
    ttft_s: float | None
    output_tokens: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.end is not None

    @property
    def e2e_s(self) -> float | None:
        return (self.end - self.start) if self.end is not None else None

    @property
    def tpot_s(self) -> float | None:
        if not self.ok or self.ttft_s is None or self.output_tokens < 2:
            return None
        return (self.e2e_s - self.ttft_s) / (self.output_tokens - 1)

    def to_row(self) -> list[Any]:
        return [round(self.start, 6), None if self.end is None else round(self.end, 6),
                None if self.ttft_s is None else round(self.ttft_s, 6), self.output_tokens, self.error]


def summarize(samples: list[RequestSample], wall_s: float) -> dict[str, Any]:
    ok = [s for s in samples if s.ok]
    errors: dict[str, int] = {}
    for s in samples:
        if s.error:
            errors[s.error] = errors.get(s.error, 0) + 1
    ms = lambda xs: [x * 1000 if x is not None else None for x in xs]  # noqa: E731
    total_tokens = sum(s.output_tokens for s in ok)
    return {
        "requests": len(samples),
        "succeeded": len(ok),
        "failed": len(samples) - len(ok),
        "error_rate": (len(samples) - len(ok)) / len(samples) if samples else None,
        "errors": errors,
        "wall_s": wall_s,
        "ttft_ms": dist(ms([s.ttft_s for s in ok])),
        "tpot_ms": dist(ms([s.tpot_s for s in ok])),
        "e2e_ms": dist(ms([s.e2e_s for s in ok])),
        "output_tokens_total": total_tokens,
        "request_throughput_rps": len(ok) / wall_s if wall_s > 0 else None,
        "output_throughput_tps": total_tokens / wall_s if wall_s > 0 else None,
    }


def aggregate_trials(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Median across trials of the headline metrics, plus min/max to show run-to-run spread."""
    keys = {
        "ttft_p50_ms": lambda t: t["ttft_ms"]["p50"],
        "ttft_p95_ms": lambda t: t["ttft_ms"]["p95"],
        "tpot_p50_ms": lambda t: t["tpot_ms"]["p50"],
        "e2e_p50_ms": lambda t: t["e2e_ms"]["p50"],
        "e2e_p95_ms": lambda t: t["e2e_ms"]["p95"],
        "request_throughput_rps": lambda t: t["request_throughput_rps"],
        "output_throughput_tps": lambda t: t["output_throughput_tps"],
        "error_rate": lambda t: t["error_rate"],
    }
    out: dict[str, Any] = {}
    for k, f in keys.items():
        vals = [f(t) for t in trials if f(t) is not None]
        out[k] = {"median": statistics.median(vals) if vals else None, "min": min(vals) if vals else None,
                  "max": max(vals) if vals else None, "trials": len(vals)}
    return out


def compare(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Relative change of each aggregate median. Lower is better for latency, higher for throughput."""
    lower_better = {"ttft_p50_ms", "ttft_p95_ms", "tpot_p50_ms", "e2e_p50_ms", "e2e_p95_ms", "error_rate"}
    rows = {}
    for k, b in baseline.items():
        c = candidate.get(k)
        bm, cm = b.get("median"), (c or {}).get("median")
        if bm is None or cm is None:
            rows[k] = {"baseline": bm, "candidate": cm, "change_pct": None, "better": None}
            continue
        change = ((cm - bm) / bm * 100) if bm else None
        # Overlapping min..max ranges across trials mean the difference may be noise.
        overlap = not (c["max"] < b["min"] or c["min"] > b["max"])
        better = None if change is None or change == 0 else ((change < 0) == (k in lower_better))
        rows[k] = {"baseline": bm, "candidate": cm, "change_pct": change, "better": better,
                   "ranges_overlap": overlap}
    return rows
