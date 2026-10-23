"""Allowlisted actions and the run engine shared by the UI, missions, and CLI.

There is no generic "run this command" endpoint. Each action is a named Python function with
validated parameters, a declared approval policy, required capabilities, the source files that
implement it, and an equivalent CLI command a user can run themselves.

Run statuses:
  blocked   needs approval that was not given (nothing executed)
  not_run   the machine lacks a required capability (nothing executed)
  running   executing; heartbeat_at updates while it is alive
  succeeded executed and produced a result
  failed    executed and failed; the error stays visible
"""

from __future__ import annotations

import json
import shlex
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

from . import hardware, hub, inference, memory
from .bench.loadgen import DEFAULT_PROMPT, BenchConfig, run_benchmark
from .config import load_settings
from .experiments import ExperimentStore, compare_records, new_record
from .provenance import Provenance
from .integrations import llmbench
from .serving.manager import ServerManager, llamacpp_argv, mini_argv, vllm_argv

# --------------------------------------------------------------------------- parameters


class NoParams(BaseModel):
    model_config = {"extra": "forbid"}


class ModelParams(BaseModel):
    model_config = {"extra": "forbid"}
    model: str = Field(min_length=1, max_length=200)

    @field_validator("model")
    @classmethod
    def _valid(cls, v: str) -> str:
        return v if v == inference.TINY_MODEL_REF else hub.normalize_model_ref(v)


class DownloadParams(ModelParams):
    revision: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")


class InferParams(ModelParams):
    prompt: str = Field(min_length=1, max_length=4000)
    max_new_tokens: int = Field(default=24, ge=1, le=256)


class ServerParams(ModelParams):
    kind: str = Field(default="mini", pattern=r"^(mini|vllm|llamacpp-cpu|llamacpp-adreno)$")
    port: int = Field(default=8800, ge=1024, le=65535)

    @field_validator("model")
    @classmethod
    def _valid(cls, v: str) -> str:
        # llama.cpp servers take GGUF files from the llmbench folder: gguf:<name>
        if llmbench.GGUF_REF.match(v):
            return v
        return v if v == inference.TINY_MODEL_REF else hub.normalize_model_ref(v)


def _server_argv(p: ServerParams) -> list[str]:
    if p.kind == "mini":
        return mini_argv(p.model, p.port)
    if p.kind == "vllm":
        return vllm_argv(p.model, p.port)
    try:
        return llamacpp_argv(p.model, p.port, p.kind.split("-", 1)[1])
    except (FileNotFoundError, ValueError) as e:
        return ["# " + str(e)]


class BenchParams(BaseModel):
    model_config = {"extra": "forbid"}
    prompt: str = Field(default=DEFAULT_PROMPT, min_length=1, max_length=8000)
    max_tokens: int = Field(default=16, ge=1, le=2048)
    concurrency: int = Field(default=1, ge=1, le=256)
    num_requests: int = Field(default=8, ge=1, le=5000)
    warmup_requests: int = Field(default=1, ge=0, le=100)
    trials: int = Field(default=2, ge=1, le=20)
    timeout_s: float = Field(default=120, ge=1, le=900)
    hypothesis: str | None = Field(default=None, max_length=2000)
    baseline_id: str | None = Field(default=None, max_length=80)


class CompareParams(BaseModel):
    model_config = {"extra": "forbid"}
    baseline_id: str = Field(max_length=80)
    candidate_id: str = Field(max_length=80)


class ReportParams(BaseModel):
    model_config = {"extra": "forbid"}
    experiment_ids: list[str] = Field(min_length=1, max_length=20)
    lang: str = Field(default="en", pattern=r"^(en|zh-TW)$")
    decision: str | None = Field(default=None, max_length=4000)


# --------------------------------------------------------------------------- runs


@dataclass
class Run:
    id: str
    action: str
    params: dict[str, Any]
    status: str
    command: str
    provenance: str = Provenance.NOT_RUN.value
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    heartbeat_at: float | None = None
    progress: float | None = None
    progress_samples: list[list[float]] = field(default_factory=list)
    timeout_s: float = 600
    logs: list[dict[str, Any]] = field(default_factory=list)
    result: Any = None
    error: dict[str, Any] | None = None
    experiment_id: str | None = None
    mission_id: str | None = None
    step_id: str | None = None
    approval: dict[str, Any] | None = None

    def log(self, msg: str, level: str = "info") -> None:
        self.logs.append({"t": time.time(), "level": level, "msg": msg})
        self.heartbeat_at = time.time()


