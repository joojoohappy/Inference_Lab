# Local test report — owner's laptop

_2026-10-24. Surface Laptop 7, Snapdragon X Plus X1P64100 (10 cores), Adreno X1-85 GPU, 16 GB RAM,
Windows 11 Pro 26200 (ARM64), Python 3.13.15 ARM64, torch 2.14.1+cpu, transformers 5.20.2, Node 24.19.
llama.cpp build b11827 (970b51ce7) from llmbench's `tools/` folder._

## What ran

| Check | Result |
|---|---|
| Backend tests (`pytest`) | **140 passed**, 2 skipped (NVIDIA GPU tests, NOT RUN) |
| — new llmbench bridge tests | 7 passed, including **live llama.cpp serve + benchmark on CPU and on the Adreno GPU** |
| Frontend unit tests (Vitest) | **15 passed** |
| i18n check | 427 keys in en and zh-TW, all consistent |
| Browser tests (Playwright, Microsoft Edge, real backend) | **8 passed**, Missions 01→07 completed in the browser |
| Hugging Face Hub (blocked in the cloud build) | live inspect OK; download blocked without approval; 260 MiB SmolLM2-135M-Instruct downloaded with approval |
| Real CPU inference with Transformers (SmolLM2-135M) | 24 tokens, TTFT 169 ms, TPOT 38.5 ms |
| vLLM | **NOT RUN, and cannot run on this machine**: vLLM needs an NVIDIA (CUDA) or AMD (ROCm) GPU. The lab reports `capability_missing vllm_docker` and executes nothing |
| Paid AI tutor | Not called (no paid usage) |

## Benchmark: Qwen3-4B-Instruct-2507 Q4_0, llama.cpp, via Inference Lab

Closed loop, concurrency 1, 64 output tokens, 4 requests × 2 trials, 1 warm-up. Medians across trials.

| Engine | TTFT p50 | TPOT p50 | Output tok/s | Errors |
|---|---|---|---|---|
| llama.cpp CPU | 78 ms | 29.3 ms | 33.0 | 0 |
| llama.cpp Adreno GPU (OpenCL, all layers offloaded) | 231 ms | 53.5 ms | 17.8 | 0 |

Prompt caching is off (`cache_prompt=false`, as in llmbench). A first run with caching left on gave
CPU 35.5 / Adreno 19.6 tok/s and TTFT 30 / 64 ms, because repeated prompts skipped prefill.

Cross-check against llmbench's own overnight run (128 in / 128 out, concurrency 1): CPU 30.5 tok/s,
Adreno 18.6 tok/s, TPOT 50.0 ms on Adreno. Inference Lab's numbers agree; on this laptop the Adreno
OpenCL backend decodes slower than the CPU. The prompts differ (Inference Lab uses a short fixed prompt),
so TTFT is not directly comparable with llmbench's.

## Changes made for this machine

* New `inference_lab/integrations/llmbench.py`: finds the sibling llmbench folder, its `llama-server`
  builds and GGUF models. Model references are `gguf:<name>` and cannot leave the models folder.
* New server kinds `llamacpp-cpu` and `llamacpp-adreno` (CLI, API, Experiment Arena), launched with the same
  flags as llmbench's `edge_*` experiments, bound to 127.0.0.1, gated by new `llamacpp_*` capabilities.
* Hardware scan gains an `llmbench` probe.
* Windows fixes: CLI no longer crashes printing tokens on a cp950 console; the i18n check and the Playwright
  config work on Windows paths.
