# Architecture audit

_Date: 2026-10-23. Scope: find the existing LLM inference benchmarking project to extend, and decide what to reuse._

## 1. What was searched

The brief asked to transform an existing LLM inference benchmarking project. The build environment could see the
following repositories on the requester's GitHub account (via the session's repository list):

| Repository | What it is | Inference benchmark? |
|---|---|---|
| `mosAIc` | Benchmarks a FastAPI recipe backend; its README states no AI model is measured | No |
| `Save_your_token` | Claude Code token-cost analyzer (`ccwhatif`); cloned and read in full | No |
| `AutoEarn001`, `look-up`, `MEmory`, `joo-universe`, `ks26-app` | Unrelated apps (names and descriptions) | No |

No local device folders were connected to the session, so nothing on the requester's own machine could be read.
**No repository containing an LLM inference benchmark was found.** The requester was asked in the thread which
repository was meant; no answer had arrived when the build finished.

## 2. Decision

Build Inference Lab as a standalone project with a clean seam for importing an existing benchmark later:

* The experiment record format (`inference_lab/experiments.py`, schema v1) is documented and checksummed.
  Results from any other tool can be brought in through `POST /api/experiments/import` or the Journal's
  _Import JSON_ button. Imported records are labelled `VERIFIED_IMPORTED`, never `LIVE_MEASURED`.
* The benchmark engine talks to any **OpenAI-compatible** `/v1/completions` endpoint on localhost
  (`inference_lab/bench/loadgen.py`), so an existing server or harness can be measured without code changes.
* Every allowlisted action declares the source files and tests it depends on (`ActionSpec.sources/tests`),
  so swapping in an existing implementation is a one-file change that the Code Explorer and tests follow.

## 3. Reused (third-party, not re-implemented)

| Need | Reused | Why |
|---|---|---|
| Model loading, tokenization, generation | Hugging Face Transformers 5.x, tokenizers, safetensors | Reference implementation; safetensors avoids pickle code execution |
| Hub metadata and downloads | `huggingface_hub` (`snapshot_download`), documented `GET /api/models/{id}` | Documented API, respects gated access |
| GPU serving | vLLM official container `vllm/vllm-openai` | Industry-standard engine with an OpenAI-compatible API |
| API server | FastAPI + Uvicorn + Pydantic | Input validation on every action parameter |
| UI | React 19, Vite, i18next/react-i18next, highlight.js | Mature i18n framework, real syntax highlighting |
| Tests | pytest, Vitest + Testing Library, Playwright | Unit, component, and real-browser coverage |

## 4. Environment facts that shaped the MVP

| Fact | Consequence |
|---|---|
| 4 CPU threads, 15 GB RAM, **no GPU** | Every core mission has a CPU path; GPU/vLLM steps are optional and recorded `NOT_RUN` |
| Docker client present, **no daemon** | vLLM path implemented and validated as argv, but never executed here |
| `huggingface.co` **blocked** by the network proxy | Hub inspection/download implemented against the documented API but returned `NOT_RUN` here; a locally built tiny model (`lab/tiny-random`) gives every learner a real, offline model |

## 5. Risks recorded during the audit

* Treating a missing repository as "nothing to preserve" could discard the requester's work. Mitigated by building
  the import seam above and asking in the thread.
* Benchmarks on a 4-thread shared VM are noisy. Mitigated by warm-up, multiple trials, min/max ranges, and an
  "overlap (may be noise)" flag in every comparison.
