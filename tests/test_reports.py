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
