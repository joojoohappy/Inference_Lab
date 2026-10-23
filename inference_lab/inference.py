"""Basic local inference with Hugging Face Transformers.

Two model sources:
  * "lab/tiny-random": a tiny GPT-2-shaped model built *locally* with random weights and a
    tokenizer trained on a short built-in text. No download. It proves the whole pipeline
    (tokenize -> forward passes -> sample -> decode) runs on this machine. Its output is
    gibberish on purpose: weights are what make a model useful, and these are random.
  * A Hugging Face model that the user explicitly approved and downloaded into the lab's
    model folder. Loaded with local_files_only=True and trust_remote_code=False.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .config import load_settings
from .provenance import Provenance

TINY_MODEL_REF = "lab/tiny-random"

# A fixed corpus so the tokenizer (and therefore the tiny model) is identical on every machine.
TINY_CORPUS = [
    "Inference is the act of running a trained model to produce an output.",
    "A tokenizer turns text into token ids, and a model predicts the next token id.",
    "Latency is how long one request takes. Throughput is how much work finishes per second.",
    "The KV cache stores keys and values so earlier tokens are not recomputed.",
    "Time to first token measures how long a user waits before anything appears.",
    "Batching many requests together keeps the hardware busy and raises throughput.",
    "Measure, change one variable, measure again, and compare under the same conditions.",
    "GPU memory holds the weights, the KV cache, and temporary activations.",
] * 4

Log = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def model_dir_for(ref: str) -> Path:
    models = load_settings().models_dir
    if ref == TINY_MODEL_REF:
        return models / "lab__tiny-random"
    return models / ref.replace("/", "__")


def build_tiny_model(log: Log = _noop, force: bool = False) -> dict[str, Any]:
    """Create the offline teaching model. Deterministic: same seed, same corpus, same weights."""
    import torch
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
    from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast

    out = model_dir_for(TINY_MODEL_REF)
    if (out / "config.json").exists() and not force:
        log(f"tiny model already exists at {out}")
        return {"path": str(out), "created": False}
    out.mkdir(parents=True, exist_ok=True)

    log("training a byte-level BPE tokenizer on the built-in corpus (vocab_size=512)")
    tok = Tokenizer(models.BPE(unk_token=None))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(vocab_size=512, special_tokens=["<|endoftext|>"],
                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet(), show_progress=False)
    tok.train_from_iterator(TINY_CORPUS, trainer=trainer)
    fast = PreTrainedTokenizerFast(tokenizer_object=tok, bos_token="<|endoftext|>", eos_token="<|endoftext|>")
    fast.save_pretrained(out)

    log("initialising GPT2LMHeadModel(n_layer=4, n_head=4, n_embd=128) with torch.manual_seed(0)")
    torch.manual_seed(0)
    cfg = GPT2Config(vocab_size=len(fast), n_positions=256, n_embd=128, n_layer=4, n_head=4,
                     bos_token_id=fast.bos_token_id, eos_token_id=fast.eos_token_id)
    model = GPT2LMHeadModel(cfg)
    model.save_pretrained(out, safe_serialization=True)
    (out / "LAB_MODEL_CARD.md").write_text(
        "# lab/tiny-random\n\nRandomly initialised GPT-2-shaped model built locally by Inference Lab.\n"
        "Not trained. Outputs are meaningless by design. Use it to learn the pipeline, not to judge quality.\n",
        encoding="utf-8")
    n_params = sum(p.numel() for p in model.parameters())
    log(f"saved {n_params:,} parameters to {out}")
    return {"path": str(out), "created": True, "parameters": n_params}


def resolve_local_model(ref: str) -> Path:
    path = model_dir_for(ref)
    if not (path / "config.json").exists():
        raise FileNotFoundError(f"model {ref!r} is not available locally at {path}")
    cfg = json.loads((path / "config.json").read_text(encoding="utf-8"))
    if cfg.get("auto_map"):
        raise PermissionError("model requires trust_remote_code; Inference Lab does not run remote code")
    return path


class _TokenClock:
    """StoppingCriteria-compatible callable that timestamps every generated token."""

    def __init__(self) -> None:
        self.stamps: list[float] = []

    def __call__(self, input_ids, scores, **kwargs):  # noqa: ANN001 - transformers signature
        import torch

        self.stamps.append(time.perf_counter())
        return torch.zeros(input_ids.shape[0], dtype=torch.bool, device=input_ids.device)


def run_inference(ref: str, prompt: str, max_new_tokens: int = 24, seed: int = 0,
                  log: Log = _noop) -> dict[str, Any]:
    """Tokenize, generate greedily, decode. Timings are measured, not estimated."""
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteriaList

    if not prompt or len(prompt) > 4000:
        raise ValueError("prompt must be 1..4000 characters")
    max_new_tokens = max(1, min(int(max_new_tokens), 256))
    path = resolve_local_model(ref)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    t0 = time.perf_counter()
    log(f"AutoTokenizer.from_pretrained({path.name!r}, local_files_only=True)")
    tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
    log(f"AutoModelForCausalLM.from_pretrained({path.name!r}, local_files_only=True, trust_remote_code=False)")
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    model.to(device).eval()
    load_ms = (time.perf_counter() - t0) * 1000
    n_params = sum(p.numel() for p in model.parameters())
    log(f"loaded {n_params:,} parameters on {device} in {load_ms:.0f} ms")

    enc = tok(prompt, return_tensors="pt").to(device)
    ids = enc["input_ids"][0].tolist()
    tokens = tok.convert_ids_to_tokens(ids)
    log(f"prompt -> {len(ids)} tokens")

    torch.manual_seed(seed)
    clock = _TokenClock()
    t1 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                             stopping_criteria=StoppingCriteriaList([clock]),
                             pad_token_id=tok.eos_token_id)
    t2 = time.perf_counter()
    new_ids = out[0][len(ids):].tolist()
    text = tok.decode(new_ids, skip_special_tokens=True)
    n_new = len(new_ids)
    ttft = (clock.stamps[0] - t1) * 1000 if clock.stamps else None
    gaps = [b - a for a, b in zip(clock.stamps, clock.stamps[1:])]
    tpot = (sum(gaps) / len(gaps) * 1000) if gaps else None
    total_ms = (t2 - t1) * 1000
    log(f"generated {n_new} tokens in {total_ms:.0f} ms")
    return {
        "provenance": Provenance.LIVE_MEASURED.value,
        "model": ref,
        "model_path": str(path),
        "is_random_teaching_model": ref == TINY_MODEL_REF,
        "device": device,
        "dtype": str(next(model.parameters()).dtype).replace("torch.", ""),
        "parameters": n_params,
        "engine": {"name": "transformers", "version": transformers.__version__, "torch": torch.__version__},
        "input": {"prompt": prompt, "token_ids": ids, "tokens": tokens, "count": len(ids)},
        "output": {"text": text, "token_ids": new_ids, "tokens": tok.convert_ids_to_tokens(new_ids),
                   "count": n_new},
        "decoding": {"strategy": "greedy", "max_new_tokens": max_new_tokens, "seed": seed},
        "timing": {
            "load_ms": round(load_ms, 2),
            "ttft_ms": round(ttft, 2) if ttft is not None else None,
            "tpot_ms": round(tpot, 3) if tpot is not None else None,
            "generate_ms": round(total_ms, 2),
            "output_tokens_per_s": round(n_new / (total_ms / 1000), 2) if total_ms > 0 and n_new else None,
        },
    }


def download_model(model_id: str, revision: str | None, allow_patterns: list[str], log: Log = _noop,
                   cancel: threading.Event | None = None) -> dict[str, Any]:
    """Download approved files with huggingface_hub. Called only after explicit approval."""
    from huggingface_hub import snapshot_download

    dest = model_dir_for(model_id)
    dest.mkdir(parents=True, exist_ok=True)
    log(f"snapshot_download({model_id!r}, revision={revision!r}, allow_patterns={allow_patterns})")
    path = snapshot_download(repo_id=model_id, revision=revision, allow_patterns=allow_patterns,
                             local_dir=str(dest))
    size = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
    log(f"downloaded {size / 1024**2:.1f} MiB to {path}")
    meta = {"model_id": model_id, "revision": revision, "bytes": size, "downloaded_at": time.time()}
    (Path(path) / "LAB_DOWNLOAD.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"path": str(path), "bytes": size, "revision": revision}


def local_revision(ref: str) -> str | None:
    if ref == TINY_MODEL_REF:
        return "local-seed0-v1"
    meta = model_dir_for(ref) / "LAB_DOWNLOAD.json"
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8")).get("revision")
    return None


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
