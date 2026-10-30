"""HTTP API between the UI and the lab. Localhost-only by default; no generic exec endpoint.

Run: inference-lab ui   (or: uvicorn inference_lab.api:get_app --factory --host 127.0.0.1 --port 8765)
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import __version__, i18n
from .actions import ACTIONS, Lab, Run
from .config import REPO_ROOT
from .demo import demo_concurrency_sweep
from .experiments import compare_records
from .missions.engine import Progress, all_statuses, evaluate_check, evaluate_step, load_missions
from .research import registry
from .sourcemap import SourceAccessError, read_source, tree
from .stuck import diagnose, error_help
from .tutor import tutor

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}
PLACEHOLDER = re.compile(r"^\$\{(m0\d-[a-z0-9-]+):([A-Za-z0-9_-]+)\}$")

CATALOG = [
    {"id": "lab/tiny-random", "kind": "local", "size_class": "tiny", "download": False,
     "note": {"en": "Built on your machine in seconds. Random weights: proves the pipeline, outputs gibberish.",
              "zh-TW": "在你的電腦上幾秒內建立。權重是隨機的：能驗證整條流程，但輸出是亂碼。"}},
    {"id": "openai-community/gpt2", "kind": "hub", "size_class": "small", "download": True,
     "note": {"en": "Classic small GPT-2. Press Inspect to fetch live size, license and files from the Hub.",
              "zh-TW": "經典的小型 GPT-2。按「檢視」從 Hub 取得即時的大小、授權與檔案資訊。"}},
    {"id": "HuggingFaceTB/SmolLM2-135M-Instruct", "kind": "hub", "size_class": "small", "download": True,
     "note": {"en": "Small instruction-tuned model with a chat template. Inspect to confirm details.",
              "zh-TW": "有 chat template 的小型指令微調模型。請按「檢視」確認細節。"}},
    {"id": "Qwen/Qwen2.5-0.5B-Instruct", "kind": "hub", "size_class": "small", "download": True,
     "note": {"en": "Sub-1B chat model; a common first model for vLLM on a single GPU. Inspect to confirm.",
              "zh-TW": "不到 1B 的對話模型；常被當成單張 GPU 上跑 vLLM 的第一個模型。請按「檢視」確認。"}},
]


class Submit(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    approve: bool = False


class StepRun(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    approve: bool = False


class QuizAnswer(BaseModel):
    answer: int


class Explain(BaseModel):
    kind: str = Field(pattern=r"^(concept|code|step)$")
    id: str | None = None
    file: str | None = None
    symbol: str | None = None
    mission: str | None = None
    step: str | None = None
    level: str = "simple"
    lang: str = "en"


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)
    lang: str = "en"


def _public_mission(m: Any) -> dict[str, Any]:
    """Mission data for the browser. Quiz answers and explanations stay on the server: the answer is checked by
    POST .../quiz, and the explanation is returned only after a correct answer."""
    d = m.model_dump(by_alias=True)
    for step in d.get("steps") or []:
        if step.get("quiz"):
            step["quiz"] = {k: v for k, v in step["quiz"].items() if k not in ("answer", "explanation")}
    return d


def create_app(lab: Lab | None = None, progress: Progress | None = None) -> FastAPI:
    lab = lab or Lab()
    progress = progress or Progress()
    missions = {m.id: m for m in load_missions()}
    app = FastAPI(title="Inference Lab", version=__version__)

    def on_finish(run: Run) -> None:
        if run.mission_id and run.step_id and run.mission_id in missions:
            m = missions[run.mission_id]
            if run.step_id == "__challenge__" and m.challenge:
                ev = {"run": asdict(run), "result": run.result or {}}
                checks = [evaluate_check(c, ev) for c in m.challenge.checks]
                status = "verified" if run.status == "succeeded" and all(c["passed"] for c in checks) else run.status
                progress.record_challenge(m.id, {"status": status, "checks": checks, "run_id": run.id})
                return
            step = next((s for s in m.steps if s.id == run.step_id), None)
            if step:
                progress.record_evaluation(m.id, step.id, evaluate_step(step, asdict(run)), asdict(run))

    lab.on_finish.append(on_finish)

    @app.middleware("http")
    async def host_guard(request: Request, call_next):  # noqa: ANN001, ANN202 - DNS-rebinding protection
        host = (request.headers.get("host") or "").rsplit(":", 1)[0] if not (request.headers.get("host") or "").startswith("[") \
            else (request.headers.get("host") or "").split("]")[0] + "]"
        if host not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "host not allowed"}, status_code=403)
        return await call_next(request)

    # ------------------------------------------------------------------ basics
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "languages": list(i18n.SUPPORTED), "default_language": i18n.DEFAULT}

    @app.get("/api/hardware")
    def hardware() -> dict[str, Any]:
        return {"scan": lab.last_scan}

    @app.get("/api/actions")
    def actions() -> list[dict[str, Any]]:
        return [a.describe() for a in ACTIONS.values()]


    @app.post("/api/actions/{action_id}/preview")
    def preview(action_id: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            return lab.preview(action_id, body.get("params", {}))
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except (ValidationError, ValueError) as e:
            raise HTTPException(422, _err(e)) from e

    def _submit(action: str, params: dict[str, Any], approve: bool, mission_id: str | None = None,
                step_id: str | None = None) -> dict[str, Any]:
        try:
            run = lab.submit(action, params, approve=approve, mission_id=mission_id, step_id=step_id)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except (ValidationError, ValueError) as e:
            raise HTTPException(422, _err(e)) from e
        return asdict(run)

    @app.post("/api/runs")
    def submit(body: Submit) -> dict[str, Any]:
        return _submit(body.action, body.params, body.approve)

    @app.get("/api/runs")
    def runs() -> list[dict[str, Any]]:
        return [_run_summary(r) for r in sorted(lab.runs.values(), key=lambda r: r.created_at, reverse=True)]

    @app.get("/api/runs/{run_id}")
    def run(run_id: str) -> dict[str, Any]:
        r = lab.runs.get(run_id)
        if not r:
            raise HTTPException(404, "run not found")
        return asdict(r)

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict[str, Any]:
        if run_id not in lab.runs:
            raise HTTPException(404, "run not found")
        return asdict(lab.cancel(run_id))

    @app.get("/api/runs/{run_id}/diagnosis")
    def run_diagnosis(run_id: str, lang: str = "en") -> dict[str, Any]:
        r = lab.runs.get(run_id)
        if not r:
            raise HTTPException(404, "run not found")
        sh = lab.servers.health() if r.action == "server.start" else None
        return diagnose(asdict(r), lang, server_health=sh)

    @app.get("/api/errors/{code}")
    def explain_error(code: str, lang: str = "en") -> dict[str, str]:
        return error_help(code, lang)

    # ------------------------------------------------------------------ missions
    @app.get("/api/missions")
    def mission_list() -> dict[str, Any]:
        caps = lab.scan()["capabilities"] if lab.last_scan else {}
        return {"missions": [_public_mission(m) for m in missions.values()],
                "status": all_statuses(list(missions.values()), progress, caps),
                "progress": progress.data, "capabilities": caps, "scanned": lab.last_scan is not None}

    def _resolve(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_resolve(v) for v in value]
        if isinstance(value, str):
            m = PLACEHOLDER.match(value)
            if m:
                ev = (progress.data["missions"].get(m.group(1), {}).get("steps", {}).get(m.group(2), {})
                      .get("evaluation") or {})
                if not ev.get("experiment_id"):
                    raise HTTPException(409, f"needs evidence from {m.group(1)} step {m.group(2)} first")
                return ev["experiment_id"]
        return value


    @app.post("/api/missions/{mid}/steps/{sid}/run")
    def step_run(mid: str, sid: str, body: StepRun) -> dict[str, Any]:
        m = missions.get(mid)
        step = next((s for s in m.steps if s.id == sid), None) if m else None
        if not step or not step.action:
            raise HTTPException(404, "no runnable step")
        params = {**step.action.params, **{k: v for k, v in body.params.items() if k in step.action.editable}}
        return _submit(step.action.id, _resolve(params), body.approve, mission_id=mid, step_id=sid)

    @app.post("/api/missions/{mid}/challenge/run")
    def challenge_run(mid: str, body: StepRun) -> dict[str, Any]:
        m = missions.get(mid)
        if not m or not m.challenge:
            raise HTTPException(404, "no challenge")
        params = {**m.challenge.action.params,
                  **{k: v for k, v in body.params.items() if k in m.challenge.action.editable}}
        return _submit(m.challenge.action.id, _resolve(params), body.approve, mission_id=mid, step_id="__challenge__")


    @app.post("/api/missions/{mid}/steps/{sid}/quiz")
    def quiz(mid: str, sid: str, body: QuizAnswer) -> dict[str, Any]:
        m = missions.get(mid)
        step = next((s for s in m.steps if s.id == sid), None) if m else None
        if not step or not step.quiz:
            raise HTTPException(404, "no quiz")
        correct = body.answer == step.quiz.answer
        progress.record_quiz(mid, sid, correct)
        return {"correct": correct, "explanation": step.quiz.explanation.model_dump(by_alias=True) if correct else None}

    @app.post("/api/missions/{mid}/steps/{sid}/hint")
    def hint(mid: str, sid: str) -> dict[str, Any]:
        m = missions.get(mid)
        step = next((s for s in m.steps if s.id == sid), None) if m else None
        if not step:
            raise HTTPException(404, "no step")
        used = progress.use_hint(mid, sid)
        return {"hints_used": used, "available": len(step.hints),
                "hints": [h.model_dump(by_alias=True) for h in step.hints[:used]]}

    @app.post("/api/progress/reset")
    def reset_progress() -> dict[str, bool]:
        progress.reset()
        return {"ok": True}

    # ------------------------------------------------------------------ models
    @app.get("/api/models/catalog")
    def catalog() -> list[dict[str, Any]]:
        return CATALOG

    @app.get("/api/models/local")
    def local_models() -> list[str]:
        from .local_model import list_local_models

        return list_local_models()

    @app.get("/api/models/inspected")
    def inspected() -> dict[str, Any]:
        return lab.inspected

    # ------------------------------------------------------------------ experiments
    @app.get("/api/experiments")
    def experiments(kind: str | None = None) -> list[dict[str, Any]]:
        return [_exp_summary(r) for r in lab.store.list(kind)]

    @app.get("/api/experiments/{eid}")
    def experiment(eid: str) -> dict[str, Any]:
        try:
            return lab.store.get(eid)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(404, "experiment not found") from e

    @app.post("/api/experiments/{eid}/notes")
    def notes(eid: str, body: dict[str, str]) -> dict[str, Any]:
        allowed = {k: v for k, v in body.items() if k in ("hypothesis", "observation", "decision", "lesson")}
        try:
            return _exp_summary(lab.store.annotate(eid, allowed))
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(404, "experiment not found") from e

    @app.post("/api/experiments/import")
    def import_exp(body: dict[str, Any]) -> dict[str, Any]:
        try:
            return _exp_summary(lab.store.import_record(body))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.get("/api/experiments/{a}/compare/{b}")
    def compare(a: str, b: str, lang: str = "en") -> dict[str, Any]:
        try:
            ra, rb = lab.store.get(a), lab.store.get(b)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(404, "experiment not found") from e
        cmp = compare_records(ra, rb)
        cmp["suggestions"] = tutor.suggest_optimizations(cmp, ra, rb, lang)
        return cmp

    @app.get("/api/demo/benchmark")
    def demo() -> dict[str, Any]:
        return demo_concurrency_sweep()

    # ------------------------------------------------------------------ source + tutor + research
    @app.get("/api/source")
    def source(path: str, symbol: str | None = None) -> dict[str, Any]:
        try:
            return read_source(path, symbol)
        except SourceAccessError as e:
            raise HTTPException(403 if "not" in str(e) and "found" not in str(e) else 404, str(e)) from e

    @app.get("/api/source/tree")
    def source_tree() -> list[str]:
        return tree()


    @app.post("/api/tutor/explain")
    def explain(body: Explain) -> dict[str, Any]:
        if body.kind == "concept":
            return tutor.explain_concept(body.id or "", body.level, body.lang)
        if body.kind == "code":
            try:
                return tutor.explain_code(body.file or "", body.symbol, body.level, body.lang)
            except SourceAccessError as e:
                raise HTTPException(404, str(e)) from e
        m = missions.get(body.mission or "")
        step = next((s for s in m.steps if s.id == body.step), None) if m else None
        if not step:
            raise HTTPException(404, "step not found")
        lang = i18n.normalize(body.lang)
        out = {"source": "curated", "what": step.what.get(lang), "why": step.why.get(lang),
               "expected": step.expected.get(lang)}
        if step.concept:
            out["concept"] = tutor.explain_concept(step.concept, body.level, lang)
        return out


    @app.post("/api/tutor/ask")
    def ask(body: Ask) -> dict[str, Any]:
        return tutor.ask(body.question, body.context, body.lang)

    @app.get("/api/tutor/concepts")
    def concept_list() -> dict[str, Any]:
        return tutor.concepts()

    @app.get("/api/research")
    def research() -> list[dict[str, Any]]:
        return registry.load()

    @app.get("/api/i18n/missing")
    def missing() -> dict[str, list[str]]:
        return i18n.missing_keys()

    # ------------------------------------------------------------------ UI
    dist = REPO_ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app


def _err(e: Exception) -> Any:
    if isinstance(e, ValidationError):
        return [{"loc": list(x["loc"]), "msg": x["msg"]} for x in e.errors()]
    return str(e)


def _run_summary(r: Run) -> dict[str, Any]:
    d = asdict(r)
    d.pop("result", None)
    d["logs"] = d["logs"][-3:]
    return d


def _exp_summary(r: dict[str, Any]) -> dict[str, Any]:
    res = r.get("result") or {}
    agg = res.get("aggregate") if isinstance(res, dict) else None
    return {k: r.get(k) for k in ("id", "kind", "provenance", "created_at", "mission_id", "model", "engine", "params",
                                  "notes", "error", "hardware", "imported_from")} | {
        "headline": {k: (agg or {}).get(k, {}).get("median") for k in ("ttft_p50_ms", "e2e_p95_ms",
                                                                     "output_throughput_tps")} if agg else
        (res.get("timing") if isinstance(res, dict) and res.get("timing") else None)}


def get_app() -> FastAPI:
    return create_app()
