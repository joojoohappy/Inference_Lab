import pytest

from inference_lab.bench.metrics import RequestSample, aggregate_trials, compare, dist, percentile, summarize


def test_percentile_linear_interpolation():
    xs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile(xs, 50) == 5.5
    assert percentile(xs, 0) == 1 and percentile(xs, 100) == 10
    assert percentile(xs, 95) == pytest.approx(9.55)
    assert percentile([], 50) is None
    with pytest.raises(ValueError):
        percentile([1], 101)


def test_percentile_is_deterministic_and_order_free():
    xs = [5.0, 1.0, 3.0, 9.0, 7.0]
    assert percentile(xs, 90) == percentile(sorted(xs), 90) == percentile(list(reversed(xs)), 90)


def test_dist_ignores_missing():
    d = dist([1.0, None, 3.0])
    assert d["n"] == 2 and d["mean"] == 2.0


def test_summarize_counts_failures_and_tpot():
    samples = [RequestSample(0.0, 1.0, 0.1, 10), RequestSample(0.0, 2.0, 0.2, 10),
               RequestSample(0.0, None, None, 0, error="timeout")]
    s = summarize(samples, wall_s=2.0)
    assert s["succeeded"] == 2 and s["failed"] == 1 and s["errors"] == {"timeout": 1}
    assert s["error_rate"] == pytest.approx(1 / 3)
    assert s["tpot_ms"]["p50"] == pytest.approx(((0.9 / 9) + (1.8 / 9)) / 2 * 1000)
    assert s["output_throughput_tps"] == 10.0


def test_aggregate_and_compare():
    def trial(ttft, tps):
        return {"ttft_ms": {"p50": ttft, "p95": ttft}, "tpot_ms": {"p50": 1.0}, "e2e_ms": {"p50": 1.0, "p95": 1.0},
                "request_throughput_rps": 1.0, "output_throughput_tps": tps, "error_rate": 0.0}
    a = aggregate_trials([trial(10, 95), trial(11, 100), trial(12, 105)])
    b = aggregate_trials([trial(20, 99), trial(22, 101), trial(25, 104)])
    assert a["ttft_p50_ms"] == {"median": 11, "min": 10, "max": 12, "trials": 3}
    c = compare(a, b)
    assert c["ttft_p50_ms"]["change_pct"] == pytest.approx(100.0)
    assert c["ttft_p50_ms"]["better"] is False and c["ttft_p50_ms"]["ranges_overlap"] is False
    assert c["output_throughput_tps"]["better"] is True and c["output_throughput_tps"]["ranges_overlap"] is True
