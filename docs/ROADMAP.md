# Roadmap

Priorities, most valuable first.

1. **Integrate the requester's existing benchmark project** once its location is known: add it as an engine or an
   importer behind the existing record schema, and point its actions' `sources` at its code.
2. **Validate the GPU path on real hardware**: run Missions 03 s4 and 04 s4 with vLLM on an NVIDIA GPU, adjust the
   container argv if needed, and turn the skipped GPU tests into CI on a GPU runner.
3. **Batching on CPU**: add a mini-server mode with simple static batching so learners can see batching help, not only queueing.
4. **Open-loop load** (Poisson arrivals) and a concurrency/rate sweep action that produces one record per point.
5. **More engines**: SGLang and llama.cpp (GGUF) servers behind the same OpenAI-compatible benchmark client.
6. **Quantization mission**: compare bf16 vs int8/4-bit on the same model with quality checks, not only speed.
7. ~~**Server-side quiz answers**~~ (done: the browser gets options without the answer index).
8. **Tutor provider tests** with a recorded fixture, plus an opt-in live smoke test.
9. **Packaging**: publish a wheel that bundles the built UI; one-command install.
10. More languages, contributed through the same locale files and parity checks.

## From the October 2026 source review

These came out of an external review; the cheap parts are done (see `docs/KNOWN_LIMITATIONS.md`).

* **Killable workers**: run heavy actions (generate, download, server start) in worker processes so a deadline
  or cancel can terminate them, with a queue instead of the current refuse-when-busy cap.
* **Evidence-grade imports**: signed records (or a raw-output bundle plus source identity) so an import can be
  more than "schema and checksum consistent".
* **Fuller environment fingerprint**: container image digest, model weight hash (including GGUF files), every
  server flag, input token length, background load and GPU clocks, so comparability is not only field-level.
* **Statistics**: confidence intervals across trials and a steady-state check, instead of min/max overlap alone.
* **Learning outcomes**: separate "workflow complete", "solved a new problem without hints" and "explained the
  result", and run a small study with target learners.
