"""Local, append-only experiment records (one JSON file per experiment).

An experiment record answers: what ran, on what, with which settings, when, and where did
the numbers come from (provenance). Records are never silently rewritten; failures are kept.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from . import __version__
from .bench.metrics import compare as compare_aggregates
from .config import REPO_ROOT, load_settings
from .provenance import Provenance, is_claimable

SCHEMA_VERSION = 1
# Settings that define a benchmark workload. Changing more than one between a baseline and a
# candidate makes it impossible to attribute a difference to a single cause.
WORKLOAD_KEYS = ("prompt", "max_tokens", "concurrency", "num_requests", "warmup_requests", "trials", "ignore_eos")


def _git_commit() -> str | None:
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                           text=True, timeout=5, check=False)
        return p.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def environment() -> dict[str, Any]:
    return {"inference_lab": __version__, "lab_commit": _git_commit(), "python": platform.python_version(),
            "os": f"{platform.system()} {platform.release()}"}


def checksum(result: Any) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()


def new_record(kind: str, provenance: Provenance, *, model: dict[str, Any] | None = None,
               hardware: dict[str, Any] | None = None, engine: dict[str, Any] | None = None,
               params: dict[str, Any] | None = None, result: Any = None, mission_id: str | None = None,
               run_id: str | None = None, error: str | None = None, notes: dict[str, Any] | None = None) -> dict[str, Any]:
    rec = {
        "schema_version": SCHEMA_VERSION,
        "id": f"exp-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "kind": kind,
        "provenance": Provenance(provenance).value,
        "created_at": time.time(),
        "mission_id": mission_id,
        "run_id": run_id,
        "model": model or {},
        "hardware": hardware or {},
        "engine": engine or {},
        "params": params or {},
        "environment": environment(),
        "result": result,
        "error": error,
        "notes": notes or {},
    }
    rec["checksum"] = checksum(rec["result"])
    return rec


class ExperimentStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or load_settings().ensure().experiments_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, exp_id: str) -> Path:
        if not exp_id.startswith("exp-") or "/" in exp_id or ".." in exp_id:
            raise ValueError("invalid experiment id")
        return self.root / f"{exp_id}.json"

    def save(self, rec: dict[str, Any]) -> dict[str, Any]:
        p = self._path(rec["id"])
        if p.exists():
            raise FileExistsError(f"experiment {rec['id']} already exists; records are append-only")
        p.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
        return rec

    def annotate(self, exp_id: str, notes: dict[str, Any]) -> dict[str, Any]:
        """Notes (hypothesis, decision) may be added later. Results and provenance may not change."""
        rec = self.get(exp_id)
        rec["notes"] = {**rec.get("notes", {}), **{k: str(v)[:4000] for k, v in notes.items()}}
        self._path(exp_id).write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
        return rec

    def get(self, exp_id: str) -> dict[str, Any]:
        return json.loads(self._path(exp_id).read_text(encoding="utf-8"))

    def list(self, kind: str | None = None) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.root.glob("exp-*.json"), reverse=True):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if kind and rec.get("kind") != kind:
                continue
            out.append(rec)
        return out

    def import_record(self, data: dict[str, Any]) -> dict[str, Any]:
        """Accept an exported record only if its schema and checksum verify."""
        required = {"schema_version", "id", "kind", "provenance", "result", "checksum", "hardware", "params"}
        missing = required - set(data)
        if missing:
            raise ValueError(f"missing fields: {sorted(missing)}")
        if data["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")
        if checksum(data["result"]) != data["checksum"]:
            raise ValueError("checksum mismatch: result was modified after export")
        if data["provenance"] not in (Provenance.LIVE_MEASURED.value, Provenance.VERIFIED_IMPORTED.value):
            raise ValueError("only measured records can be imported as verified")
        rec = {**data, "id": f"exp-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
               "provenance": Provenance.VERIFIED_IMPORTED.value, "imported_from": data["id"],
               "imported_at": time.time()}
        return self.save(rec)


def comparability(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Which variables differ between two benchmark records, and can they be fairly compared?"""
    diffs = []
    if (a.get("model") or {}).get("id") != (b.get("model") or {}).get("id"):
        diffs.append("model")
    elif (a.get("model") or {}).get("revision") != (b.get("model") or {}).get("revision"):
        diffs.append("model_revision")
    if a.get("hardware") != b.get("hardware"):
        diffs.append("hardware")
    if (a.get("engine") or {}).get("name") != (b.get("engine") or {}).get("name"):
        diffs.append("engine")
    elif (a.get("engine") or {}).get("version") != (b.get("engine") or {}).get("version"):
        diffs.append("engine_version")
    pa, pb = a.get("params") or {}, b.get("params") or {}
    diffs += [f"workload.{k}" for k in WORKLOAD_KEYS if pa.get(k) != pb.get(k)]
    warnings = []
    if not (is_claimable(a["provenance"]) and is_claimable(b["provenance"])):
        warnings.append("non_measured_provenance")
    if len(diffs) > 1:
        warnings.append("more_than_one_variable_changed")
    if not diffs:
        warnings.append("no_variable_changed")
    return {"differences": diffs, "comparable": len(diffs) == 1 and not warnings, "warnings": warnings}


def compare_records(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    ba = (baseline.get("result") or {}).get("aggregate") or {}
    ca = (candidate.get("result") or {}).get("aggregate") or {}
    return {"baseline_id": baseline["id"], "candidate_id": candidate["id"],
            "comparability": comparability(baseline, candidate), "metrics": compare_aggregates(ba, ca)}
