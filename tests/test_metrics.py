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
    assert {k: a["ttft_p50_ms"][k] for k in ("median", "min", "max", "trials")} == \
        {"median": 11, "min": 10, "max": 12, "trials": 3}
    c = compare(a, b)
    assert c["ttft_p50_ms"]["change_pct"] == pytest.approx(100.0)
    assert c["ttft_p50_ms"]["better"] is False and c["ttft_p50_ms"]["ranges_overlap"] is False
    assert c["output_throughput_tps"]["better"] is True and c["output_throughput_tps"]["ranges_overlap"] is True


def test_t_quantiles():
    from inference_lab.bench.metrics import t975

    assert t975(1) == pytest.approx(12.706) and t975(2) == pytest.approx(4.303)
    assert t975(2.9) == t975(2)  # fractional Welch df rounds down (wider interval)
    assert t975(10_000) == pytest.approx(1.96)


def test_mean_ci95_matches_hand_computation():
    from inference_lab.bench.metrics import mean_ci95

    m, lo, hi = mean_ci95([10.0, 11.0, 12.0])
    # mean 11, sd 1, se 1/sqrt(3), t(2) 4.303
    assert m == 11 and hi - m == pytest.approx(4.303 / 3 ** 0.5, rel=1e-4) and m - lo == pytest.approx(hi - m)
    assert mean_ci95([1.0]) is None


def test_diff_ci95_welch():
    from inference_lab.bench.metrics import diff_ci95

    d, lo, hi = diff_ci95([10.0, 11.0, 12.0], [20.0, 22.0, 25.0])
    # Welch: se^2 = 1/3 + 6.333/3, df ~ 2.6 -> t(2) = 4.303
    se = ((1 / 3) + (19 / 3 / 3)) ** 0.5
    assert d == pytest.approx(67 / 3 - 11)  # mean 22.333 - mean 11
    assert hi - d == pytest.approx(4.303 * se, rel=1e-4) and lo > 0
    assert diff_ci95([1.0], [2.0, 3.0]) is None
    assert diff_ci95([5.0, 5.0], [5.0, 5.0]) == (0.0, 0.0, 0.0)


def test_compare_marks_significance_from_the_interval():
    def trial(ttft, tps):
        return {"ttft_ms": {"p50": ttft, "p95": ttft}, "tpot_ms": {"p50": 1.0}, "e2e_ms": {"p50": 1.0, "p95": 1.0},
                "request_throughput_rps": 1.0, "output_throughput_tps": tps, "error_rate": 0.0}
    a = aggregate_trials([trial(10, 95), trial(11, 100), trial(12, 105)])
    b = aggregate_trials([trial(20, 99), trial(22, 101), trial(25, 104)])
    assert a["ttft_p50_ms"]["values"] == [10, 11, 12] and a["ttft_p50_ms"]["ci95"][0] < 11 < a["ttft_p50_ms"]["ci95"][1]
    c = compare(a, b)
    assert c["ttft_p50_ms"]["significant"] is True and c["ttft_p50_ms"]["trials"] == [3, 3]
    assert c["output_throughput_tps"]["significant"] is False  # 100 vs 101.3 with this spread: not shown
    one = aggregate_trials([trial(10, 95)])
    assert one["ttft_p50_ms"]["ci95"] is None and compare(one, one)["ttft_p50_ms"]["significant"] is None


def test_compare_works_on_records_saved_before_values_existed():
    old = {"ttft_p50_ms": {"median": 10.0, "min": 9.0, "max": 11.0, "trials": 3}}
    new = {"ttft_p50_ms": {"median": 20.0, "min": 19.0, "max": 21.0, "trials": 3}}
    row = compare(old, new)["ttft_p50_ms"]
    assert row["significant"] is None and row["diff_ci95"] is None and row["ranges_overlap"] is False
