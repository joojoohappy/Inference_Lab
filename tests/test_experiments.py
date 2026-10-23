import copy

import pytest

from inference_lab.experiments import ExperimentStore, checksum, comparability, new_record
from inference_lab.provenance import Provenance


def bench(conc=1, tokens=16, prov=Provenance.LIVE_MEASURED, model="lab/tiny-random", engine="inference-lab-mini"):
    return new_record("benchmark", prov, model={"id": model, "revision": "r1"}, hardware={"cpu_model": "X"},
                      engine={"name": engine, "version": "1"},
                      params={"prompt": "p", "max_tokens": tokens, "concurrency": conc, "num_requests": 8,
                              "warmup_requests": 1, "trials": 3, "timeout_s": 120},
                      result={"aggregate": {"ttft_p50_ms": {"median": 10.0 * conc, "min": 9, "max": 11}}})


def test_records_are_append_only():
    st = ExperimentStore()
    r = st.save(bench())
    with pytest.raises(FileExistsError):
        st.save(r)


def test_notes_never_change_results():
    st = ExperimentStore()
    r = st.save(bench())
    out = st.annotate(r["id"], {"hypothesis": "h", "result": "hacked"})
    assert out["result"] == r["result"] and out["checksum"] == r["checksum"] and out["provenance"] == "LIVE_MEASURED"


def test_invalid_ids_rejected():
    with pytest.raises(ValueError):
        ExperimentStore().get("../../etc/passwd")


def test_import_verifies_checksum_and_relabels():
    st = ExperimentStore()
    rec = bench()
    imp = st.import_record(copy.deepcopy(rec))
    assert imp["provenance"] == "VERIFIED_IMPORTED" and imp["imported_from"] == rec["id"]
    tampered = copy.deepcopy(rec)
    tampered["result"]["aggregate"]["ttft_p50_ms"]["median"] = 1.0
    with pytest.raises(ValueError, match="checksum"):
        st.import_record(tampered)
    demo = new_record("benchmark", Provenance.DEMO_SAMPLE, result={})
    demo["hardware"], demo["params"] = {}, {}
    with pytest.raises(ValueError, match="measured"):
        st.import_record(demo)


def test_checksum_stable():
    assert checksum({"a": 1, "b": [1, 2]}) == checksum({"b": [1, 2], "a": 1})


def test_comparability_one_variable():
    c = comparability(bench(1), bench(4))
    assert c == {"differences": ["workload.concurrency"], "comparable": True, "warnings": []}


def test_comparability_confounded_and_demo():
    c = comparability(bench(1, 16), bench(4, 64))
    assert not c["comparable"] and "more_than_one_variable_changed" in c["warnings"]
    d = comparability(bench(1), bench(4, prov=Provenance.DEMO_SAMPLE))
    assert not d["comparable"] and "non_measured_provenance" in d["warnings"]
    e = comparability(bench(1), bench(1))
    assert "no_variable_changed" in e["warnings"]
