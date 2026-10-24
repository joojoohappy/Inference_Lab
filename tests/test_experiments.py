import copy

import pytest

from inference_lab.experiments import ExperimentStore, checksum, comparability, new_record, record_checksum
from inference_lab.provenance import Provenance, is_claimable


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


def test_import_checks_integrity_and_labels_unverified():
    st = ExperimentStore()
    rec = bench()
    imp = st.import_record(copy.deepcopy(rec))
    assert imp["provenance"] == "IMPORTED" and imp["imported_from"] == rec["id"]
    assert imp["import_check"] == {"schema": "valid", "result_checksum": "match", "record_checksum": "match",
                                   "origin": "not_verified"}
    tampered = copy.deepcopy(rec)
    tampered["result"]["aggregate"]["ttft_p50_ms"]["median"] = 1.0
    with pytest.raises(ValueError, match="checksum"):
        st.import_record(tampered)
    demo = new_record("benchmark", Provenance.DEMO_SAMPLE, result={})
    demo["hardware"], demo["params"] = {}, {}
    with pytest.raises(ValueError, match="measured"):
        st.import_record(demo)


def test_import_detects_edits_outside_result():
    st = ExperimentStore()
    for field, value in [("hardware", {"cpu_model": "Faster CPU"}), ("engine", {"name": "vllm", "version": "9"}),
                         ("params", {"concurrency": 64})]:
        rec = bench()
        rec[field] = value
        with pytest.raises(ValueError, match="record_checksum"):
            st.import_record(rec)


def test_import_of_older_export_without_record_checksum_says_so():
    rec = bench()
    del rec["record_checksum"]
    imp = ExperimentStore().import_record(rec)
    assert imp["provenance"] == "IMPORTED" and imp["import_check"]["record_checksum"] == "absent"


def test_a_forged_record_still_imports_but_never_as_a_measurement():
    """A checksum is not a signature: anyone can fabricate a record that passes. It must never be claimable."""
    forged = bench()
    forged["result"] = {"aggregate": {"ttft_p50_ms": {"median": 0.1, "min": 0.1, "max": 0.1}}}
    forged["checksum"] = checksum(forged["result"])
    forged["record_checksum"] = record_checksum(forged)
    imp = ExperimentStore().import_record(forged)
    assert imp["provenance"] == "IMPORTED" and not is_claimable(imp["provenance"])


def test_legacy_verified_imported_records_read_as_imported(lab_home):
    st = ExperimentStore()
    rec = bench()
    rec["provenance"] = "VERIFIED_IMPORTED"
    st.save(rec)
    assert st.get(rec["id"])["provenance"] == "IMPORTED"
    assert st.list()[0]["provenance"] == "IMPORTED"
    assert Provenance("VERIFIED_IMPORTED") is Provenance.IMPORTED


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


def test_comparability_flags_imported_and_unknown_identity():
    c = comparability(bench(1), bench(4, prov=Provenance.IMPORTED))
    assert not c["comparable"] and "imported_unverified" in c["warnings"]
    assert "non_measured_provenance" not in c["warnings"]
    a, b = bench(1), bench(4)
    b["model"]["revision"] = None
    b["engine"]["version"] = None
    c = comparability(a, b)
    assert not c["comparable"]
    assert {"unknown_model_revision", "unknown_engine_version"} <= set(c["warnings"])
