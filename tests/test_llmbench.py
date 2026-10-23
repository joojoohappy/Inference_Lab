"""The llmbench bridge: llama.cpp (CPU / Adreno GPU) servers using llmbench's binaries and GGUF files.

Unit tests use a fake llmbench folder. The live tests start the real llama-server from the real
llmbench folder and are SKIPPED (reported NOT RUN) when it is not on this machine.
"""
import sys

import pytest

from inference_lab.integrations import llmbench
from inference_lab.serving.manager import llamacpp_argv

EXE = "llama-server.exe" if sys.platform == "win32" else "llama-server"


@pytest.fixture
def fake_llmbench(tmp_path, monkeypatch):
    root = tmp_path / "llm-inference-bench"
    for b in ("llama-cpu", "llama-adreno"):
        (root / "tools" / b).mkdir(parents=True)
        (root / "tools" / b / EXE).write_bytes(b"")
    (root / "models").mkdir()
    (root / "models" / "tiny-Q4_0.gguf").write_bytes(b"GGUF")
    monkeypatch.setenv("INFERENCE_LAB_LLMBENCH_DIR", str(root))
    return root


def test_probe_finds_binaries_and_models(fake_llmbench):
    info = llmbench.probe()
    assert info["root"] == str(fake_llmbench.resolve())
    assert info["llama_server_cpu"] and info["llama_server_adreno"]
    assert [m["ref"] for m in info["models"]] == ["gguf:tiny-Q4_0"]


def test_argv_localhost_and_gpu_offload(fake_llmbench):
    cpu = llamacpp_argv("gguf:tiny-Q4_0", 8080, "cpu")
    gpu = llamacpp_argv("gguf:tiny-Q4_0", 8080, "adreno")
    assert cpu[0].endswith(EXE) and "llama-cpu" in cpu[0] and "llama-adreno" in gpu[0]
    assert cpu[cpu.index("--host") + 1] == "127.0.0.1"
    assert cpu[cpu.index("-ngl") + 1] == "0" and gpu[gpu.index("-ngl") + 1] == "99"


def test_model_refs_cannot_escape_models_folder(fake_llmbench):
    for bad in ("gguf:../secret", "gguf:a/b", "tiny-Q4_0", "gguf:"):
        with pytest.raises(ValueError):
            llmbench.resolve_model(bad)
    with pytest.raises(FileNotFoundError):
        llmbench.resolve_model("gguf:missing")
    with pytest.raises(ValueError):
        llamacpp_argv("gguf:tiny-Q4_0", 8080, "cuda")


def test_capability_gating_reports_not_run(lab, fake_llmbench):
    r = lab.submit("server.start", {"model": "gguf:tiny-Q4_0", "kind": "llamacpp-adreno", "port": 8090}, wait=True)
    assert r.status == "not_run" or (r.error and "capability_missing" in r.error.get("code", ""))


def test_not_found_without_llmbench(tmp_path, monkeypatch):
    monkeypatch.setenv("INFERENCE_LAB_LLMBENCH_DIR", str(tmp_path / "nope"))
    assert llmbench.probe()["root"] is None


# --------------------------------------------------------------------------- live, real hardware

REAL = llmbench.find_root()
REAL_MODELS = [m["ref"] for m in llmbench.list_models(REAL)] if REAL else []
LIVE_MODEL = next((m for m in REAL_MODELS if m.endswith("Q4_0")), REAL_MODELS[0] if REAL_MODELS else None)


@pytest.mark.llamacpp
@pytest.mark.parametrize("backend", ["cpu", "adreno"])
def test_live_llamacpp_serve_and_benchmark(lab, backend):
    if not REAL or not LIVE_MODEL or not llmbench.server_binary(backend, REAL):
        pytest.skip(f"NOT RUN: llmbench llama-server ({backend}) or GGUF models not on this machine")
    from tests.conftest import fake_scan

    lab.last_scan = fake_scan(llamacpp_cpu=True, llamacpp_adreno=True)
    kind = f"llamacpp-{backend}"
    start = lab.submit("server.start", {"model": LIVE_MODEL, "kind": kind, "port": 8861}, wait=True)
    assert start.status == "succeeded", start.error
    try:
        assert start.result["version"]["engine"] == "llama.cpp"
        b = lab.submit("bench.run", {"concurrency": 2, "max_tokens": 16, "num_requests": 4, "warmup_requests": 1,
                                     "trials": 1, "timeout_s": 300}, wait=True)
        assert b.status == "succeeded", b.error
        rec = lab.store.get(b.experiment_id)
        assert rec["provenance"] == "LIVE_MEASURED"
        assert rec["engine"]["name"] == {"cpu": "llama.cpp-cpu", "adreno": "llama.cpp-adreno-opencl"}[backend]
        agg = rec["result"]["aggregate"]
        assert agg["ttft_p50_ms"]["median"] > 0 and agg["error_rate"]["median"] == 0
    finally:
        lab.submit("server.stop", {}, wait=True)
