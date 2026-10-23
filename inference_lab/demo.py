"""Educational demo data. Every value here is synthetic and labelled DEMO_SAMPLE.

The curve comes from a textbook queueing toy model (one server, fixed service time), not from
any hardware. It exists so the charts are not empty before you run your own benchmark.
"""

from __future__ import annotations

from typing import Any

from .provenance import Provenance


def demo_concurrency_sweep() -> dict[str, Any]:
    service_ms = 40.0  # assumed per-request service time of a server that handles one request at a time
    rows = []
    for c in (1, 2, 4, 8, 16):
        # Closed loop, single server: each request waits for the c-1 requests ahead of it.
        e2e = service_ms * c
        rows.append({"concurrency": c, "e2e_p50_ms": e2e, "ttft_p50_ms": e2e - service_ms * 0.8,
                     "request_throughput_rps": 1000.0 / service_ms})
    return {
        "provenance": Provenance.DEMO_SAMPLE.value,
        "label": "Synthetic queueing example (not measured)",
        "assumptions": ["single server processes one request at a time",
                        f"fixed service time {service_ms:.0f} ms", "closed-loop clients"],
        "rows": rows,
    }
