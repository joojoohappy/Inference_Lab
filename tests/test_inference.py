import pytest

from inference_lab.inference import TINY_MODEL_REF, run_inference

pytestmark = pytest.mark.inference


def test_real_inference_is_measured_and_deterministic(with_tiny_model):
    a = run_inference(TINY_MODEL_REF, "The KV cache stores", max_new_tokens=8)
    b = run_inference(TINY_MODEL_REF, "The KV cache stores", max_new_tokens=8)
    assert a["provenance"] == "LIVE_MEASURED" and a["is_random_teaching_model"]
    assert a["output"]["count"] == 8 and a["input"]["count"] > 0
    assert a["timing"]["ttft_ms"] > 0 and a["timing"]["tpot_ms"] > 0
    assert a["output"]["token_ids"] == b["output"]["token_ids"]  # greedy decoding is reproducible


def test_input_limits(with_tiny_model):
    with pytest.raises(ValueError):
        run_inference(TINY_MODEL_REF, "", max_new_tokens=4)
    with pytest.raises(ValueError):
        run_inference(TINY_MODEL_REF, "x" * 5000, max_new_tokens=4)
