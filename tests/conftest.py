from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def lab_home(tmp_path, monkeypatch):
    """Every test gets its own throwaway data directory. Nothing touches ~/.inference-lab."""
    monkeypatch.setenv("INFERENCE_LAB_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("INFERENCE_LAB_TUTOR", raising=False)
    return tmp_path / "home"


def fake_scan(**caps: bool) -> dict:
    base = {"cpu_inference": True, "nvidia_gpu": False, "cuda_torch": False, "docker": False,
            "vllm_docker": False, "vllm_python": False, "hub_access": False,
            "llamacpp_cpu": False, "llamacpp_adreno": False}
    base.update(caps)
    return {
        "summary": {"cpu_model": "Test CPU", "logical_cores": 4, "ram_total_gb": 16.0, "vram_total_gb": 0},
        "probes": {"gpu": {"data": {"gpus": []}}, "docker": {"data": {}}},
        "capabilities": base,
    }


@pytest.fixture
def lab():
    from inference_lab.actions import Lab
    from inference_lab.experiments import ExperimentStore

    lb = Lab(ExperimentStore())
    lb.last_scan = fake_scan()
    yield lb
    lb.servers.stop()


@pytest.fixture(scope="session")
def tiny_model_home(tmp_path_factory):
    """Build the tiny teaching model once per session (real CPU work, a few seconds)."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    home = tmp_path_factory.mktemp("tinyhome")
    old = os.environ.get("INFERENCE_LAB_HOME")
    os.environ["INFERENCE_LAB_HOME"] = str(home)
    try:
        from inference_lab.inference import build_tiny_model
        build_tiny_model()
    finally:
        if old is None:
            os.environ.pop("INFERENCE_LAB_HOME", None)
        else:
            os.environ["INFERENCE_LAB_HOME"] = old
    return home


@pytest.fixture
def with_tiny_model(tiny_model_home, lab_home):
    shutil.copytree(Path(tiny_model_home) / "models", Path(lab_home) / "models", dirs_exist_ok=True)
    return lab_home
