# Known limitations

## Not executed in the build environment

| Item | Why | Status |
|---|---|---|
| GPU inference, vLLM serving (Mission 03 s4, Mission 04 s4), GPU tests | No NVIDIA GPU (the cloud VM had none; the owner's Snapdragon X laptop has an Adreno GPU, which vLLM does not support) | Implemented; reported **NOT RUN**. vLLM argv and compose file are untested on real hardware; the image's CLI flags may need adjusting for a given vLLM release |
| Hugging Face Hub inspection and downloads | `huggingface.co` blocked by the build network | **Verified 2026-10-24** on the owner's laptop: live inspect, approval gate, and a 260 MiB download (SmolLM2-135M-Instruct) |
| AI tutor providers (Anthropic SDK, local OpenAI-compatible) | No API key and no `anthropic` package installed; no paid calls were made | Code written against the official SDK; never called. The curated tutor is fully tested |
| App Docker image (`Dockerfile`) | No Docker daemon | Not built |
| The requester's original benchmark repository | Found later at `llmbench/llm-inference-bench` | **Integrated**: llama.cpp CPU / Adreno engines reuse its binaries and GGUF models (`inference_lab/integrations/llmbench.py`) |
| Prompt caching on llama.cpp | llama-server caches prompts by default; llmbench disables it with `cache_prompt=false` | Not disabled here yet, so repeated identical prompts have a slightly lower TTFT than llmbench measures |

## Design limits

* The mini server serves one request at a time (a lock around `generate`). That is deliberate for teaching
  queueing, but it means CPU concurrency experiments always show queueing, not batching.
* The tiny teaching model has random weights. Its text is gibberish; its timings and tokens are real.
* Benchmarks on shared or virtual machines are noisy. Trials and min/max help but do not remove noise.
* Closed-loop load only (fixed in-flight requests). Open-loop arrival rates (Poisson) are not implemented.
* TTFT is measured at the client from the first streamed chunk, so it includes local HTTP overhead.
* Memory estimates are heuristics (weights + 20% + 0.5 GB + KV cache). Activations and engine pre-allocation are not modelled.
* Quiz answer indices are included in the mission data sent to the browser. Completion is still checked on the
  server, but a curious learner could read the answer. This is a learning tool, not an exam.
* Progress is per data directory and single-user. There is no authentication; the server relies on binding to
  127.0.0.1 and a Host-header guard.
* Only `en` and `zh-TW` are provided. Adding a language needs a new locale file in both `inference_lab/locales/`
  and `frontend/src/locales/` (the checks will list missing keys).
* Research registry: 14 of 15 records were fetched and checked on 2026-10-23. Collins et al. (1989) could not be
  fetched and is labelled "Not verified".
* The Arena's server panel runs a `server.health` action when opened, which adds a small entry to "All runs".
