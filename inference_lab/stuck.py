"""Context-aware "is this stuck?" diagnosis. Deterministic; uses evidence, not elapsed time alone.

Signals: run status, heartbeat age (any log line or progress update refreshes it), progress
history, the action's time budget, and for servers the process state and /health.
A long-running action that keeps producing heartbeats and progress is reported as working.
"""

from __future__ import annotations

import time
from typing import Any

from .i18n import t

HEARTBEAT_STALE_S = 30.0
PROGRESS_STALL_S = 60.0


def _progress_stalled_for(samples: list[list[float]], now: float) -> float | None:
    """Seconds since progress last increased; None if there is no progress signal."""
    if not samples:
        return None
    last_val = samples[-1][1]
    since = samples[-1][0]
    for ts, val in reversed(samples):
        if val < last_val:
            break
        since = ts
    return now - since


def error_help(code: str, lang: str) -> dict[str, str]:
    base = code.split(":", 1)[0]
    return {"code": code, "what": t(lang, f"err.{base}.what"), "why": t(lang, f"err.{base}.why"),
            "next": t(lang, f"err.{base}.next")}


def diagnose(run: dict[str, Any], lang: str = "en", now: float | None = None,
             server_health: dict[str, Any] | None = None) -> dict[str, Any]:
    now = now or time.time()
    status = run["status"]
    evidence: list[str] = []
    if status in ("succeeded",):
        return {"state": "done", "summary": t(lang, "stuck.done"), "evidence": [], "causes": [], "next": []}
    if status in ("failed", "blocked", "not_run"):
        code = (run.get("error") or {}).get("code", "unexpected_error")
        h = error_help(code, lang)
        evidence.append(t(lang, "stuck.ev.status", status=status, code=code))
        if run.get("logs"):
            evidence.append(t(lang, "stuck.ev.last_log", msg=run["logs"][-1]["msg"][:200]))
        return {"state": status, "summary": h["what"], "evidence": evidence, "causes": [h["why"]], "next": [h["next"]]}

    started = run.get("started_at") or now
    elapsed = now - started
    hb_age = now - (run.get("heartbeat_at") or started)
    stalled = _progress_stalled_for(run.get("progress_samples") or [], now)
    evidence.append(t(lang, "stuck.ev.elapsed", s=f"{elapsed:.0f}", budget=f"{run.get('timeout_s', 0):.0f}"))
    evidence.append(t(lang, "stuck.ev.heartbeat", s=f"{hb_age:.0f}"))
    if run.get("progress") is not None:
        evidence.append(t(lang, "stuck.ev.progress", pct=f"{run['progress'] * 100:.0f}"))
    if stalled is not None:
        evidence.append(t(lang, "stuck.ev.progress_flat", s=f"{stalled:.0f}"))
    if server_health is not None and server_health.get("process_alive") is False:
        evidence.append(t(lang, "stuck.ev.process_dead"))
        state = "process_exited"
    elif elapsed > run.get("timeout_s", 1e9):
        state = "over_budget"
    elif hb_age > HEARTBEAT_STALE_S:
        state = "possibly_stalled"
    elif stalled is not None and stalled > PROGRESS_STALL_S:
        state = "slow_no_progress"
    else:
        state = "working"
    action = run.get("action", "")
    causes = [] if state == "working" else [t(lang, f"stuck.cause.{action}"), t(lang, "stuck.cause.generic")]
    nxt = [t(lang, "stuck.next.wait")] if state == "working" else [t(lang, "stuck.next.logs"),
                                                                     t(lang, f"stuck.next.{state}")]
    return {"state": state, "summary": t(lang, f"stuck.state.{state}"), "evidence": evidence,
            "causes": [c for c in causes if not c.startswith("stuck.")], "next": nxt}
