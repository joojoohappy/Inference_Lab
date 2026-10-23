# Execution and validation

## One engine, three modes

Observe, Guided and Expert all call the same endpoint (`POST /api/missions/{m}/steps/{s}/run`) and the same
`Lab.submit`. Modes only change presentation: Observe auto-runs steps that need no approval and skips the rest;
Guided shows what/why, hints and editable params; Expert shows every param and the command up front.
**There is no simulated path.** If an action cannot run, the run says so.

## Run lifecycle

```
submit ─► validate params (Pydantic, extra=forbid) ──► invalid → HTTP 422, nothing runs
       ─► approval needed and not approved ──────────► status=blocked, error=approval_required
       ─► capability missing ─────────────────────────► status=not_run, provenance=NOT_RUN
       ─► thread: running (heartbeat, progress, logs)
             ├─ handler returns ─► succeeded (+ provenance from the handler, e.g. LIVE_MEASURED)
             └─ handler raises  ─► failed, provenance=FAILED, error code + detail (+ trace for unexpected errors)
       ─► persist runs/<id>.json ─► on_finish hooks ─► mission check evaluation ─► progress.json
```

Every run, including blocked/not_run/failed, is listed in the Journal ("All runs").

## Approval gate

| Action | Needs approval when |
|---|---|
| `model.download` | always (network + disk); the modal shows the exact revision, files and expected bytes |
| `server.start` kind=vllm | always (GPU + container image pull) |
| `bench.run` | more than 500 requests, or requests × max_tokens > 50,000 |

`approve=true` is only sent from an explicit button press in the UI or `--approve` on the CLI.

## Validation

* Mission checks are evaluated on the persisted run (`missions/engine.py:evaluate_step`): pure function, same input → same output (tested).
* A verified step stays verified; later failed attempts are kept as attempts.
* Demo data cannot verify a benchmark step: checks require `run.provenance == LIVE_MEASURED`.
* Quizzes are checked on the server. (The answer index is present in the mission payload the UI receives;
  this is a learning tool, not an exam — see Known limitations.)

## Stuck detection

`stuck.py:diagnose` reads elapsed time vs. the action's budget, heartbeat age, progress samples, and (for server
starts) process liveness and `/health`. It answers "working", "slow but progressing", "possibly stalled",
"over budget", "process exited", or explains a failure with what/why/next in the learner's language.

## Measurement methodology

See `EXPERIMENT_WORKFLOW.md`.
