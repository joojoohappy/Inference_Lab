"""Run deadlines, cancellation and the concurrent-run cap."""
import threading
import time

import pytest

from inference_lab.actions import ACTIONS, ActionSpec, NoParams


def _wait(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def slow_action(monkeypatch):
    """A test-only action that waits until it is told to stop (or released)."""
    release = threading.Event()
    seen_stop = threading.Event()

    def handler(ctx, p):
        while not release.wait(0.02):
            if ctx.cancelled():
                seen_stop.set()
                return {"late": True}
        return {"done": True}

    def make(timeout_s):
        spec = ActionSpec("test.slow", NoParams, handler, lambda p: "test", [("inference_lab/actions.py", "Lab")],
                          [], timeout_s=timeout_s)
        monkeypatch.setitem(ACTIONS, "test.slow", spec)
        return spec

    yield make, release, seen_stop
    release.set()


def test_deadline_stops_the_run_and_discards_late_results(lab, slow_action):
    make, release, seen_stop = slow_action
    make(0.2)
    run = lab.submit("test.slow", {})
    assert _wait(lambda: run.status == "failed")
    assert run.error["code"] == "timeout" and run.provenance == "FAILED"
    assert seen_stop.wait(2), "the handler should see the stop flag"
    assert _wait(lambda: any("discarded" in l["msg"] for l in run.logs))
    assert run.result is None and run.status == "failed"


def test_cancel_marks_the_run_and_signals_the_worker(lab, slow_action):
    make, release, seen_stop = slow_action
    make(60)
    run = lab.submit("test.slow", {})
    assert run.status == "running"
    lab.cancel(run.id)
    assert run.status == "failed" and run.error["code"] == "cancelled"
    assert seen_stop.wait(2)


def test_cancel_of_a_finished_run_changes_nothing(lab, slow_action):
    make, release, _ = slow_action
    make(60)
    release.set()
    run = lab.submit("test.slow", {}, wait=True)
    assert run.status == "succeeded"
    lab.cancel(run.id)
    assert run.status == "succeeded" and run.result == {"done": True}


def test_concurrent_run_cap(lab, slow_action, monkeypatch):
    monkeypatch.setenv("INFERENCE_LAB_MAX_CONCURRENT_RUNS", "1")
    make, release, _ = slow_action
    make(60)
    first = lab.submit("test.slow", {})
    second = lab.submit("test.slow", {})
    assert first.status == "running"
    assert second.status == "not_run" and second.error["code"] == "too_many_runs"
    release.set()
    assert _wait(lambda: first.status == "succeeded")
    assert _wait(lambda: lab.submit("test.slow", {}).status in ("running", "succeeded"))


def test_cancel_endpoint(lab, slow_action):
    from fastapi.testclient import TestClient

    from inference_lab.api import create_app

    make, _, seen_stop = slow_action
    make(60)
    client = TestClient(create_app(lab))
    run = client.post("/api/runs", json={"action": "test.slow"}).json()
    out = client.post(f"/api/runs/{run['id']}/cancel").json()
    assert out["status"] == "failed" and out["error"]["code"] == "cancelled"
    assert client.post("/api/runs/run-nope/cancel").status_code == 404
    assert client.get("/api/errors/cancelled").json()["what"]


def test_ui_refuses_a_public_bind_without_opt_in(monkeypatch, capsys):
    from inference_lab import cli

    started = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: started.append(k))
    monkeypatch.delenv("INFERENCE_LAB_ALLOW_REMOTE", raising=False)
    assert cli.main(["ui", "--host", "0.0.0.0"]) == 2
    assert not started and "no authentication" in capsys.readouterr().err
    assert cli.main(["ui", "--host", "0.0.0.0", "--allow-remote"]) == 0 and started
    monkeypatch.setenv("INFERENCE_LAB_ALLOW_REMOTE", "1")
    assert cli.main(["ui", "--host", "0.0.0.0"]) == 0
