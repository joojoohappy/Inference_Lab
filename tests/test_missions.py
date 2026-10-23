from pathlib import Path

import pytest

from inference_lab.config import REPO_ROOT
from inference_lab.missions.engine import Progress, all_statuses, evaluate_step, load_missions
from inference_lab.research import registry
from inference_lab.sourcemap import safe_path, symbol_range
from inference_lab.tutor.tutor import concepts

MISSIONS = load_missions()
CAPS_CPU = {"cpu_inference": True}


def test_seven_missions_in_order():
    assert [m.number for m in MISSIONS] == [1, 2, 3, 4, 5, 6, 7]
    assert len({m.id for m in MISSIONS}) == 7


@pytest.mark.parametrize("m", MISSIONS, ids=lambda m: m.id)
def test_mission_is_complete_and_bilingual(m):
    assert m.version and m.objectives and m.completion_evidence.en and m.completion_evidence.zh_TW
    for loc in [m.title, m.tagline, *m.objectives]:
        assert loc.en.strip() and loc.zh_TW.strip()
    for s in m.steps:
        for loc in [s.title, s.what, s.why, s.expected, s.failure, *s.hints]:
            assert loc.en.strip() and loc.zh_TW.strip(), f"{m.id}/{s.id}"
        assert s.action or s.quiz, f"{m.id}/{s.id} has nothing to verify"
        if s.action:
            assert s.checks, f"{m.id}/{s.id}: an action step needs deterministic checks"


@pytest.mark.parametrize("m", MISSIONS, ids=lambda m: m.id)
def test_source_refs_point_at_real_code(m):
    for s in m.steps:
        for ref in s.sources:
            p = safe_path(ref.file)
            if ref.symbol:
                assert symbol_range(p, ref.symbol), f"{m.id}/{s.id}: {ref.file}:{ref.symbol} not found"


@pytest.mark.parametrize("m", MISSIONS, ids=lambda m: m.id)
def test_concepts_and_references_exist(m):
    known_concepts = set(concepts())
    known_refs = {r["id"] for r in registry.load()}
    for c in m.concepts + [s.concept for s in m.steps if s.concept]:
        assert c in known_concepts, c
    for r in m.references:
        assert r in known_refs, r


def test_prerequisites_point_backwards():
    seen = set()
    for m in MISSIONS:
        assert set(m.prerequisites) <= seen
        seen.add(m.id)


def _run(status="succeeded", result=None, provenance="LIVE_MEASURED"):
    return {"id": "run-x", "status": status, "provenance": provenance, "result": result, "experiment_id": "exp-1",
            "error": None}


def test_evaluation_is_deterministic():
    step = MISSIONS[0].steps[0]
    from inference_lab.hardware import scan
    r = _run(result=scan())
    assert evaluate_step(step, r) == evaluate_step(step, r)


def test_failed_run_never_verifies():
    step = MISSIONS[0].steps[0]
    ev = evaluate_step(step, _run(status="failed"))
    assert ev["status"] != "verified"


def test_demo_data_cannot_complete_a_benchmark_step():
    step = next(s for s in MISSIONS[4].steps if s.id == "s2-baseline")
    fake = {"trials": [{}, {}, {}], "aggregate": {"ttft_p50_ms": {"median": 10}, "error_rate": {"median": 0}}}
    ev = evaluate_step(step, _run(result=fake, provenance="DEMO_SAMPLE"))
    assert ev["status"] != "verified"


def test_progress_unlocks_and_persists(tmp_path):
    p = Progress(tmp_path / "progress.json")
    st = all_statuses(MISSIONS, p, CAPS_CPU)
    assert st["m01-meet-your-machine"]["state"] == "available" and st["m02-find-your-model"]["state"] == "locked"
    p.record_evaluation("m01-meet-your-machine", "s1-scan", {"status": "verified", "checks": [], "run_id": "r"}, _run())
    p.record_quiz("m01-meet-your-machine", "s2-vram-check", True)
    st = all_statuses(MISSIONS, Progress(tmp_path / "progress.json"), CAPS_CPU)  # reload from disk
    assert st["m01-meet-your-machine"]["state"] == "complete" and st["m02-find-your-model"]["state"] == "available"


def test_verified_step_is_sticky(tmp_path):
    p = Progress(tmp_path / "progress.json")
    p.record_evaluation("m01-meet-your-machine", "s1-scan", {"status": "verified", "checks": [], "run_id": "a"}, _run())
    p.record_evaluation("m01-meet-your-machine", "s1-scan", {"status": "failed", "checks": [], "run_id": "b"}, _run("failed"))
    assert p.data["missions"]["m01-meet-your-machine"]["steps"]["s1-scan"]["evaluation"]["status"] == "verified"


def test_optional_gpu_steps_do_not_block_cpu_users(tmp_path):
    m04 = next(m for m in MISSIONS if m.number == 4)
    opt = [s for s in m04.steps if s.optional]
    assert opt and all(s.requires_capabilities for s in opt)


def test_hints_lower_mastery(tmp_path):
    p = Progress(tmp_path / "progress.json")
    p.use_hint("m01-meet-your-machine", "s2-vram-check")
    st = all_statuses(MISSIONS, p, CAPS_CPU)["m01-meet-your-machine"]
    assert st["hints_used"] == 1 and st["mastery"] == "none"


def test_registry_urls_are_https_and_verified_or_flagged():
    for r in registry.load():
        assert r["url"].startswith("https://")
        assert r["verification"]["method"] in ("fetched", "not_fetched")
