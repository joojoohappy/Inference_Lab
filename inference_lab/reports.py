"""Engineering report generation (Mission 07). Deterministic: same records in, same report out.

Rules enforced here:
  * Only LIVE_MEASURED and VERIFIED_IMPORTED numbers appear under "Measured results".
  * DEMO_SAMPLE, NOT_RUN and FAILED records are listed separately with their label.
  * Every number is followed by the id of the experiment it came from.
  * Limitations are derived from the records themselves (trial count, hardware, model).
"""

from __future__ import annotations

import time
from typing import Any

from .experiments import compare_records
from .i18n import t
from .provenance import is_claimable


def _fmt(x: Any, nd: int = 1) -> str:
    return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def _limitations(recs: list[dict[str, Any]], lang: str) -> list[str]:
    out = []
    benches = [r for r in recs if r["kind"] == "benchmark"]
    if any((r.get("params") or {}).get("trials", 0) < 3 for r in benches):
        out.append(t(lang, "report.lim.few_trials"))
    if any(not (r.get("hardware") or {}).get("gpus") for r in recs):
        out.append(t(lang, "report.lim.cpu_only"))
    if any((r.get("model") or {}).get("id") == "lab/tiny-random" for r in recs):
        out.append(t(lang, "report.lim.random_model"))
    if any((r.get("engine") or {}).get("name") == "inference-lab-mini" for r in benches):
        out.append(t(lang, "report.lim.mini_server"))
    out.append(t(lang, "report.lim.single_machine"))
    return out


def _observations(cmp: dict[str, Any], lang: str) -> list[str]:
    obs = []
    for k, row in cmp["metrics"].items():
        if row.get("change_pct") is None:
            continue
        key = "report.obs.noise" if row.get("ranges_overlap") else "report.obs.change"
        obs.append(t(lang, key, metric=k, baseline=_fmt(row["baseline"], 2), candidate=_fmt(row["candidate"], 2),
                     pct=_fmt(row["change_pct"], 1)))
    return obs


def build_report(recs: list[dict[str, Any]], lang: str = "en", decision: str | None = None) -> dict[str, Any]:
    claim = [r for r in recs if is_claimable(r["provenance"])]
    excluded = [r for r in recs if not is_claimable(r["provenance"])]
    L: list[str] = [f"# {t(lang, 'report.title')}", "",
                    f"_{t(lang, 'report.generated', when=time.strftime('%Y-%m-%d %H:%M:%S'))}_", ""]

    L += [f"## {t(lang, 'report.methodology')}", "", t(lang, "report.methodology_body"), ""]
    benches = [r for r in claim if r["kind"] == "benchmark"]
    for r in benches:
        p = r.get("params") or {}
        L.append(f"- `{r['id']}`: concurrency={p.get('concurrency')}, max_tokens={p.get('max_tokens')}, "
                 f"num_requests={p.get('num_requests')}, warmup={p.get('warmup_requests')}, trials={p.get('trials')}")
    L.append("")

    L += [f"## {t(lang, 'report.environment')}", ""]
    seen = set()
    for r in claim:
        hw = r.get("hardware") or {}
        key = str(hw)
        if key in seen or not hw:
            continue
        seen.add(key)
        L.append(f"- CPU: {hw.get('cpu_model')} ({hw.get('logical_cores')} threads), RAM {hw.get('ram_total_gb')} GB, "
                 f"GPU: {', '.join(hw.get('gpus') or []) or t(lang, 'report.none')}")
    for r in claim:
        e, m = r.get("engine") or {}, r.get("model") or {}
        if e or m:
            L.append(f"- `{r['id']}`: model `{m.get('id')}` @ `{m.get('revision')}`, engine {e.get('name')} {e.get('version')}")
    L.append("")

    L += [f"## {t(lang, 'report.results')}", ""]
    if not claim:
        L += [t(lang, "report.no_measurements"), ""]
    for r in benches:
        a = (r.get("result") or {}).get("aggregate") or {}
        L += [f"### `{r['id']}` [{r['provenance']}]", "",
              f"| {t(lang, 'report.metric')} | median | min | max |", "|---|---|---|---|"]
        for k, v in a.items():
            L.append(f"| {k} | {_fmt(v.get('median'), 2)} | {_fmt(v.get('min'), 2)} | {_fmt(v.get('max'), 2)} |")
        res = (r.get("result") or {}).get("resources") or {}
        L += ["", f"- server_rss_mb_peak: {_fmt(res.get('server_rss_mb_peak'))}; "
                  f"gpu_vram_used_mb_peak: {_fmt(res.get('gpu_vram_used_mb_peak'))}", ""]
    for r in [x for x in claim if x["kind"] == "inference"]:
        tm = (r.get("result") or {}).get("timing") or {}
        L.append(f"- `{r['id']}` [{r['provenance']}] inference: load {_fmt(tm.get('load_ms'))} ms, "
                 f"TTFT {_fmt(tm.get('ttft_ms'))} ms, TPOT {_fmt(tm.get('tpot_ms'), 2)} ms, "
                 f"{_fmt(tm.get('output_tokens_per_s'))} tok/s")
    L.append("")

    comparison = None
    if len(benches) >= 2:
        comparison = compare_records(benches[-1], benches[0]) if benches[0]["created_at"] > benches[-1]["created_at"] \
            else compare_records(benches[0], benches[-1])
        c = comparison["comparability"]
        L += [f"## {t(lang, 'report.comparison')}", "",
              t(lang, "report.cmp_header", baseline=comparison["baseline_id"], candidate=comparison["candidate_id"]),
              "", f"- {t(lang, 'report.variables_changed')}: {', '.join(c['differences']) or '-'}"]
        for w in c["warnings"]:
            L.append(f"- ⚠ {t(lang, 'report.warn.' + w)}")
        L.append("")
        L += [f"### {t(lang, 'report.observations')}", ""] + [f"- {o}" for o in _observations(comparison, lang)] + [""]

    L += [f"## {t(lang, 'report.limitations')}", ""] + [f"- {x}" for x in _limitations(recs, lang)] + [""]
    L += [f"## {t(lang, 'report.decision')}", "",
          (f"> {decision}" if decision else t(lang, "report.no_decision")), "",
          f"_{t(lang, 'report.decision_note')}_", ""]
    if excluded:
        L += [f"## {t(lang, 'report.excluded')}", "", t(lang, "report.excluded_body"), ""]
        for r in excluded:
            L.append(f"- `{r['id']}` [{r['provenance']}] {r['kind']}" + (f": {r.get('error')}" if r.get("error") else ""))
        L.append("")
    L += [f"## {t(lang, 'report.provenance')}", "", "| id | kind | provenance | checksum |", "|---|---|---|---|"]
    for r in recs:
        L.append(f"| `{r['id']}` | {r['kind']} | {r['provenance']} | `{r.get('checksum', '')[:12]}` |")
    return {"markdown": "\n".join(L) + "\n", "claimed_ids": [r["id"] for r in claim],
            "excluded_ids": [r["id"] for r in excluded], "comparison": comparison, "lang": lang}
