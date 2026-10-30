"""Benchmark statistics. Pure functions, no I/O, easy to test.

Definitions used throughout Inference Lab:
  TTFT  time to first token: request sent -> first generated token received.
  TPOT  time per output token: (end-to-end latency - TTFT) / (output tokens - 1).
  E2E   end-to-end latency: request sent -> last byte received.
  P50 / P95 / P99  percentiles across requests (linear interpolation between closest ranks).

Across trials, each headline metric keeps its per-trial values, their mean and a 95% confidence interval
(Student t). A comparison reports the difference of trial means with a 95% Welch interval; "significant"
means that interval excludes zero. With 2-3 trials these intervals are wide on purpose: few trials cannot
support a precise claim, and the numbers say so.
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


# Two-sided 95% Student t critical values by degrees of freedom (df 1-30, then a few anchors).
_T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145,
         2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048,
         2.045, 2.042]


def t975(df: float) -> float:
    """t quantile for a two-sided 95% interval. Fractional df (Welch) round down, which widens the interval."""
    if df < 1:
        raise ValueError("df must be >= 1")
    d = int(math.floor(df))
    if d <= 30:
        return _T975[d - 1]
    return 2.021 if d < 60 else 2.000 if d < 120 else 1.980 if d < 1000 else 1.960


def mean_ci95(values: list[float]) -> tuple[float, float, float] | None:
    """(mean, low, high) of a 95% t interval for the mean, or None with fewer than 2 values."""
    if len(values) < 2:
        return None
    m = statistics.fmean(values)
    half = t975(len(values) - 1) * statistics.stdev(values) / math.sqrt(len(values))
    return m, m - half, m + half


def diff_ci95(a: list[float], b: list[float]) -> tuple[float, float, float] | None:
    """(mean(b) - mean(a), low, high): Welch 95% interval for the difference of means, or None if either side
    has fewer than 2 values. Welch does not assume equal variances, which suits runs on different settings."""
    if len(a) < 2 or len(b) < 2:
        return None
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = statistics.variance(a) / len(a), statistics.variance(b) / len(b)
    se2 = va + vb
    if se2 == 0:
        return mb - ma, mb - ma, mb - ma
    df = se2 ** 2 / ((va ** 2 / (len(a) - 1) if va else 0) + (vb ** 2 / (len(b) - 1) if vb else 0))
    half = t975(max(1.0, df)) * math.sqrt(se2)
    return mb - ma, mb - ma - half, mb - ma + half


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
    # False when the server reported no usage and output_tokens is a count of text chunks, not tokens.
    tokens_exact: bool = True

    @property
    def ok(self) -> bool:
        return self.error is None and self.end is not None

    @property
    def e2e_s(self) -> float | None:
        return (self.end - self.start) if self.end is not None else None

    @property
    def tpot_s(self) -> float | None:
        if not self.ok or not self.tokens_exact or self.ttft_s is None or self.output_tokens < 2:
            return None
        return (self.e2e_s - self.ttft_s) / (self.output_tokens - 1)

    def to_row(self) -> list[Any]:
        return [round(self.start, 6), None if self.end is None else round(self.end, 6),
                None if self.ttft_s is None else round(self.ttft_s, 6), self.output_tokens, self.error, self.tokens_exact]


def summarize(samples: list[RequestSample], wall_s: float) -> dict[str, Any]:
    ok = [s for s in samples if s.ok]
    errors: dict[str, int] = {}
    for s in samples:
        if s.error:
            errors[s.error] = errors.get(s.error, 0) + 1
    ms = lambda xs: [x * 1000 if x is not None else None for x in xs]  # noqa: E731
    exact = [s for s in ok if s.tokens_exact]
    source = "usage" if len(exact) == len(ok) else ("chunks" if not exact else "mixed")
    # Token throughput is only reported when every successful request has a server-reported token count.
    total_tokens = sum(s.output_tokens for s in ok) if source == "usage" else None
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
        "token_count_source": source,
        "output_tokens_total": total_tokens,
        "output_chunks_total": sum(s.output_tokens for s in ok if not s.tokens_exact) if source != "usage" else None,
        "request_throughput_rps": len(ok) / wall_s if wall_s > 0 else None,
        "output_throughput_tps": total_tokens / wall_s if wall_s > 0 and total_tokens is not None else None,
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
        ci = mean_ci95(vals)
        out[k] = {"median": statistics.median(vals) if vals else None, "min": min(vals) if vals else None,
                  "max": max(vals) if vals else None, "trials": len(vals), "values": vals,
                  "mean": statistics.fmean(vals) if vals else None,
                  "ci95": [ci[1], ci[2]] if ci else None}
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
        # Records saved before per-trial values were kept have no "values": no interval, no significance call.
        d = diff_ci95(b.get("values") or [], (c or {}).get("values") or [])
        rows[k] = {"baseline": bm, "candidate": cm, "change_pct": change, "better": better,
                   "ranges_overlap": overlap,
                   "diff_mean": d[0] if d else None, "diff_ci95": [d[1], d[2]] if d else None,
                   "significant": (not (d[1] <= 0 <= d[2])) if d else None,
                   "trials": [len(b.get("values") or []), len((c or {}).get("values") or [])]}
    return rows
