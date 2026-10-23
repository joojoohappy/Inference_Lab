# Architecture

Inference Lab is one local process (FastAPI on `127.0.0.1:8765`) that serves a React UI and runs a small,
fixed set of **allowlisted actions**. Everything the UI can do, the CLI can do too, through the same action code.

```
 Browser (React, i18next)                     Terminal
   │  /api/*  (JSON, Host-guarded)               │  inference-lab <cmd>
   ▼                                             ▼
 inference_lab/api.py ──────────────┐     inference_lab/cli.py
   │ missions, tutor, research,      │           │
   │ source explorer, experiments    ▼           ▼
   │                         inference_lab/actions.py  ← allowlist (ACTIONS), approval gate,
   │                                 │                    capability gate, Run lifecycle
   │        ┌─────────────┬──────────┼─────────────┬──────────────┬─────────────┐
   │        ▼             ▼          ▼             ▼              ▼             ▼
   │   hardware.py     hub.py   inference.py  serving/manager.py  bench/       reports.py
   │   (fixed probes)  (HF API) (Transformers) (mini | vLLM argv)  loadgen.py
   │                                              │                metrics.py
   │                                              ▼
   │                                   serving/mini_server.py  (OpenAI-compatible, 127.0.0.1)
   ▼
 missions/engine.py ── evaluates deterministic checks on each finished run → progress.json
 experiments.py     ── append-only, checksummed experiment records (~/.inference-lab/experiments)
```

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | Settings from env vars; data dir `~/.inference-lab` (override `INFERENCE_LAB_HOME`) |
| `provenance.py` | `LIVE_MEASURED`, `VERIFIED_IMPORTED`, `DEMO_SAMPLE`, `NOT_RUN`, `FAILED`; only the first two are claimable |
| `hardware.py` | Fixed, read-only probes (CPU, RAM, `nvidia-smi` query, `docker version`, Python imports, Hub reachability); derives capabilities |
| `memory.py` | Labelled memory **estimates** with explicit assumptions; compatibility verdicts |
| `hub.py` | Model ID/URL validation; Hub metadata via the documented model-info API; download plan (safetensors only; refuses remote code, gated, pickle-only) |
| `inference.py` | Builds the offline tiny teaching model; real greedy generation with measured TTFT/TPOT |
| `local_model.py` | Reads safetensors headers to count parameters exactly |
| `serving/` | Mini OpenAI-compatible server (CPU) and the vLLM container argv; process lifecycle |
| `bench/` | Closed-loop async load generator, resource sampler, percentile math, trial aggregation, comparison |
| `experiments.py` | Record schema v1, checksum, append-only store, verified import, comparability |
| `reports.py` | Markdown reports (en / zh-TW) that only claim measured records |
| `missions/` | Pydantic schema, YAML missions, check evaluation, persisted progress, mastery |
| `tutor/` | Curated concept/code explanations, optional AI provider, secret redaction, evidence-based suggestions |
| `research/` | Citation registry (primary sources only, verification recorded) |
| `sourcemap.py` | Read-only, repository-scoped source access for the Code Explorer |
| `stuck.py` | "Is it stuck?" diagnosis from heartbeats, progress samples and budgets |
| `i18n.py` + `locales/` | Backend strings (reports, errors, tutor, suggestions) in en and zh-TW |

## Frontend

`frontend/src` — `App.tsx` (shell, language and mode switchers), `pages/` (one per area), `components/`
(RunView, SourceViewer, Tutor, Charts, common badges), `lib/` (typed API client, app state, localized data helper),
`locales/` (425 keys each, generated from `scripts/locales_source.py`). Hash routing keeps the app a single static
bundle served by the backend.

## Data on disk (`~/.inference-lab`)

```
experiments/exp-*.json   append-only experiment records (notes are the only editable field)
runs/run-*.json          every run, including blocked, not_run and failed
models/<org>__<name>/    local models (tiny model built here; downloads only after approval)
reports/report-*.md      generated reports
progress.json            mission progress (language and mode are NOT stored here)
```

## Security model (summary)

* Bound to `127.0.0.1` by default; a Host-header guard rejects other hosts (DNS-rebinding protection).
* No shell and no generic Docker API: actions are Python functions with Pydantic-validated, `extra="forbid"` params;
  subprocesses use argv lists, never `shell=True`.
* Costly or networked actions (model download, vLLM, large benchmarks) return `blocked` until explicitly approved.
* `trust_remote_code` is never enabled; models with `auto_map` are refused; pickle-only weights are refused.
* Gated models are not bypassed: the plan refuses them and the user must accept terms on the Hub and use their own `HF_TOKEN`.
* Secrets: `HF_TOKEN`/API keys come from env only, are never written to records or logs, and are redacted from any tutor prompt.
* The Code Explorer serves repository files only, denies `.git`, `.venv`, `node_modules`, `.env*`, and is read-only.