@dataclass
class Ctx:
    run: Run
    lab: "Lab"

    def log(self, msg: str, level: str = "info") -> None:
        self.run.log(msg, level)

    def progress(self, p: float) -> None:
        self.run.progress = max(0.0, min(1.0, p))
        self.run.heartbeat_at = time.time()
        self.run.progress_samples.append([self.run.heartbeat_at, self.run.progress])
        del self.run.progress_samples[:-120]


class ActionError(Exception):
    """Expected failure with a stable code the UI can translate and troubleshoot."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass
class ActionSpec:
    id: str
    params: type[BaseModel]
    handler: Callable[[Ctx, Any], Any]
    cli: Callable[[Any], str]
    sources: list[tuple[str, str]]
    tests: list[str]
    approval: Callable[[Any, "Lab"], str | None] = lambda p, lab: None
    requires: list[str] = field(default_factory=list)
    timeout_s: float = 600
    extra_requires: Callable[[Any], list[str]] = lambda p: []

    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "requires": self.requires, "timeout_s": self.timeout_s,
                "sources": [{"file": f, "symbol": s} for f, s in self.sources], "tests": self.tests,
                "params_schema": self.params.model_json_schema()}


# --------------------------------------------------------------------------- handlers


def _hardware_scan(ctx: Ctx, p: NoParams) -> dict[str, Any]:
    ctx.log("probing CPU, memory, NVIDIA GPU, Docker, and Python ML libraries")
    scan = hardware.scan()
    for name, pr in scan["probes"].items():
        ctx.log(f"[{pr['status']}] {name}: {pr['command']}")
    ctx.lab.last_scan = scan
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    rec = new_record("hardware", Provenance.LIVE_MEASURED, hardware=hardware.hardware_fingerprint(scan),
                     result=scan, run_id=ctx.run.id, mission_id=ctx.run.mission_id)
    ctx.run.experiment_id = ctx.lab.store.save(rec)["id"]
    return scan


def _hub_inspect(ctx: Ctx, p: ModelParams) -> dict[str, Any]:
    if p.model == inference.TINY_MODEL_REF:
        raise ActionError("not_a_hub_model", "lab/tiny-random is built locally; it has no Hub page")
    ctx.log(f"GET {load_settings().hf_endpoint}/api/models/{p.model}?blobs=true")
    try:
        info = hub.inspect_model(p.model)
    except hub.HubUnavailable as e:
        raise ActionError("hub_unreachable", str(e)) from e
    for c in info.get("calls", []):
        ctx.log(c)
    if not info["ok"]:
        raise ActionError(info["error"], f"HTTP {info.get('http_status')}")
    s = info["summary"]
    scan = ctx.lab.scan()
    est = memory.estimate(s.get("parameters"), s.get("config"), dtype=_st_dtype(s.get("dominant_dtype")))
    info["memory_estimate"] = est
    info["compatibility"] = memory.assess_compatibility(est, scan["summary"], scan["capabilities"])
    info["download_plan"] = hub.download_plan(s)
    ctx.lab.inspected[p.model] = info
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    return info


def _inspect_local(ctx: Ctx, p: ModelParams) -> dict[str, Any]:
    from .local_model import inspect_local

    if p.model == inference.TINY_MODEL_REF and not inference.model_dir_for(p.model).joinpath("config.json").exists():
        ctx.log("lab/tiny-random not built yet; building it first")
        inference.build_tiny_model(log=ctx.log)
    ctx.log(f"reading config.json, tokenizer files and safetensors headers in {inference.model_dir_for(p.model)}")
    try:
        s = inspect_local(p.model)
    except FileNotFoundError as e:
        raise ActionError("model_not_local", str(e)) from e
    scan = ctx.lab.scan()
    est = memory.estimate(s["parameters"], s["config"], dtype=_st_dtype(s.get("dominant_dtype")))
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    return {"ok": True, "model_id": p.model, "source": "local_files", "summary": s, "memory_estimate": est,
            "compatibility": memory.assess_compatibility(est, scan["summary"], scan["capabilities"])}


def _st_dtype(d: str | None) -> str:
    return {"F32": "float32", "F16": "float16", "BF16": "bfloat16", "I8": "int8"}.get(d or "", "bfloat16")


def _prepare_tiny(ctx: Ctx, p: NoParams) -> dict[str, Any]:
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    return inference.build_tiny_model(log=ctx.log)


def _download_approval(p: DownloadParams, lab: "Lab") -> str | None:
    return "model_download_uses_network_and_disk"


def _download(ctx: Ctx, p: DownloadParams) -> dict[str, Any]:
    info = ctx.lab.inspected.get(p.model)
    if not info:
        ctx.log("model not inspected yet; inspecting first")
        info = _hub_inspect(ctx, ModelParams(model=p.model))
    plan = info["download_plan"]
    if not plan["allowed"]:
        raise ActionError("download_refused", plan["reason"])
    est = plan.get("estimated_bytes")
    limit = load_settings().max_download_bytes
    if est is None:
        raise ActionError("download_size_unknown", "the Hub did not report file sizes; refusing to download blind")
    if est > limit:
        raise ActionError("download_too_large", f"{est / 1024**3:.2f} GiB > limit {limit / 1024**3:.2f} GiB")
    target = inference.model_dir_for(p.model)
    stop = threading.Event()

    def watch() -> None:  # heartbeat + progress from bytes on disk, for stuck detection
        while not stop.wait(1.0):
            ctx.progress(min(0.99, inference.dir_size(target) / est))

    threading.Thread(target=watch, daemon=True).start()
    try:
        res = inference.download_model(p.model, p.revision or info["summary"].get("revision"),
                                       plan["allow_patterns"], log=ctx.log)
    finally:
        stop.set()
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    return res


def _infer(ctx: Ctx, p: InferParams) -> dict[str, Any]:
    if p.model == inference.TINY_MODEL_REF and not inference.model_dir_for(p.model).joinpath("config.json").exists():
        ctx.log("lab/tiny-random not built yet; building it first")
        inference.build_tiny_model(log=ctx.log)
    try:
        res = inference.run_inference(p.model, p.prompt, p.max_new_tokens, log=ctx.log)
    except FileNotFoundError as e:
        raise ActionError("model_not_local", str(e)) from e
    except PermissionError as e:
        raise ActionError("remote_code_refused", str(e)) from e
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    scan = ctx.lab.scan()
    rec = new_record("inference", Provenance.LIVE_MEASURED,
                     model={"id": p.model, "revision": _local_revision(p.model)},
                     hardware=hardware.hardware_fingerprint(scan), engine=res["engine"],
                     params=p.model_dump(), result=res, run_id=ctx.run.id, mission_id=ctx.run.mission_id)
    ctx.run.experiment_id = ctx.lab.store.save(rec)["id"]
    return res


def _local_revision(model: str) -> str | None:
    return inference.local_revision(model)


def _server_approval(p: ServerParams, lab: "Lab") -> str | None:
    return "vllm_uses_gpu_and_pulls_container_image" if p.kind == "vllm" else None


def _server_start(ctx: Ctx, p: ServerParams) -> dict[str, Any]:
    scan = ctx.lab.scan()
    if p.kind == "vllm":
        if not scan["capabilities"]["vllm_docker"]:
            raise ActionError("capability_missing:vllm_docker", "vLLM serving needs an NVIDIA GPU and a running Docker daemon")
        info = ctx.lab.servers.start_vllm(p.model, p.port)
        timeout = 900
    elif p.kind.startswith("llamacpp"):
        backend = p.kind.split("-", 1)[1]
        if not llmbench.GGUF_REF.match(p.model):
            raise ActionError("not_a_gguf_model", "llama.cpp servers take gguf:<name> models from the llmbench folder")
        if not scan["capabilities"].get(f"llamacpp_{backend}"):
            raise ActionError(f"capability_missing:llamacpp_{backend}",
                              "llama-server for this backend was not found in the llmbench tools folder")
        try:
            info = ctx.lab.servers.start_llamacpp(p.model, p.port, backend)
        except FileNotFoundError as e:
            raise ActionError("model_not_local", str(e)) from e
        timeout = 300
    else:
        if p.model == inference.TINY_MODEL_REF and not inference.model_dir_for(p.model).joinpath("config.json").exists():
            inference.build_tiny_model(log=ctx.log)
        info = ctx.lab.servers.start_mini(p.model, p.port)
        timeout = 180
    ctx.log("$ " + shlex.join(info.argv))
    ctx.log(f"waiting for GET {info.base_url}/health")
    t0 = time.time()
    ok = ctx.lab.servers.wait_healthy(timeout, on_tick=lambda h: ctx.progress(min(0.95, (time.time() - t0) / timeout)))
    h = ctx.lab.servers.health()
    if not ok:
        tail = h.get("log_tail", "")
        ctx.lab.servers.stop()
        raise ActionError("server_not_healthy", tail[-800:])
    ctx.log(f"healthy after {time.time() - t0:.1f}s")
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    return {"server": asdict(info), "base_url": info.base_url, "startup_s": round(time.time() - t0, 2),
            "health": {k: v for k, v in h.items() if k != "log_tail"}, "version": ctx.lab.servers.version()}


def _server_health(ctx: Ctx, p: NoParams) -> dict[str, Any]:
    h = ctx.lab.servers.health()
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    return {k: v for k, v in h.items() if k != "log_tail"}


def _server_stop(ctx: Ctx, p: NoParams) -> dict[str, Any]:
    ctx.lab.servers.stop()
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    return {"stopped": True}


def _bench_approval(p: BenchParams, lab: "Lab") -> str | None:
    total = (p.num_requests * p.trials + p.warmup_requests)
    return "large_benchmark" if total * p.max_tokens > 50_000 or total > 500 else None


def _bench(ctx: Ctx, p: BenchParams) -> dict[str, Any]:
    srv = ctx.lab.servers.current
    if not srv or not ctx.lab.servers.health().get("healthy"):
        raise ActionError("no_healthy_server", "start a server first (Mission 04)")
    cfg = BenchConfig(base_url=srv.base_url, model=srv.model, prompt=p.prompt, max_tokens=p.max_tokens,
                      concurrency=p.concurrency, num_requests=p.num_requests, warmup_requests=p.warmup_requests,
                      trials=p.trials, timeout_s=p.timeout_s)
    res = run_benchmark(cfg, server_pid=ctx.lab.servers._proc.pid if ctx.lab.servers._proc else None,
                        log=ctx.log, progress=ctx.progress)
    scan = ctx.lab.scan()
    if res.get("aborted"):
        raise ActionError("benchmark_aborted", res["aborted"])
    any_ok = any(t["succeeded"] for t in res["trials"])
    prov = Provenance.LIVE_MEASURED if any_ok else Provenance.FAILED
    ctx.run.provenance = prov.value
    version = ctx.lab.servers.version() or {}
    engine = {"name": {"vllm": "vllm", "llamacpp-cpu": "llama.cpp-cpu",
                       "llamacpp-adreno": "llama.cpp-adreno-opencl"}.get(srv.kind, "inference-lab-mini"),
              "version": version.get("version") or version.get("transformers"), "details": version}
    rec = new_record("benchmark", prov, model={"id": srv.model, "revision": _local_revision(srv.model)},
                     hardware=hardware.hardware_fingerprint(scan), engine=engine,
                     params={k: v for k, v in p.model_dump().items() if k not in ("hypothesis", "baseline_id")},
                     result=res, run_id=ctx.run.id, mission_id=ctx.run.mission_id,
                     notes={k: v for k, v in {"hypothesis": p.hypothesis, "baseline_id": p.baseline_id}.items() if v})
    ctx.run.experiment_id = ctx.lab.store.save(rec)["id"]
    if not any_ok:
        raise ActionError("all_requests_failed", json.dumps(res["trials"][0]["errors"]))
    return {k: v for k, v in res.items() if k != "raw_samples"}


def _compare(ctx: Ctx, p: CompareParams) -> dict[str, Any]:
    try:
        a, b = ctx.lab.store.get(p.baseline_id), ctx.lab.store.get(p.candidate_id)
    except (FileNotFoundError, ValueError) as e:
        raise ActionError("experiment_not_found", str(e)) from e
    ctx.run.provenance = Provenance.LIVE_MEASURED.value if all(
        r["provenance"] == Provenance.LIVE_MEASURED.value for r in (a, b)) else Provenance.VERIFIED_IMPORTED.value
    return compare_records(a, b)


def _report(ctx: Ctx, p: ReportParams) -> dict[str, Any]:
    from .reports import build_report

    recs = []
    for eid in p.experiment_ids:
        try:
            recs.append(ctx.lab.store.get(eid))
        except (FileNotFoundError, ValueError) as e:
            raise ActionError("experiment_not_found", str(e)) from e
    rep = build_report(recs, lang=p.lang, decision=p.decision)
    path = load_settings().ensure().reports_dir / f"report-{ctx.run.id}-{p.lang}.md"
    path.write_text(rep["markdown"], encoding="utf-8")
    ctx.log(f"wrote {path}")
    ctx.run.provenance = Provenance.LIVE_MEASURED.value
    return {**rep, "path": str(path)}


# --------------------------------------------------------------------------- registry

ACTIONS: dict[str, ActionSpec] = {a.id: a for a in [
    ActionSpec("hardware.scan", NoParams, _hardware_scan, lambda p: "inference-lab hardware",
               [("inference_lab/hardware.py", "scan"), ("inference_lab/hardware.py", "probe_gpu"),
                ("inference_lab/hardware.py", "capabilities")],
               ["tests/test_hardware.py"], timeout_s=60),
    ActionSpec("hub.inspect", ModelParams, _hub_inspect, lambda p: f"inference-lab inspect {shlex.quote(p.model)}",
               [("inference_lab/hub.py", "inspect_model"), ("inference_lab/hub.py", "summarize"),
                ("inference_lab/memory.py", "estimate"), ("inference_lab/memory.py", "assess_compatibility")],
               ["tests/test_hub.py", "tests/test_memory.py"], requires=["hub_access"], timeout_s=60),
    ActionSpec("model.inspect_local", ModelParams, _inspect_local,
               lambda p: f"inference-lab inspect-local {shlex.quote(p.model)}",
               [("inference_lab/local_model.py", "inspect_local"), ("inference_lab/local_model.py", "count_parameters"),
                ("inference_lab/memory.py", "estimate")],
               ["tests/test_local_model.py", "tests/test_memory.py"], timeout_s=120),
    ActionSpec("model.prepare_tiny", NoParams, _prepare_tiny, lambda p: "inference-lab prepare-tiny",
               [("inference_lab/inference.py", "build_tiny_model")], ["tests/test_inference.py"],
               requires=["cpu_inference"], timeout_s=300),
    ActionSpec("model.download", DownloadParams, _download,
               lambda p: f"inference-lab download {shlex.quote(p.model)} --approve",
               [("inference_lab/inference.py", "download_model"), ("inference_lab/hub.py", "download_plan")],
               ["tests/test_actions.py"], approval=_download_approval, requires=["cpu_inference", "hub_access"],
               timeout_s=3600),
    ActionSpec("inference.run", InferParams, _infer,
               lambda p: f"inference-lab infer --model {shlex.quote(p.model)} --prompt {shlex.quote(p.prompt)} "
                         f"--max-new-tokens {p.max_new_tokens}",
               [("inference_lab/inference.py", "run_inference"), ("inference_lab/inference.py", "_TokenClock")],
               ["tests/test_inference.py"], requires=["cpu_inference"], timeout_s=600),
    ActionSpec("server.start", ServerParams, _server_start,
               lambda p: shlex.join(_server_argv(p)),
               [("inference_lab/serving/manager.py", "mini_argv"), ("inference_lab/serving/manager.py", "vllm_argv"),
                ("inference_lab/serving/manager.py", "llamacpp_argv"),
                ("inference_lab/serving/manager.py", "ServerManager"),
                ("inference_lab/serving/mini_server.py", "create_app")],
               ["tests/test_serving.py"], approval=_server_approval, requires=["cpu_inference"], timeout_s=900,
               extra_requires=lambda p: (["vllm_docker", "hub_access"] if p.kind == "vllm" else
                                         [p.kind.replace("-", "_")] if p.kind.startswith("llamacpp") else [])),
    ActionSpec("server.health", NoParams, _server_health,
               lambda p: "curl -s http://127.0.0.1:<port>/health",
               [("inference_lab/serving/manager.py", "ServerManager")], ["tests/test_serving.py"], timeout_s=10),
    ActionSpec("server.stop", NoParams, _server_stop, lambda p: "inference-lab serve --stop",
               [("inference_lab/serving/manager.py", "ServerManager")], ["tests/test_serving.py"], timeout_s=60),
    ActionSpec("bench.run", BenchParams, _bench,
               lambda p: (f"inference-lab bench --concurrency {p.concurrency} --max-tokens {p.max_tokens} "
                          f"--num-requests {p.num_requests} --warmup {p.warmup_requests} --trials {p.trials}"),
               [("inference_lab/bench/loadgen.py", "run_benchmark"), ("inference_lab/bench/loadgen.py", "_one"),
                ("inference_lab/bench/metrics.py", "summarize"), ("inference_lab/bench/metrics.py", "percentile")],
               ["tests/test_metrics.py", "tests/test_serving.py"], approval=_bench_approval, timeout_s=1800),
    ActionSpec("experiment.compare", CompareParams, _compare,
               lambda p: f"inference-lab compare {p.baseline_id} {p.candidate_id}",
               [("inference_lab/experiments.py", "comparability"), ("inference_lab/bench/metrics.py", "compare")],
               ["tests/test_experiments.py"], timeout_s=30),
    ActionSpec("report.generate", ReportParams, _report,
               lambda p: f"inference-lab report {' '.join(p.experiment_ids)} --lang {p.lang}",
               [("inference_lab/reports.py", "build_report")], ["tests/test_reports.py"], timeout_s=60),
]}


class Lab:
    """Process-wide state: runs, servers, experiment store, last hardware scan."""

    def __init__(self, store: ExperimentStore | None = None) -> None:
        self.store = store or ExperimentStore()
        self.servers = ServerManager()
        self.runs: dict[str, Run] = {}
        self.last_scan: dict[str, Any] | None = None
        self.inspected: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.on_finish: list[Callable[[Run], None]] = []

    def scan(self) -> dict[str, Any]:
        if self.last_scan is None:
            self.last_scan = hardware.scan()
        return self.last_scan

    def preview(self, action_id: str, params: dict[str, Any]) -> dict[str, Any]:
        spec = self._spec(action_id)
        p = spec.params.model_validate(params)
        missing = [c for c in spec.requires + spec.extra_requires(p) if not self.scan()["capabilities"].get(c)]
        return {"action": spec.describe(), "command": spec.cli(p), "approval_required": spec.approval(p, self),
                "missing_capabilities": missing}

    def _spec(self, action_id: str) -> ActionSpec:
        if action_id not in ACTIONS:
            raise KeyError(f"unknown action {action_id!r}")
        return ACTIONS[action_id]

    def submit(self, action_id: str, params: dict[str, Any], approve: bool = False, mission_id: str | None = None,
               wait: bool = False, step_id: str | None = None) -> Run:
        spec = self._spec(action_id)
        p = spec.params.model_validate(params)  # raises ValidationError on bad input
        run = Run(id=f"run-{uuid.uuid4().hex[:10]}", action=action_id, params=p.model_dump(), status="pending",
                  command=spec.cli(p), timeout_s=spec.timeout_s, mission_id=mission_id, step_id=step_id)
        with self._lock:
            self.runs[run.id] = run
        reason = spec.approval(p, self)
        if reason and not approve:
            run.status = "blocked"
            run.error = {"code": "approval_required", "detail": reason}
            run.log(f"blocked: approval required ({reason}); nothing was executed", "warn")
            self._persist(run)
            return run
        if reason:
            run.approval = {"reason": reason, "approved_at": time.time()}
        missing = [c for c in spec.requires + spec.extra_requires(p) if not self.scan()["capabilities"].get(c)]
        if missing:
            run.status = "not_run"
            run.error = {"code": "capability_missing", "detail": ", ".join(missing)}
            run.log(f"not run: this machine lacks {', '.join(missing)}", "warn")
            self._persist(run)
            return run
        t = threading.Thread(target=self._execute, args=(spec, p, run), daemon=True)
        run.status = "running"
        run.started_at = run.heartbeat_at = time.time()
        t.start()
        if wait:
            t.join()
        return run

    def _execute(self, spec: ActionSpec, p: BaseModel, run: Run) -> None:
        ctx = Ctx(run, self)
        try:
            run.result = spec.handler(ctx, p)
            run.status = "succeeded"
            run.progress = 1.0
        except ActionError as e:
            run.status = "failed"
            run.error = {"code": e.code, "detail": e.detail}
            if run.provenance != Provenance.FAILED.value and run.experiment_id is None:
                run.provenance = Provenance.FAILED.value
            run.log(f"failed: {e.code} {e.detail[:500]}", "error")
        except Exception as e:  # noqa: BLE001 - surface every failure to the user
            run.status = "failed"
            run.provenance = Provenance.FAILED.value
            run.error = {"code": "unexpected_error", "detail": f"{type(e).__name__}: {e}",
                         "trace": traceback.format_exc()[-3000:]}
            run.log(f"failed: {type(e).__name__}: {e}", "error")
        finally:
            run.finished_at = time.time()
            self._persist(run)

    def _persist(self, run: Run) -> None:
        for cb in self.on_finish:
            try:
                cb(run)
            except Exception:  # noqa: BLE001 - a listener must not hide the run
                traceback.print_exc()
        d = load_settings().ensure().runs_dir
        (d / f"{run.id}.json").write_text(json.dumps(asdict(run), default=str, indent=1), encoding="utf-8")

    def get_run(self, run_id: str) -> Run:
        return self.runs[run_id]


__all__ = ["ACTIONS", "Lab", "Run", "ActionError", "ValidationError"]
