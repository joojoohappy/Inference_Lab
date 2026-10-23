"""A deliberately small OpenAI-compatible completion server built on Transformers.

Why it exists: vLLM's optimized serving needs an NVIDIA GPU. This server lets a CPU-only
machine practise the *serving* workflow (start, health check, send HTTP requests, benchmark)
with the same client and benchmark code that talks to vLLM.

What it does NOT do: continuous batching, PagedAttention, or concurrent generation.
Requests are processed one at a time behind a lock. Under concurrency, requests queue.
That is a real, measurable bottleneck and the subject of Mission 06.

Run:  python -m inference_lab.serving.mini_server --model lab/tiny-random --port 8800
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field


class CompletionRequest(BaseModel):
    model: str | None = None
    prompt: str = Field(min_length=1, max_length=8000)
    max_tokens: int = Field(default=32, ge=1, le=512)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    stream: bool = False
    ignore_eos: bool = False
    stream_options: dict[str, Any] | None = None


class _QueueStreamer:
    """transformers BaseStreamer protocol: put() gets the prompt first, then one token per step."""

    def __init__(self, loop: asyncio.AbstractEventLoop, q: asyncio.Queue) -> None:
        self.loop, self.q, self.seen_prompt = loop, q, False

    def put(self, value) -> None:  # noqa: ANN001
        if not self.seen_prompt:
            self.seen_prompt = True
            return
        for tid in value.reshape(-1).tolist():
            self.loop.call_soon_threadsafe(self.q.put_nowait, ("token", tid))

    def end(self) -> None:
        self.loop.call_soon_threadsafe(self.q.put_nowait, ("end", None))


def create_app(model_ref: str) -> FastAPI:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from ..inference import resolve_local_model

    path = resolve_local_model(model_ref)
    tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    gen_lock = threading.Lock()  # one generation at a time: the documented bottleneck
    state = {"started": time.time(), "requests": 0, "in_flight": 0}

    app = FastAPI(title="Inference Lab mini server")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "model": model_ref, "device": device, "uptime_s": round(time.time() - state["started"], 1),
                "requests": state["requests"], "in_flight": state["in_flight"]}

    @app.get("/version")
    def version() -> dict[str, str]:  # same path vLLM exposes
        from .. import __version__

        return {"engine": "inference-lab-mini", "version": f"{__version__}+transformers-{transformers.__version__}",
                "transformers": transformers.__version__, "torch": torch.__version__}

    @app.get("/v1/models")
    def models() -> dict[str, Any]:
        return {"object": "list", "data": [{"id": model_ref, "object": "model", "owned_by": "local"}]}

    def _generate(req: CompletionRequest, streamer=None) -> tuple[list[int], int]:  # noqa: ANN001
        enc = tok(req.prompt, return_tensors="pt").to(device)
        kwargs: dict[str, Any] = {"max_new_tokens": req.max_tokens, "pad_token_id": tok.eos_token_id,
                                  "do_sample": req.temperature > 0}
        if req.temperature > 0:
            kwargs["temperature"] = req.temperature
        if req.ignore_eos:
            kwargs["min_new_tokens"] = req.max_tokens
        with gen_lock, torch.no_grad():
            state["in_flight"] += 1
            try:
                out = model.generate(**enc, streamer=streamer, **kwargs)
            finally:
                state["in_flight"] -= 1
        return out[0][enc["input_ids"].shape[1]:].tolist(), enc["input_ids"].shape[1]

    @app.post("/v1/completions")
    async def completions(req: CompletionRequest):  # noqa: ANN202
        if req.model and req.model != model_ref:
            raise HTTPException(404, f"model {req.model!r} is not served here")
        state["requests"] += 1
        rid = f"cmpl-{uuid.uuid4().hex[:12]}"
        if not req.stream:
            ids, n_prompt = await asyncio.to_thread(_generate, req)
            return JSONResponse({"id": rid, "object": "text_completion", "model": model_ref,
                                 "choices": [{"index": 0, "text": tok.decode(ids, skip_special_tokens=True),
                                              "finish_reason": "length" if len(ids) >= req.max_tokens else "stop"}],
                                 "usage": {"prompt_tokens": n_prompt, "completion_tokens": len(ids),
                                           "total_tokens": n_prompt + len(ids)}})

        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        streamer = _QueueStreamer(loop, q)
        task = asyncio.create_task(asyncio.to_thread(_generate, req, streamer))

        async def events():
            n = 0
            while True:
                kind, tid = await q.get()
                if kind == "end":
                    break
                n += 1
                chunk = {"id": rid, "object": "text_completion", "model": model_ref,
                         "choices": [{"index": 0, "text": tok.decode([tid]), "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
            _, n_prompt = await task
            final = {"id": rid, "object": "text_completion", "model": model_ref,
                     "choices": [{"index": 0, "text": "", "finish_reason": "length" if n >= req.max_tokens else "stop"}]}
            yield f"data: {json.dumps(final)}\n\n"
            if (req.stream_options or {}).get("include_usage"):
                usage = {"id": rid, "object": "text_completion", "model": model_ref, "choices": [],
                         "usage": {"prompt_tokens": n_prompt, "completion_tokens": n, "total_tokens": n_prompt + n}}
                yield f"data: {json.dumps(usage)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="lab/tiny-random")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8800)
    a = ap.parse_args()
    uvicorn.run(create_app(a.model), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
