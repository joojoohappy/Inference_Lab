# Experiment workflow and methodology

## Reproduce a real experiment from a terminal (CPU, offline)

```bash
python -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # or your CUDA build
pip install -e ".[inference,dev]"

inference-lab hardware                      # what is this machine?
inference-lab prepare-tiny                  # builds lab/tiny-random locally (no network)
inference-lab infer --prompt "The KV cache stores" --max-new-tokens 16
inference-lab bench --concurrency 1 --max-tokens 16 --num-requests 8 --warmup 1 --trials 3
inference-lab bench --concurrency 4 --max-tokens 16 --num-requests 8 --warmup 1 --trials 3
inference-lab experiments                   # list record ids
inference-lab compare <baseline-id> <candidate-id>
inference-lab report <baseline-id> <candidate-id> --lang zh-TW
```

`bench` starts the mini server for the model, runs the load, and stops the server. Add `--json` for machine output.

## Methodology (what `bench/loadgen.py` does)

1. **Closed loop.** `concurrency` virtual clients; each sends its next request only when the previous one finished.
   This measures a server under a fixed number of in-flight requests (not an open arrival rate).
2. **Warm-up.** `warmup_requests` are sent first and discarded (model and allocator warm-up). If warm-up fails, the run aborts.
3. **Trials.** The whole load is repeated `trials` times. The aggregate is the **median across trials**, with min and max.
4. **Per request.** Streamed `/v1/completions` with `ignore_eos` so output length is fixed. TTFT = first streamed
   token; TPOT = (E2E − TTFT) / (tokens − 1); E2E = full response.
   A request **succeeds** only with HTTP 200, at least one generated text chunk and the closing `data: [DONE]`.
   A stream that ends early (`incomplete_stream`), carries no text (`empty_stream`), contains unparseable JSON
   (`malformed_chunk`) or an error object (`server_error_in_stream`) is a failure and counts toward the error rate.
   Output tokens come from the server's `usage.completion_tokens`. Chunks are not tokens (one chunk can carry
   several), so when a server reports no usage the trial records `token_count_source: "chunks"` and leaves TPOT
   and tokens/s empty.
5. **Percentiles.** Linear interpolation between closest ranks (same as NumPy's default).
6. **Throughput.** Successful requests and output tokens divided by the trial's wall time (tokens/s only when
   every successful request reported usage).
7. **Resources.** The server process's RSS and CPU% are sampled during the run (and GPU memory via `nvidia-smi` when present).
8. **Record.** Model id + revision, engine + version, hardware fingerprint, params, environment (Python, packages,
   git commit), raw per-request samples, checksum, and the learner's notes.

## Comparing

`experiments.comparability` lists every difference between two records (model, revision, hardware, engine, engine
version, each workload parameter). A comparison is "clean" only when exactly one thing changed and both sides are
measured here. Imported records (`imported_unverified`) and unknown model revisions or engine versions
(`unknown_model_revision`, `unknown_engine_version`) are warnings that make a comparison not clean: an unknown
value is a limitation, not a match. The check is field-level; it cannot see settings the record does not store
(server flags beyond those listed, background load, thermal state), so treat "comparable" as necessary, not
sufficient. Each metric shows % change, better/worse, and whether the trial ranges overlap ("may be noise").
Overlap is a noise hint, not a significance test.

## Example result from the build machine (4 vCPU, no GPU, tiny random model, mini server)

| | concurrency 1 | concurrency 4 |
|---|---|---|
| TTFT p50 (median of 3 trials) | 21.5 ms | 686.7 ms |
| Output throughput | 105.7 tok/s | 72.1 tok/s |

Provenance: LIVE_MEASURED in the browser test run on 2026-10-23. The mini server handles one request at a time,
so extra clients queue (TTFT rises) and throughput does not improve. These numbers describe this VM only.
