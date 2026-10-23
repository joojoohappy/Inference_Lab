import pytest
from pydantic import ValidationError

from tests.conftest import fake_scan
from inference_lab.actions import ACTIONS


def test_registry_is_an_allowlist():
    assert "shell" not in ACTIONS and "exec" not in ACTIONS
    from pathlib import Path

    from inference_lab.config import REPO_ROOT
    from inference_lab.sourcemap import safe_path, symbol_range
    for spec in ACTIONS.values():
        assert spec.sources, f"{spec.id} must point at the code it runs"
        for file, symbol in spec.sources:
            p = safe_path(file)
            if symbol:
                assert symbol_range(p, symbol), f"{spec.id}: {file}:{symbol} not found"
        for t in spec.tests:
            assert (Path(REPO_ROOT) / t).is_file(), f"{spec.id}: test file {t} missing"


def test_unknown_action_rejected(lab):
    with pytest.raises(KeyError):
        lab.submit("os.system", {"cmd": "rm -rf /"})


def test_extra_params_rejected(lab):
    with pytest.raises(ValidationError):
        lab.submit("bench.run", {"concurrency": 1, "cmd": "rm -rf /"})


def test_download_blocked_without_approval(lab):
    run = lab.submit("model.download", {"model": "openai-community/gpt2"})
    assert run.status == "blocked" and run.error["code"] == "approval_required"
    assert run.result is None and run.started_at is None


def test_missing_capability_is_not_run_not_failed(lab):
    run = lab.submit("hub.inspect", {"model": "openai-community/gpt2"})
    assert run.status == "not_run" and run.provenance == "NOT_RUN"
    run = lab.submit("server.start", {"model": "Qwen/Qwen2.5-0.5B-Instruct", "kind": "vllm"}, approve=True)
    assert run.status == "not_run" and "vllm_docker" in run.error["detail"]


def test_large_benchmark_needs_approval(lab):
    run = lab.submit("bench.run", {"num_requests": 500, "max_tokens": 512})
    assert run.status == "blocked"


def test_bench_without_server_fails_visibly(lab):
    run = lab.submit("bench.run", {"num_requests": 2, "trials": 1}, wait=True)
    assert run.status == "failed" and run.error["code"] == "no_healthy_server"
    assert run.provenance == "FAILED"
    assert lab.store.list() == []  # a failure never becomes a fake measurement


def test_scan_is_live(lab):
    lab.last_scan = None
    run = lab.submit("hardware.scan", {}, wait=True)
    assert run.status == "succeeded" and run.provenance == "LIVE_MEASURED"
    assert "capabilities" in run.result


def test_bad_model_id_rejected_before_execution(lab):
    lab.last_scan = fake_scan(hub_access=True)
    with pytest.raises(ValidationError):
        lab.submit("hub.inspect", {"model": "../../etc/passwd"})
