import json

import pytest

from inference_lab.local_model import inspect_local, list_local_models

pytestmark = pytest.mark.inference


def test_inspect_tiny_model(with_tiny_model):
    info = inspect_local("lab/tiny-random")
    s = info["summary"] if "summary" in info else info
    assert s["parameters"] == 891_648  # counted from the safetensors header, not guessed
    assert s["has_safetensors"] and s["has_tokenizer"] and s["source"] == "local_files"
    assert "lab/tiny-random" in list_local_models()


def test_missing_model():
    with pytest.raises(FileNotFoundError):
        inspect_local("org/not-here")


def test_remote_code_model_is_refused(with_tiny_model):
    from inference_lab.inference import model_dir_for, resolve_local_model
    d = model_dir_for("evil/remote")
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps({"auto_map": {"AutoModelForCausalLM": "modeling.Evil"}}))
    with pytest.raises(PermissionError):
        resolve_local_model("evil/remote")
