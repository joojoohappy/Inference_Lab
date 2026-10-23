"""GPU paths. These need an NVIDIA GPU (+ Docker for vLLM). Without one they are SKIPPED and reported NOT RUN."""
import shutil

import pytest

from inference_lab import hardware

HAS_GPU = bool(shutil.which("nvidia-smi")) and bool(hardware.probe_gpu().data.get("gpus"))
pytestmark = [pytest.mark.gpu, pytest.mark.skipif(not HAS_GPU, reason="NOT RUN: no NVIDIA GPU on this machine")]


def test_gpu_detected_with_vram():
    g = hardware.probe_gpu().data["gpus"][0]
    assert g["vram_total_mb"] > 0 and g["driver_version"]


def test_cuda_torch_inference(with_tiny_model):
    import torch
    assert torch.cuda.is_available()
    from inference_lab.inference import run_inference
    assert run_inference("lab/tiny-random", "hello", max_new_tokens=4)["device"] == "cuda"
