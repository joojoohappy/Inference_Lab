from inference_lab.memory import assess_compatibility, estimate, kv_cache_bytes_per_token, weights_gb


def test_weights_math():
    assert abs(weights_gb(1_000_000_000, "bfloat16") - 2e9 / 1024**3) < 1e-9
    assert weights_gb(1_000_000_000, "float32") == 2 * weights_gb(1_000_000_000, "bfloat16")


def test_kv_cache_uses_kv_heads():
    cfg = {"num_hidden_layers": 24, "num_attention_heads": 14, "num_key_value_heads": 2, "hidden_size": 896}
    # 2 (K and V) * layers * kv_heads * head_dim * bytes
    assert kv_cache_bytes_per_token(cfg) == 2 * 24 * 2 * 64 * 2


def test_estimate_is_labelled_with_assumptions():
    e = estimate(500_000_000, {"num_hidden_layers": 24, "num_attention_heads": 14, "hidden_size": 896})
    assert e["kind"] == "ESTIMATE" and e["assumptions"] and e["total_gb"] > e["weights_gb"]
    assert estimate(None, None)["known"] is False


def test_compatibility_without_gpu_is_cpu_only():
    e = estimate(135_000_000, {})
    c = assess_compatibility(e, {"ram_total_gb": 16, "vram_total_gb": 0}, {"cpu_inference": True})
    assert c["verdict"] == "cpu_only" and c["paths"] == ["cpu_transformers"]


def test_compatibility_gpu_paths():
    e = estimate(135_000_000, {})
    c = assess_compatibility(e, {"ram_total_gb": 16, "vram_total_gb": 24},
                             {"cpu_inference": True, "nvidia_gpu": True, "vllm_docker": True})
    assert c["verdict"] == "fits_gpu" and "gpu_vllm" in c["paths"]


def test_too_large():
    e = estimate(70_000_000_000, {})
    c = assess_compatibility(e, {"ram_total_gb": 16, "vram_total_gb": 8}, {"cpu_inference": True, "nvidia_gpu": True})
    assert c["verdict"] == "too_large" and c["paths"] == []
