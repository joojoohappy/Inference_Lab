from inference_lab.provenance import Provenance
from inference_lab.reports import build_report
from tests.test_experiments import bench


def test_only_measured_records_are_claimed():
    live, demo = bench(1), bench(4, prov=Provenance.DEMO_SAMPLE)
    failed = bench(2, prov=Provenance.FAILED)
    rep = build_report([live, demo, failed], "en", decision="Ship c=1")
    assert rep["claimed_ids"] == [live["id"]]
    assert set(rep["excluded_ids"]) == {demo["id"], failed["id"]}
    md = rep["markdown"]
    claimed_part = md.split(demo["id"])[0]
    assert live["id"] in claimed_part  # the claimed record appears before any excluded one
    assert "Ship c=1" in md


def test_report_language():
    en = build_report([bench(1)], "en")["markdown"]
    zh = build_report([bench(1)], "zh-TW")["markdown"]
    assert en != zh and any("一" <= ch <= "鿿" for ch in zh)
    assert "concurrency=1" in zh  # parameters stay untranslated


def test_decision_is_never_invented():
    md = build_report([bench(1), bench(4)], "en")["markdown"]
    assert "Ship" not in md


def test_imported_records_are_shown_apart_and_never_claimed():
    live, imp = bench(1), bench(4, prov=Provenance.IMPORTED)
    rep = build_report([live, imp], "en")
    assert rep["claimed_ids"] == [live["id"]] and rep["imported_ids"] == [imp["id"]]
    md = rep["markdown"]
    measured, rest = md.split("Imported results (origin not verified)", 1)
    assert live["id"] in measured and f"### `{imp['id']}`" not in measured
    assert f"### `{imp['id']}` [IMPORTED]" in rest
    assert "imported and its origin is not verified" in md  # comparison warning
    zh = build_report([imp], "zh-TW")["markdown"]
    assert "匯入的結果（來源未驗證）" in zh and "沒有選到任何現場實測" in zh


def test_report_states_the_confidence_interval():
    a, b = bench(1), bench(4)
    a["result"]["aggregate"]["ttft_p50_ms"].update(values=[10.0, 11.0, 12.0])
    b["result"]["aggregate"]["ttft_p50_ms"].update(values=[20.0, 22.0, 25.0], median=22.0, min=20, max=25)
    md = build_report([a, b], "en")["markdown"]
    assert "95% CI" in md and "excludes zero" in md and "3 vs 3 trials" in md
    zh = build_report([a, b], "zh-TW")["markdown"]
    assert "95% 信賴區間" in zh
