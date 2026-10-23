# Inference Lab — implementation report

_2026-10-23. Built and verified in a cloud sandbox: 4 vCPU, 15 GB RAM, no GPU, no Docker daemon, Hugging Face Hub blocked._
_All work is in local git commits on `main` in the project folder. Nothing was pushed, deployed, downloaded from the Hub, or paid for._

## 1. What was built

* **Backend** (Python, FastAPI, ~3,700 lines): hardware scan with capability detection; Hub model inspector with
  ID/URL validation, memory estimates and compatibility verdicts; safe downloads (safetensors only, approval required,
  remote code / gated / pickle refused); real CPU inference with measured TTFT/TPOT; an offline tiny teaching model;
  a mini OpenAI-compatible server and a vLLM launcher; a closed-loop benchmark engine with warm-up, trials,
  percentiles, throughput and resource sampling; append-only checksummed experiment records with verified import;
  comparability checks; evidence-based suggestions; bilingual Markdown reports that only claim measured data.
* **Mission engine**: 7 data-driven missions (21 steps + 2 challenges) in YAML, validated by a schema, with
  deterministic checks, progressive hints, quizzes, prerequisites, capability gating and mastery levels.
* **Frontend** (React + TypeScript, ~2,400 lines): seven areas (The Lab, Model Garage, Mission Control, Code
  Explorer, Research Archive, Experiment Arena, Engineering Journal), Observe / Guided / Expert modes, approval
  dialogs, "Is it stuck?" diagnosis, View Source with line ranges and four explanation levels, interactive
  KV-cache and latency/throughput visuals, comparison charts, report generation.
* **Localization**: English default for every new user (browser language is never used), manual switcher,
  persisted choice, 425 UI keys and all backend strings in en and zh-TW, mission and research content in both,
  automated parity checks.
* **CLI** with the same actions: `hardware`, `inspect`, `inspect-local`, `prepare-tiny`, `download --approve`,
  `infer`, `bench`, `experiments`, `compare`, `report`, `ui`.
* **Docs**: README (en, zh-TW), architecture audit, architecture, mission schema, execution and validation,
  Source Explorer design, experiment workflow, known limitations, roadmap, this report. Docker compose for vLLM and an app Dockerfile.

## 2. What was reused

No existing inference-benchmark repository was found in the account's repositories (see ARCHITECTURE_AUDIT.md),
so no project code was reused. Third-party building blocks: Hugging Face Transformers / tokenizers / safetensors /
huggingface_hub, vLLM's official container (GPU path), FastAPI / Pydantic / Uvicorn, httpx, psutil, React,
i18next, highlight.js, Vite, pytest, Vitest, Playwright.

## 3. What was verified (actually run)

| Check | Result |
|---|---|
| Backend tests (`pytest`) | **133 passed**, 2 GPU tests skipped and reported NOT RUN |
| Includes | real tiny-model inference, real mini server + benchmark, approval blocking, NOT_RUN on missing capabilities, failure visibility, report provenance separation, source refs resolve to real files/symbols, mission schema in both languages, determinism, secret redaction, path traversal denial, Host guard, tutor cannot complete steps, no Simplified characters in zh-TW |
| Frontend unit tests (Vitest) | **15 passed**: English default even with a zh-TW browser, persisted switch, invalid stored value ignored, key parity, mode kept across language switch, provenance badges distinct |
| i18n check | 425 keys in both languages, 352 static usages, 29 dynamic key families complete |
| Browser tests (Playwright, real Chromium, real backend) | **8 passed**: default English, manual switch + persistence, **Missions 01→07 completed in the browser with real execution** (scan, local inspection, model build, inference, server, two benchmarks, comparison, report), Arena comparison with demo vs live labels, large benchmark blocked until approval (nothing ran on cancel), invalid model URL rejected, Journal shows all runs |
| Screenshots | 14 full-page screenshots, 7 areas × en / zh-TW, in `docs/screenshots/` |
| CLI workflow from a clean data dir | hardware → prepare-tiny → infer → bench c=1 → bench c=4 → compare → zh-TW report: all succeeded |

Example live result (tiny model, mini server, this VM): TTFT p50 22 ms at concurrency 1 vs 631 ms at concurrency 4;
output throughput 144 → lower at c=4. The comparison flagged exactly one changed variable (`workload.concurrency`)
and the suggestion engine identified queueing behind a serial server.

## 4. What remains untested

GPU inference and vLLM (no GPU); live Hub inspection/download (network blocked); the Anthropic and local AI tutor
providers (no key, no paid calls); building/running the Docker images (no daemon); integration with the
requester's original benchmark (not found). Details in KNOWN_LIMITATIONS.md.

## 5. How to launch

```bash
python -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[inference,dev]"
(cd frontend && npm ci && npm run build)
inference-lab ui        # http://127.0.0.1:8765
```

## 6. How to reproduce a real experiment

In the UI: The Lab → Scan my machine → Mission Control → Missions 01–07 (about 2 minutes of compute on a laptop CPU).
From a terminal: see EXPERIMENT_WORKFLOW.md (`prepare-tiny`, two `bench` runs at concurrency 1 and 4, `compare`, `report`).

## 7. Security limitations

* Local single-user tool: no authentication. Safety relies on binding to 127.0.0.1 plus a Host-header guard. Binding
  to another interface prints a warning and exposes the lab to that network.
* Actions are an allowlist of Python functions with strict parameter validation; there is no shell or generic Docker
  endpoint. The vLLM action does run `docker run` with a fixed argv after approval.
* Model safety: no `trust_remote_code`, no pickle weights, gated models not bypassed, download size cap (2 GiB default).
  A malicious safetensors file can still contain misleading weights; it cannot execute code through this loader.
* Secrets are read from environment variables only, never stored, and redacted from tutor prompts by pattern and by
  value. Redaction is best-effort for unknown secret formats.
* The Code Explorer is read-only and repository-scoped.

## 8. Next priorities

1. Connect the original benchmark project once its location is confirmed.
2. Run the GPU/vLLM path on real hardware and add a GPU CI job.
3. CPU batching mode and open-loop load to teach batching, not only queueing.
4. Quantization mission; SGLang and llama.cpp engines.
5. Move quiz answers server-side; add recorded-fixture tests for tutor providers.
