"""Inference Lab command line. Works without the UI; uses the same actions and records.

  inference-lab ui                         start the app on http://127.0.0.1:8765
  inference-lab hardware                   scan this machine
  inference-lab inspect <model-id|url>     Hub metadata + memory estimate + compatibility
  inference-lab inspect-local <model>      read a local model's files (no torch needed)
  inference-lab prepare-tiny               build the offline teaching model
  inference-lab download <model> --approve download safetensors weights (explicit approval)
  inference-lab infer --prompt "..."       real local inference
  inference-lab bench [--concurrency N]    start the mini server (unless --url) and benchmark it
  inference-lab experiments                list recorded experiments
  inference-lab compare <baseline> <cand>  compare two benchmark experiments
  inference-lab report <id>... [--lang]    write an engineering report
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Any

from .actions import Lab, Run


def _print_run(run: Run, as_json: bool) -> int:
    if as_json:
        print(json.dumps(asdict(run), indent=2, default=str))
    else:
        for line in run.logs:
            print(f"[{line['level']}] {line['msg']}")
        print(f"status: {run.status}  provenance: {run.provenance}"
              + (f"  experiment: {run.experiment_id}" if run.experiment_id else ""))
        if run.error:
            print(f"error: {run.error['code']} {run.error.get('detail', '')[:400]}")
    return 0 if run.status == "succeeded" else 1


def _summary(run: Run) -> None:
    r: Any = run.result
    if run.action == "hardware.scan" and r:
        print(json.dumps({"summary": r["summary"], "capabilities": r["capabilities"]}, indent=2))
    elif run.action == "inference.run" and r:
        print(f"prompt tokens: {r['input']['tokens']}")
        print(f"output: {r['output']['text']!r}")
        print(f"timing: {r['timing']}")
    elif run.action in ("hub.inspect", "model.inspect_local") and r:
        print(json.dumps({k: r.get(k) for k in ("summary", "memory_estimate", "compatibility", "download_plan")},
                         indent=2, default=str)[:6000])
    elif run.action == "bench.run" and r:
        print(json.dumps(r.get("aggregate"), indent=2))
    elif run.action == "experiment.compare" and r:
        print(json.dumps(r, indent=2, default=str))
    elif run.action == "report.generate" and r:
        print(r["markdown"])


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles (e.g. cp950) cannot print every token
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower().replace("-", "") != "utf8":
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="inference-lab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print the full run record as JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ui = sub.add_parser("ui")
    ui.add_argument("--host", default=None)
    ui.add_argument("--port", type=int, default=None)
    ui.add_argument("--allow-remote", action="store_true",
                    help="allow binding to a non-loopback address (no authentication: trusted single-user networks only)")
    sub.add_parser("hardware")
    p = sub.add_parser("inspect")
    p.add_argument("model")
    p = sub.add_parser("inspect-local")
    p.add_argument("model", nargs="?", default="lab/tiny-random")
    sub.add_parser("prepare-tiny")
    p = sub.add_parser("download")
    p.add_argument("model")
    p.add_argument("--revision")
    p.add_argument("--approve", action="store_true", help="required: confirms network + disk use")
    p = sub.add_parser("infer")
    p.add_argument("--model", default="lab/tiny-random")
    p.add_argument("--prompt", required=True)
    p.add_argument("--max-new-tokens", type=int, default=24)
    p = sub.add_parser("bench")
    p.add_argument("--model", default="lab/tiny-random")
    p.add_argument("--kind", choices=["mini", "vllm", "llamacpp-cpu", "llamacpp-adreno"], default="mini")
    p.add_argument("--port", type=int, default=8800)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--max-tokens", type=int, default=16)
    p.add_argument("--num-requests", type=int, default=8)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--hypothesis")
    p.add_argument("--approve", action="store_true")
    sub.add_parser("experiments")
    p = sub.add_parser("compare")
    p.add_argument("baseline")
    p.add_argument("candidate")
    p = sub.add_parser("report")
    p.add_argument("ids", nargs="+")
    p.add_argument("--lang", choices=["en", "zh-TW"], default="en")
    p.add_argument("--decision")
    a = ap.parse_args(argv)

    if a.cmd == "ui":
        import uvicorn

        from .api import create_app
        from .config import load_settings

        s = load_settings()
        host, port = a.host or s.host, a.port or s.port
        if host not in ("127.0.0.1", "localhost", "::1"):
            if not (a.allow_remote or s.allow_remote):
                print(f"refusing to bind to {host}: Inference Lab has no authentication, no per-user data and no job "
                      "quotas, so anyone who can reach it can read your experiments, start heavy jobs and reset "
                      "progress. It is a single-user tool for this machine. If you really mean it (e.g. inside a "
                      "container published only on 127.0.0.1), pass --allow-remote or set "
                      "INFERENCE_LAB_ALLOW_REMOTE=1.", file=sys.stderr)
                return 2
            print(f"warning: binding to {host} without authentication; keep it off public networks", file=sys.stderr)
        print(f"Inference Lab on http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}")
        uvicorn.run(create_app(), host=host, port=port, log_level="warning")
        return 0

    lab = Lab()
    if a.cmd == "experiments":
        for r in lab.store.list():
            print(f"{r['id']}  {r['kind']:<10} {r['provenance']:<18} {(r.get('model') or {}).get('id') or ''}")
        return 0
    simple = {
        "hardware": ("hardware.scan", lambda: {}),
        "inspect": ("hub.inspect", lambda: {"model": a.model}),
        "inspect-local": ("model.inspect_local", lambda: {"model": a.model}),
        "prepare-tiny": ("model.prepare_tiny", lambda: {}),
        "download": ("model.download", lambda: {"model": a.model, "revision": a.revision}),
        "infer": ("inference.run", lambda: {"model": a.model, "prompt": a.prompt, "max_new_tokens": a.max_new_tokens}),
        "compare": ("experiment.compare", lambda: {"baseline_id": a.baseline, "candidate_id": a.candidate}),
        "report": ("report.generate", lambda: {"experiment_ids": a.ids, "lang": a.lang, "decision": a.decision}),
    }
    if a.cmd in simple:
        action, params = simple[a.cmd]
        run = lab.submit(action, params(), approve=getattr(a, "approve", False), wait=True)
        code = _print_run(run, a.json)
        if run.status == "succeeded" and not a.json:
            _summary(run)
        return code
    if a.cmd == "bench":
        srv = lab.submit("server.start", {"model": a.model, "kind": a.kind, "port": a.port}, approve=a.approve, wait=True)
        if _print_run(srv, a.json):
            return 1
        try:
            run = lab.submit("bench.run", {"concurrency": a.concurrency, "max_tokens": a.max_tokens,
                                           "num_requests": a.num_requests, "warmup_requests": a.warmup,
                                           "trials": a.trials, "hypothesis": a.hypothesis},
                             approve=a.approve, wait=True)
            code = _print_run(run, a.json)
            if run.status == "succeeded" and not a.json:
                _summary(run)
            return code
        finally:
            lab.servers.stop()
    return 2


if __name__ == "__main__":
    sys.exit(main())
