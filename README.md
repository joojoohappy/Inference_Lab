# Inference Lab

**Learn it. Run it. Understand it. Improve it.**

[繁體中文說明](README.zh-TW.md)

Inference Lab is a local, interactive workbench for learning AI inference engineering. You run a real model on
your own machine, benchmark it with honest methodology, read the exact code that did it, compare one change at a
time, and defend a decision with evidence. Every number is labelled with where it came from; nothing is simulated.

![The Lab](docs/screenshots/en-lab.png)

## Demo video

[![Inference Lab demo video (3:33)](docs/media/demo-poster.jpg)]



https://github.com/user-attachments/assets/a956d596-b720-46dc-a088-afa59c20190b



A 3½-minute tour with bilingual captions: hardware scan, all seven missions run for real, Experiment Arena,
Model Garage, Code Explorer, Research Archive and the Engineering Journal, plus measured llama.cpp results from a
Snapdragon X Plus laptop (CPU 33.0 tok/s vs Adreno GPU 17.8 tok/s; vLLM shown as NOT RUN, no GPU).
The UI walkthrough was recorded in a CPU-only cloud sandbox, with waits for compute cut or sped up.

## Quick start (CPU, works offline)

Requirements: Python 3.10+ (tested 3.13), Node 20+ (tested 22) to build the UI.

```bash
git clone <this repo> inference-lab && cd inference-lab
python -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu    # or the CUDA build for your GPU
pip install -e ".[inference,dev]"
(cd frontend && npm ci && npm run build)
inference-lab ui            # → http://127.0.0.1:8765
```

The UI opens in **English**. Switch to 繁體中文 with the language switcher at the top right; your choice is
remembered on this computer and never changes your progress.

## What is inside

| Area | What you do there |
|---|---|
| **The Lab** | Scan your machine, see missions, skills and recent results |
| **Model Garage** | Inspect a Hugging Face model by ID or URL (metadata only), estimate memory, check compatibility, download only after approval, try inference |
| **Mission Control** | Seven missions, from "Meet Your Machine" to "Defend Your Decision" |
| **Code Explorer** | Read the real source that each step runs, with line ranges and four explanation levels |
| **Research Archive** | Primary sources (papers, docs) with verification notes; interactive KV-cache and latency/throughput visuals |
| **Experiment Arena** | Start a server, benchmark it, compare two runs, see evidence-based suggestions |
| **Engineering Journal** | Every experiment and run (including failures), notes, import/export, reports in en or zh-TW |

Modes: **Observe** (watch an approved workflow), **Guided** (you run each step with hints), **Expert** (all
parameters up front). All three use the same execution and validation engine.

## Provenance labels

| Label | Meaning |
|---|---|
| `LIVE_MEASURED` | Measured on this machine by the code in this repository |
| `IMPORTED` | Imported from a file whose schema is valid and whose checksums match; **origin not verified** |
| `DEMO_SAMPLE` | Synthetic teaching data; never evidence |
| `NOT_RUN` | Not executed (usually a missing capability such as a GPU) |
| `FAILED` | Executed and failed; kept and shown |

Reports only claim `LIVE_MEASURED` results. A matching checksum shows an imported file was not edited after
export; it does not show the numbers were ever measured, because anyone can write a record and compute its
checksum. Imported records therefore appear in their own labelled section of a report and are flagged in
comparisons. Re-run a benchmark on your own machine before you rely on it.

A benchmark request counts as successful only if it returns HTTP 200, streams generated text and ends with
`[DONE]`. Token counts come from the server's `usage`; if a server does not report usage, TPOT and tokens/s are
left empty instead of being estimated from chunk counts.

## Command line

The CLI uses the same actions as the UI:

```bash
inference-lab hardware
inference-lab prepare-tiny
inference-lab infer --prompt "The KV cache stores" --max-new-tokens 16
inference-lab bench --concurrency 1 --trials 3
inference-lab bench --concurrency 4 --trials 3
inference-lab experiments
inference-lab compare <baseline-id> <candidate-id>
inference-lab report <id> <id> --lang zh-TW
inference-lab inspect Qwen/Qwen2.5-0.5B-Instruct          # needs network access to huggingface.co
inference-lab download Qwen/Qwen2.5-0.5B-Instruct --approve
```

## GPU path (optional)

With an NVIDIA GPU, the NVIDIA Container Toolkit and Docker, Mission 04 can start vLLM
(`vllm/vllm-openai`, bound to 127.0.0.1). See `docker/vllm/docker-compose.yml`. This path was **not executed** in
the build environment (no GPU). Without a GPU those steps show as NOT RUN and never block your progress.

## llama.cpp via llmbench (CPU or Adreno GPU)

