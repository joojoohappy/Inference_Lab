"""Stream parsing: what counts as a successful request, and where token counts come from."""
import asyncio
import json

import httpx
import pytest

from inference_lab.bench.loadgen import BenchConfig, _one
from inference_lab.bench.metrics import summarize


def _sse(*events: object, done: bool = True) -> bytes:
    lines = [f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n" for e in events]
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _chunk(text: str) -> dict:
    return {"choices": [{"index": 0, "text": text, "finish_reason": None}]}


def _usage(n: int) -> dict:
    return {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": n, "total_tokens": 3 + n}}


def run_one(body: bytes, status: int = 200):
    transport = httpx.MockTransport(lambda req: httpx.Response(status, content=body,
                                                               headers={"content-type": "text/event-stream"}))
    cfg = BenchConfig(base_url="http://127.0.0.1:1", model="m", timeout_s=5)

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            return await _one(client, cfg)

    return asyncio.run(go())


def test_complete_stream_with_usage_is_ok_and_uses_server_token_count():
    s = run_one(_sse(_chunk("Hello"), _chunk(" wor"), _chunk("ld"), _usage(3)))
    assert s.ok and s.output_tokens == 3 and s.tokens_exact and s.ttft_s is not None


def test_multi_token_chunks_count_usage_not_chunks():
    s = run_one(_sse(_chunk("two tokens"), _chunk("and three more"), _usage(5)))
    assert s.ok and s.output_tokens == 5


def test_stream_without_done_marker_is_a_failure():
    s = run_one(_sse(_chunk("Hello"), _usage(1), done=False))
    assert not s.ok and s.error == "incomplete_stream"


def test_empty_stream_is_a_failure():
    assert run_one(_sse()).error == "empty_stream"
    assert run_one(_sse(_usage(0))).error == "empty_stream"
    assert run_one(b"").error == "incomplete_stream"


def test_malformed_or_error_chunks_fail_the_request():
    assert run_one(_sse("{not json", _chunk("x"), _usage(1))).error == "malformed_chunk"
    assert run_one(_sse({"error": {"message": "oom"}})).error == "server_error_in_stream"


def test_http_error_is_a_failure():
    assert run_one(b"nope", status=503).error == "http_503"


def test_missing_usage_marks_counts_inexact_and_hides_token_metrics():
    s = run_one(_sse(_chunk("a"), _chunk("b"), _chunk("c")))
    assert s.ok and not s.tokens_exact and s.output_tokens == 3 and s.tpot_s is None
    summary = summarize([s], wall_s=1.0)
    assert summary["token_count_source"] == "chunks"
    assert summary["output_throughput_tps"] is None and summary["output_tokens_total"] is None
    assert summary["output_chunks_total"] == 3 and summary["tpot_ms"]["n"] == 0
    assert summary["request_throughput_rps"] == pytest.approx(1.0)


def test_mixed_usage_reporting_hides_token_throughput():
    exact = run_one(_sse(_chunk("a"), _chunk("b"), _usage(2)))
    inexact = run_one(_sse(_chunk("a"), _chunk("b")))
    summary = summarize([exact, inexact], wall_s=1.0)
    assert summary["token_count_source"] == "mixed" and summary["output_throughput_tps"] is None
