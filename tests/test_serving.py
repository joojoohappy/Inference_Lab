"""Starts the real mini server on the tiny model and benchmarks it. CPU only; ~20 s."""
import pytest

from inference_lab.serving.manager import mini_argv, vllm_argv

pytestmark = pytest.mark.inference


def test_argv_has_no_shell_and_binds_localhost():
    argv = mini_argv("lab/tiny-random", 8800)
    assert isinstance(argv, list) and "127.0.0.1" in argv
    v = vllm_argv("Qwen/Qwen2.5-0.5B-Instruct", 8000)
    assert "127.0.0.1:8000:8000" in v and "--trust-remote-code" not in v
    with pytest.raises(ValueError):
        vllm_argv("bad id; rm -rf /", 8000)


def test_serve_and_benchmark_end_to_end(lab, with_tiny_model):
    start = lab.submit("server.start", {"model": "lab/tiny-random", "kind": "mini", "port": 8851}, wait=True)
    assert start.status == "succeeded", start.error
    try:
        h = lab.submit("server.health", {}, wait=True)
        assert h.result["healthy"]
        b = lab.submit("bench.run", {"concurrency": 2, "max_tokens": 8, "num_requests": 4, "warmup_requests": 1,
                                     "trials": 2}, wait=True)
        assert b.status == "succeeded", b.error
        rec = lab.store.get(b.experiment_id)
        assert rec["provenance"] == "LIVE_MEASURED" and rec["engine"]["name"] == "inference-lab-mini"
        agg = rec["result"]["aggregate"]
        assert agg["ttft_p50_ms"]["median"] > 0 and agg["error_rate"]["median"] == 0
        assert len(rec["result"]["trials"]) == 2 and rec["result"]["raw_samples"]
    finally:
        lab.submit("server.stop", {}, wait=True)
