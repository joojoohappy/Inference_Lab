from inference_lab import hardware
from inference_lab.hardware import Probe, capabilities, parse_nvidia_smi


def test_parse_nvidia_smi():
    out = "0, NVIDIA GeForce RTX 4090, 24564, 1024, 550.54.14, 3\n1, NVIDIA A100-SXM4-80GB, 81920, 0, 550.54.14, [N/A]\ngarbage\n"
    g = parse_nvidia_smi(out)
    assert [x["name"] for x in g] == ["NVIDIA GeForce RTX 4090", "NVIDIA A100-SXM4-80GB"]
    assert g[0]["vram_total_mb"] == 24564 and g[1]["utilization_pct"] is None


def test_missing_tools_do_not_crash(monkeypatch):
    monkeypatch.setattr(hardware, "_run", lambda cmd, timeout=10.0: (127, f"{cmd[0]}: not found"))
    p = hardware.probe_gpu()
    assert p.status == "not_found" and p.data["gpus"] == []


def _probes(gpus=(), docker=False, torch=True):
    P = lambda name, data: Probe(name, "ok", "test", data=data)  # noqa: E731
    return {"gpu": P("gpu", {"gpus": list(gpus)}), "docker": P("docker", {"daemon_running": docker}),
            "python_ml": P("python_ml", {"torch": "2" if torch else None, "transformers": "5" if torch else None}),
            "hub": P("hub", {"reachable": False})}


def test_gpu_and_docker_enable_vllm_path():
    caps = capabilities(_probes(gpus=[{"name": "GPU"}], docker=True))
    assert caps["nvidia_gpu"] and caps["vllm_docker"]


def test_capabilities_unsupported_hardware():
    caps = capabilities(_probes())
    assert caps["cpu_inference"] and not caps["nvidia_gpu"] and not caps["vllm_docker"] and not caps["hub_access"]


def test_capabilities_without_ml_stack():
    assert capabilities(_probes(torch=False))["cpu_inference"] is False
