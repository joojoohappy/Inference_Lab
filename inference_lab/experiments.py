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
from .provenance import LEGACY_IMPORTED, Provenance, is_claimable, is_imported

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


# Fields left out of the whole-record checksum: notes may be added later, and the checksums and import
# bookkeeping are written after the hash is taken.
_UNHASHED = {"notes", "checksum", "record_checksum", "imported_from", "imported_at", "import_check"}


def record_checksum(rec: dict[str, Any]) -> str:
    """SHA-256 over every field that describes the measurement (model, hardware, engine, params, environment,
    result, provenance...). Detects edits after export. It is NOT a signature: whoever writes a record can
    compute a matching value, so it proves internal consistency, never authenticity."""
    return checksum({k: v for k, v in rec.items() if k not in _UNHASHED})


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
    rec["record_checksum"] = record_checksum(rec)
    return rec


def _upgrade(rec: dict[str, Any]) -> dict[str, Any]:
    """Records saved before the IMPORTED rename said VERIFIED_IMPORTED; present them with today's label."""
    if rec.get("provenance") == LEGACY_IMPORTED:
        rec["provenance"] = Provenance.IMPORTED.value
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
        return _upgrade(json.loads(self._path(exp_id).read_text(encoding="utf-8")))

    def list(self, kind: str | None = None) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.root.glob("exp-*.json"), reverse=True):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if kind and rec.get("kind") != kind:
                continue
            out.append(_upgrade(rec))
        return out

    def import_record(self, data: dict[str, Any]) -> dict[str, Any]:
        """Accept an exported record if its schema is valid and its checksums are consistent.

        This is an integrity check, not proof of origin: anyone can write a record and compute matching
        checksums. Imported records are therefore labelled IMPORTED, kept out of "measured results", and
        flagged when compared. Records exported before `record_checksum` existed are accepted with only the
        result checksum, and say so in `import_check`.
        """
        required = {"schema_version", "id", "kind", "provenance", "result", "checksum", "hardware", "params"}
        missing = required - set(data)
        if missing:
            raise ValueError(f"missing fields: {sorted(missing)}")
        if data["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")
        if checksum(data["result"]) != data["checksum"]:
            raise ValueError("checksum mismatch: result was modified after export")
        has_record_sum = "record_checksum" in data
        if has_record_sum and record_checksum(data) != data["record_checksum"]:
            raise ValueError("record_checksum mismatch: model, hardware, engine, params or result changed after export")
        try:
            prov = Provenance(data["provenance"])
        except ValueError as e:
            raise ValueError("unknown provenance") from e
        if prov not in (Provenance.LIVE_MEASURED, Provenance.IMPORTED):
            raise ValueError("only measured records can be imported")
        rec = {**data, "id": f"exp-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
               "provenance": Provenance.IMPORTED.value, "imported_from": data["id"],
               "imported_at": time.time(),
               "import_check": {"schema": "valid", "result_checksum": "match",
                                "record_checksum": "match" if has_record_sum else "absent",
                                "origin": "not_verified"}}
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
    provs = (a["provenance"], b["provenance"])
    if any(is_imported(p) for p in provs):
        warnings.append("imported_unverified")
    if any(not is_claimable(p) and not is_imported(p) for p in provs):
        warnings.append("non_measured_provenance")
    # Unknown identity is a limitation, not a match: two records with no model revision may be different weights.
    if any((r.get("model") or {}).get("revision") is None for r in (a, b)):
        warnings.append("unknown_model_revision")
    if any((r.get("engine") or {}).get("version") is None for r in (a, b)):
        warnings.append("unknown_engine_version")
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
