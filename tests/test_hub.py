import pytest

from inference_lab.hub import InvalidModelId, download_plan, normalize_model_ref, summarize


@pytest.mark.parametrize("ref,expected", [
    ("Qwen/Qwen2.5-0.5B-Instruct", "Qwen/Qwen2.5-0.5B-Instruct"),
    ("gpt2", "gpt2"),
    ("https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct", "HuggingFaceTB/SmolLM2-135M-Instruct"),
    ("https://huggingface.co/openai-community/gpt2/tree/main", "openai-community/gpt2"),
    ("  https://hf.co/Qwen/Qwen2.5-0.5B  ", "Qwen/Qwen2.5-0.5B"),
])
def test_valid_refs(ref, expected):
    assert normalize_model_ref(ref) == expected


@pytest.mark.parametrize("ref", [
    "", "x" * 300, "../../etc/passwd", "org/../model", "a--b/c", "http://huggingface.co/gpt2",
    "https://evil.example.com/org/model", "https://huggingface.co/datasets/org/data",
    "https://huggingface.co/spaces/org/app", "https://user@huggingface.co/org/model",
    "https://huggingface.co:8443/org/model", "org/model; rm -rf /", "org/model name",
])
def test_invalid_refs(ref):
    with pytest.raises(InvalidModelId):
        normalize_model_ref(ref)


def _info(**kw):
    base = {"id": "org/m", "sha": "abc", "library_name": "transformers", "tags": ["license:apache-2.0"],
            "siblings": [{"rfilename": "model.safetensors", "size": 1000}, {"rfilename": "config.json", "size": 10},
                         {"rfilename": "tokenizer.json", "size": 50}, {"rfilename": "README.md", "size": 5}],
            "safetensors": {"total": 135_000_000, "parameters": {"BF16": 135_000_000}}}
    base.update(kw)
    return base


def test_summarize_fields():
    s = summarize(_info(), {"architectures": ["LlamaForCausalLM"], "num_hidden_layers": 30}, {"chat_template": "x"})
    assert s["parameters"] == 135_000_000
    assert s["license"] == "apache-2.0"
    assert s["has_safetensors"] and not s["pickle_only"]
    assert s["has_chat_template"] and s["has_tokenizer"]
    assert s["download_bytes"] == 1060  # README excluded by the download patterns
    assert download_plan(s)["allowed"]


def test_remote_code_and_gated_and_pickle_are_refused():
    rc = summarize(_info(), {"auto_map": {"AutoModel": "x.Model"}}, None)
    assert rc["needs_remote_code"] and download_plan(rc) == {"allowed": False, "reason": "requires_remote_code"}
    gated = summarize(_info(gated="manual"), {}, None)
    assert download_plan(gated)["reason"] == "gated_model_requires_accepting_terms_on_hub"
    pk = summarize(_info(siblings=[{"rfilename": "pytorch_model.bin", "size": 5}]), {}, None)
    assert pk["pickle_only"] and download_plan(pk)["reason"] == "pickle_weights_only"
