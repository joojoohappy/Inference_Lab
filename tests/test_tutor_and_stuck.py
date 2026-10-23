import time

from inference_lab.stuck import diagnose, error_help
from inference_lab.tutor import tutor


def test_explain_concept_levels_and_languages():
    for lvl in ("simple", "logic", "design", "tradeoffs"):
        en = tutor.explain_concept("kv-cache", lvl, "en")
        zh = tutor.explain_concept("kv-cache", lvl, "zh-TW")
        assert en["source"] == "curated" and en["text"] and zh["text"] and en["text"] != zh["text"]


def test_ask_without_provider_is_curated_and_free():
    r = tutor.ask("what is TTFT?", {}, "en")
    assert r["source"] == "curated" and r["provider"] is None and r["matches"]


def test_explain_code_curated_or_docstring():
    r = tutor.explain_code("inference_lab/bench/metrics.py", "percentile", "simple", "en")
    assert r["source"] in ("curated", "source") and r["range"]


def test_stuck_detection_states():
    now = time.time()
    run = {"status": "running", "started_at": now - 5, "heartbeat_at": now - 1, "timeout_s": 600, "progress": 0.5,
           "progress_samples": [[now - 4, 0.2], [now - 1, 0.5]], "logs": []}
    assert diagnose(run, "en", now)["state"] == "working"
    stalled = {**run, "started_at": now - 400, "heartbeat_at": now - 300, "progress_samples": [[now - 390, 0.1]]}
    assert diagnose(stalled, "en", now)["state"] != "working"
    over = {**run, "started_at": now - 700}
    assert diagnose(over, "en", now)["state"] == "over_budget"
    failed = {"status": "failed", "error": {"code": "no_healthy_server"}, "logs": [{"msg": "x"}]}
    d = diagnose(failed, "zh-TW", now)
    assert d["state"] == "failed" and d["next"]


def test_error_help_known_and_unknown():
    assert error_help("no_healthy_server", "en")["next"]
    assert error_help("totally_unknown_code", "en")["what"]