If the [llm-inference-bench](../llmbench/llm-inference-bench) project (llmbench) sits next to this repo, Inference Lab
reuses its llama.cpp builds (`tools/llama-cpu`, `tools/llama-adreno`) and GGUF models (`models/*.gguf`) without copying
or changing them. Set `INFERENCE_LAB_LLMBENCH_DIR` if it lives elsewhere. Models are referenced as `gguf:<file name>`.

```bash
inference-lab bench --kind llamacpp-adreno --model gguf:qwen3-4b-instruct-2507-Q4_0 --port 8870 --max-tokens 64
```

The Experiment Arena has the same two engines. Results from this path were measured on a Snapdragon X laptop; see
[docs/LOCAL_TEST_REPORT.md](docs/LOCAL_TEST_REPORT.md).

## Optional AI tutor

The tutor works without any paid API (curated explanations and docstrings). To add a model:

```bash
pip install -e ".[tutor]"
export INFERENCE_LAB_TUTOR=anthropic ANTHROPIC_API_KEY=...       # model: INFERENCE_LAB_TUTOR_MODEL (default claude-opus-5-5)
# or a local OpenAI-compatible server you run yourself:
export INFERENCE_LAB_TUTOR=local INFERENCE_LAB_TUTOR_URL=http://127.0.0.1:8000 INFERENCE_LAB_TUTOR_MODEL=<model>
```

The AI never decides completion, never gets a shell, and receives only redacted text.

## Deployment: single user, this machine only

Inference Lab is a local, single-user workbench. It has **no authentication, no per-user data and no job
quotas**: anyone who can reach the port can read your experiments, start heavy jobs and reset your progress.
The Host-header check blocks DNS-rebinding attacks from web pages, but it is not access control.

* It listens on `127.0.0.1` by default. `inference-lab ui` refuses any other address unless you pass
  `--allow-remote` (or set `INFERENCE_LAB_ALLOW_REMOTE=1`).
* With Docker, publish on loopback only: `docker run -p 127.0.0.1:8765:8765 ...`.
* Do not put it on a public network or behind a public reverse proxy. Hosting it for several people would
  first need authentication, per-user storage, job quotas and isolated workers.

Each action runs with a deadline. When it passes, or when you call `POST /api/runs/{id}/cancel`, the run is
marked failed and long actions (benchmarks, server start) stop at their next check. A single `generate` call or
a download already in progress cannot be interrupted and finishes in the background; its result is discarded.
At most `INFERENCE_LAB_MAX_CONCURRENT_RUNS` actions run at once.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `INFERENCE_LAB_HOME` | `~/.inference-lab` | Experiments, runs, models, reports, progress |
| `INFERENCE_LAB_HOST` / `INFERENCE_LAB_PORT` | `127.0.0.1` / `8765` | Where the UI listens |
| `INFERENCE_LAB_ALLOW_REMOTE` | unset | `1` allows a non-loopback host (no authentication; see above) |
| `INFERENCE_LAB_MAX_CONCURRENT_RUNS` | `4` | Actions allowed to run at the same time |
| `INFERENCE_LAB_MAX_DOWNLOAD_BYTES` | 2 GiB | Downloads above this are refused |
| `HF_ENDPOINT` | `https://huggingface.co` | Hub mirror |
| `HF_TOKEN` | unset | Your token for models you have been granted; never stored |
| `INFERENCE_LAB_VLLM_IMAGE` | `vllm/vllm-openai:latest` | vLLM container image |

## Tests

```bash
pytest                                   # backend: 162 tests; without a GPU or llmbench, 4 skip as NOT RUN
cd frontend && npm test                  # component and i18n tests
npm run i18n:check                       # en / zh-TW key parity and usage scan
npx playwright test                      # real browser: language, full mission journey, approvals, screenshots
```

GitHub Actions (`.github/workflows/ci.yml`) runs the backend tests, the frontend build, unit tests and i18n
check, the Playwright journey and a Docker image build on every push and pull request. GPU and llama.cpp tests
need hardware CI does not have; they are reported as NOT RUN there and covered by the dated manual report in
[docs/LOCAL_TEST_REPORT.md](docs/LOCAL_TEST_REPORT.md). Test counts in the dated reports reflect the code and
machine at that time.

## Documentation

`docs/ARCHITECTURE_AUDIT.md`, `docs/ARCHITECTURE.md`, `docs/MISSION_SCHEMA.md`, `docs/EXECUTION_AND_VALIDATION.md`,
`docs/SOURCE_EXPLORER.md`, `docs/EXPERIMENT_WORKFLOW.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/ROADMAP.md`,
`docs/IMPLEMENTATION_REPORT.md`.
