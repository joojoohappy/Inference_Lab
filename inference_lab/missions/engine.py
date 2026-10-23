"""Mission engine: loads mission data, evaluates deterministic checks against run evidence,
and tracks progress. The AI tutor has no access to anything in this module's write path.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from ..config import load_settings
from .schema import Check, Mission, Step

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_missions(data_dir: Path = DATA_DIR) -> list[Mission]:
    missions = [Mission.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
                for p in sorted(data_dir.glob("m*.yaml"))]
    ids = {m.id for m in missions}
    for m in missions:
        for pre in m.prerequisites:
            if pre not in ids:
                raise ValueError(f"{m.id}: unknown prerequisite {pre}")
    return sorted(missions, key=lambda m: m.number)


_MISSING = object()


def resolve(path: str, evidence: dict[str, Any]) -> Any:
    cur: Any = evidence
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _MISSING
    return cur


def evaluate_check(check: Check, evidence: dict[str, Any]) -> dict[str, Any]:
    """Pure and deterministic: same evidence, same answer."""
    actual = resolve(check.path, evidence)
    v = check.value
    if actual is _MISSING:
        passed = False
    else:
        try:
            passed = {
                "eq": lambda: actual == v,
                "ne": lambda: actual != v,
                "gt": lambda: actual is not None and actual > v,
                "gte": lambda: actual is not None and actual >= v,
                "lt": lambda: actual is not None and actual < v,
                "lte": lambda: actual is not None and actual <= v,
                "exists": lambda: actual is not None,
                "truthy": lambda: bool(actual),
                "in": lambda: actual in v,
                "len_gte": lambda: len(actual) >= v,
                "contains": lambda: v in actual,
            }[check.op]()
        except TypeError:
            passed = False
    shown = None if actual is _MISSING else actual
    if isinstance(shown, (dict, list)) and len(json.dumps(shown, default=str)) > 300:
        shown = f"<{type(shown).__name__} len={len(shown)}>"
    return {"id": check.id, "passed": bool(passed), "path": check.path, "op": check.op, "expected": v,
            "actual": shown, "missing": actual is _MISSING}


def evaluate_step(step: Step, run: dict[str, Any] | None) -> dict[str, Any]:
    if run is None:
        return {"status": "not_started", "checks": []}
    if run["status"] in ("blocked", "not_run", "failed", "running", "pending"):
        return {"status": run["status"], "checks": [], "run_id": run["id"]}
    evidence = {"run": run, "result": run.get("result") or {}}
    results = [evaluate_check(c, evidence) for c in step.checks]
    ok = all(r["passed"] for r in results)
    return {"status": "verified" if ok else "check_failed", "checks": results, "run_id": run["id"]}


class Progress:
    """Persisted learner progress. Language and mode are NOT stored here: switching them never
    touches progress. Completion only changes through record_run / record_quiz."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (load_settings().ensure().data_dir / "progress.json")
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {"missions": {}}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except ValueError:
                pass

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def _step(self, mid: str, sid: str) -> dict[str, Any]:
        m = self.data["missions"].setdefault(mid, {"steps": {}, "challenge": None})
        return m["steps"].setdefault(sid, {"hints_used": 0, "evaluation": None, "quiz": None})

    def record_evaluation(self, mid: str, sid: str, evaluation: dict[str, Any], run: dict[str, Any]) -> None:
        with self._lock:
            st = self._step(mid, sid)
            # A verified step stays verified: later failed attempts are kept as attempts, not regressions.
            if st.get("evaluation", {}) and st["evaluation"].get("status") == "verified" \
                    and evaluation["status"] != "verified":
                st.setdefault("attempts", []).append({"run_id": run["id"], "status": evaluation["status"]})
            else:
                st["evaluation"] = {**evaluation, "at": time.time(), "provenance": run.get("provenance"),
                                    "experiment_id": run.get("experiment_id")}
                st.setdefault("attempts", []).append({"run_id": run["id"], "status": evaluation["status"]})
            del st["attempts"][:-20]
            self._save()

    def record_quiz(self, mid: str, sid: str, correct: bool) -> None:
        with self._lock:
            st = self._step(mid, sid)
            st["quiz"] = {"correct": correct, "at": time.time(),
                          "attempts": ((st.get("quiz") or {}).get("attempts", 0) + 1)}
            self._save()

    def use_hint(self, mid: str, sid: str) -> int:
        with self._lock:
            st = self._step(mid, sid)
            st["hints_used"] += 1
            self._save()
            return st["hints_used"]

    def record_challenge(self, mid: str, evaluation: dict[str, Any]) -> None:
        with self._lock:
            m = self.data["missions"].setdefault(mid, {"steps": {}, "challenge": None})
            if not (m.get("challenge") or {}).get("status") == "verified":
                m["challenge"] = {**evaluation, "at": time.time()}
            self._save()

    def reset(self) -> None:
        with self._lock:
            self.data = {"missions": {}}
            self._save()


def step_done(step: Step, st: dict[str, Any] | None, capabilities: dict[str, bool]) -> str:
    """verified | not_available | pending.  Optional steps never block completion."""
    st = st or {}
    if step.action is not None:
        ok = (st.get("evaluation") or {}).get("status") == "verified"
    else:
        ok = (st.get("quiz") or {}).get("correct") is True
    if ok:
        return "verified"
    if any(not capabilities.get(c) for c in step.requires_capabilities):
        return "not_available"
    return "pending"


def mission_status(m: Mission, progress: Progress, capabilities: dict[str, bool],
                   all_status: dict[str, str] | None = None) -> dict[str, Any]:
    pm = progress.data["missions"].get(m.id, {})
    steps = {s.id: step_done(s, pm.get("steps", {}).get(s.id), capabilities) for s in m.steps}
    required = [s for s in m.steps if not s.optional]
    blocked_by = [p for p in m.prerequisites if (all_status or {}).get(p) != "complete"]
    done_required = [s for s in required if steps[s.id] == "verified"]
    unavailable = [s.id for s in required if steps[s.id] == "not_available"]
    hints = sum(v.get("hints_used", 0) for v in pm.get("steps", {}).values())
    if len(done_required) == len(required):
        state = "complete"
    elif unavailable:
        state = "not_available"
    elif blocked_by:
        state = "locked"
    elif done_required or any(v == "verified" for v in steps.values()):
        state = "in_progress"
    else:
        state = "available"
    challenge_ok = (pm.get("challenge") or {}).get("status") == "verified"
    # Mastery is earned with evidence, not clicks: complete + independent challenge, few hints.
    mastery = "independent" if state == "complete" and challenge_ok and hints == 0 else \
        ("practiced" if state == "complete" else ("started" if state == "in_progress" else "none"))
    return {"id": m.id, "state": state, "steps": steps, "blocked_by": blocked_by, "unavailable_steps": unavailable,
            "required": len(required), "verified": len(done_required), "hints_used": hints,
            "challenge_verified": challenge_ok, "mastery": mastery}


def all_statuses(missions: list[Mission], progress: Progress, capabilities: dict[str, bool]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    simple: dict[str, str] = {}
    for m in missions:  # sorted by number, prerequisites always earlier
        st = mission_status(m, progress, capabilities, simple)
        out[m.id] = st
        simple[m.id] = st["state"]
    return out
