import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CompareBars, LatencyStrip, SweepChart } from "../components/Charts";
import { CommandBox, Empty, Modal, ProvenanceBadge, fmt } from "../components/common";
import { RunView } from "../components/RunView";
import { api, ApiError, waitForRun, type Run } from "../lib/api";
import { useApp } from "../lib/state";

const METRICS: { key: string; lowerBetter: boolean }[] = [
  { key: "ttft_p50_ms", lowerBetter: true },
  { key: "ttft_p95_ms", lowerBetter: true },
  { key: "tpot_p50_ms", lowerBetter: true },
  { key: "e2e_p50_ms", lowerBetter: true },
  { key: "e2e_p95_ms", lowerBetter: true },
  { key: "request_throughput_rps", lowerBetter: false },
  { key: "output_throughput_tps", lowerBetter: false },
];

/** Submit an allowlisted action, honouring the approval gate, and follow it to completion. */
function useAction() {
  const { bump } = useApp();
  const [run, setRun] = useState<Run | null>(null);
  const [pending, setPending] = useState<{ action: string; params: Record<string, unknown>; reason: string; command: string } | null>(null);
  const exec = async (action: string, params: Record<string, unknown>, approve = false) => {
    if (!approve) {
      const pv = await api.preview(action, params);
      if (pv.approval_required) { setPending({ action, params, reason: pv.approval_required, command: pv.command }); return null; }
    }
    setPending(null);
    const r = await api.submit(action, params, approve);
    setRun(r);
    const fin = await waitForRun(r.id, setRun);
    bump();
    return fin;
  };
  return { run, exec, pending, setPending };
}

type Kind = "mini" | "vllm" | "llamacpp-cpu" | "llamacpp-adreno";
const DEFAULT_MODEL: Record<Kind, string> = {
  mini: "lab/tiny-random", vllm: "lab/tiny-random",
  "llamacpp-cpu": "gguf:qwen3-4b-instruct-2507-Q4_0", "llamacpp-adreno": "gguf:qwen3-4b-instruct-2507-Q4_0",
};

function ServerPanel() {
  const { t } = useTranslation();
  const [kind, setKind] = useState<Kind>("mini");
  const [model, setModel] = useState("lab/tiny-random");
  const [health, setHealth] = useState<any>(null);
  const { run, exec, pending, setPending } = useAction();
  const refresh = async () => { const r = await exec("server.health", {}); setHealth(r?.result ?? null); };
  useEffect(() => { refresh(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, []);
  return (
    <section className="panel" aria-labelledby="srv-h">
      <div className="row">
        <h2 id="srv-h">{t("arena.server")}</h2>
        <span className="spacer" />
        <span className={`badge ${health?.healthy ? "live" : "notrun"}`} data-testid="server-state">{health?.healthy ? t("arena.healthy") : t("arena.noServer")}</span>
      </div>
      <p className="sub">{t("arena.serverSub")}</p>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <label className="field">{t("arena.engine")}
          <select value={kind} onChange={(e) => { const k = e.target.value as Kind; setKind(k); setModel(DEFAULT_MODEL[k]); }} data-testid="server-kind">
            <option value="mini">{t("arena.engineMini")}</option>
            <option value="vllm">{t("arena.engineVllm")}</option>
            <option value="llamacpp-cpu">{t("arena.engineLlamaCpu")}</option>
            <option value="llamacpp-adreno">{t("arena.engineLlamaAdreno")}</option>
          </select>
        </label>
        <label className="field">{t("garage.model")}<input className="mono" value={model} onChange={(e) => setModel(e.target.value)} /></label>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button type="button" className="btn primary" onClick={async () => { await exec("server.start", { model, kind }); refresh(); }} data-testid="server-start">{t("arena.start")}</button>
        <button type="button" className="btn" onClick={refresh}>{t("arena.health")}</button>
        <button type="button" className="btn" onClick={async () => { await exec("server.stop", {}); refresh(); }}>{t("arena.stop")}</button>
      </div>
      {health?.healthy && <div className="small mono dim" style={{ marginTop: 6 }}>{health.server?.base_url ?? ""} {health.server?.model ?? ""}</div>}
      {run && run.action !== "server.health" && <div style={{ marginTop: 10 }}><RunView run={run} /></div>}
      {pending && <ApprovalModal pending={pending} onClose={() => setPending(null)} onApprove={() => exec(pending.action, pending.params, true).then(refresh)} />}
    </section>
  );
}

function ApprovalModal({ pending, onClose, onApprove }: { pending: { reason: string; command: string }; onClose: () => void; onApprove: () => void }) {
  const { t } = useTranslation();
  return (
    <Modal title={t("approval.title")} onClose={onClose}>
      <p>{t(`approval.${pending.reason}`)}</p>
      <CommandBox command={pending.command} label={t("run.command")} />
      <p className="small dim">{t("approval.note")}</p>
      <div className="row"><span className="spacer" />
        <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
        <button type="button" className="btn primary" onClick={onApprove} data-testid="approve">{t("approval.approve")}</button>
      </div>
    </Modal>
  );
}

function BenchPanel() {
  const { t } = useTranslation();
  const [p, setP] = useState({ concurrency: 1, max_tokens: 16, num_requests: 8, warmup_requests: 1, trials: 2, hypothesis: "" });
  const { run, exec, pending, setPending } = useAction();
  const [preview, setPreview] = useState("");
  const params = { ...p, hypothesis: p.hypothesis || undefined };
  useEffect(() => { api.preview("bench.run", params).then((r) => setPreview(r.command)).catch(() => setPreview("")); }, [JSON.stringify(params)]); // eslint-disable-line react-hooks/exhaustive-deps
  const num = (k: keyof typeof p, min: number, max: number) => (
    <label className="field">{t(`arena.p.${k}`)}
      <input type="number" min={min} max={max} value={p[k] as number} onChange={(e) => setP({ ...p, [k]: Math.max(min, Math.min(max, +e.target.value || min)) })} data-testid={`bench-${k}`} />
    </label>
  );
  return (
    <section className="panel" aria-labelledby="bench-h">
      <h2 id="bench-h">{t("arena.bench")}</h2>
      <p className="sub">{t("arena.benchSub")}</p>
      <div className="grid four">
        {num("concurrency", 1, 64)}{num("max_tokens", 1, 512)}{num("num_requests", 1, 500)}{num("warmup_requests", 0, 20)}{num("trials", 1, 10)}
      </div>
      <label className="field" style={{ marginTop: 8 }}>{t("arena.p.hypothesis")}
        <input value={p.hypothesis} onChange={(e) => setP({ ...p, hypothesis: e.target.value })} placeholder={t("arena.hypothesisPh")} />
      </label>
      {preview && <div style={{ marginTop: 8 }}><CommandBox command={preview} label={t("missions.willRun")} /></div>}
      <div className="row" style={{ marginTop: 8 }}>
        <button type="button" className="btn primary" onClick={() => exec("bench.run", params)} data-testid="bench-run">{t("arena.runBench")}</button>
        <span className="small dim">{t("arena.benchNote")}</span>
      </div>
      {run && <div style={{ marginTop: 10 }}><RunView run={run} /></div>}
      {pending && <ApprovalModal pending={pending} onClose={() => setPending(null)} onApprove={() => exec(pending.action, pending.params, true)} />}
    </section>
  );
}

function ComparePanel() {
  const { t, i18n } = useTranslation();
  const { refreshKey } = useApp();
  const [exps, setExps] = useState<any[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [cmp, setCmp] = useState<any>(null);
  const [err, setErr] = useState("");
  const [raw, setRaw] = useState<{ a?: any; b?: any }>({});
  useEffect(() => {
    api.experiments().then((e) => {
      const benches = e.filter((x) => x.kind === "benchmark");
      setExps(benches);
      if (benches.length >= 2 && !a && !b) { setB(benches[0].id); setA(benches[1].id); }
    });
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const doCompare = async () => {
    setErr("");
    try {
      setCmp(await api.compare(a, b, i18n.language));
      const [ra, rb] = await Promise.all([api.experiment(a), api.experiment(b)]);
      setRaw({ a: ra, b: rb });
    } catch (e) { setErr(e instanceof ApiError ? String(e.detail) : String(e)); }
  };
  const label = (e: any) => `${e.id.slice(4, 19)} · c=${e.params?.concurrency ?? "?"} · ${e.params?.max_tokens ?? "?"} tok · ${t(`provenance.${e.provenance}.label`)}`;
  return (
    <section className="panel" aria-labelledby="cmp-h">
      <h2 id="cmp-h">{t("arena.compare")}</h2>
      <p className="sub">{t("arena.compareSub")}</p>
      {exps.length < 2 ? <Empty>{t("arena.needTwo")}</Empty> : (
        <>
          <div className="row" style={{ flexWrap: "wrap" }}>
            <label className="field">{t("charts.baseline")}
              <select value={a} onChange={(e) => setA(e.target.value)} data-testid="cmp-a">{exps.map((e) => <option key={e.id} value={e.id}>{label(e)}</option>)}</select>
            </label>
            <label className="field">{t("charts.candidate")}
              <select value={b} onChange={(e) => setB(e.target.value)} data-testid="cmp-b">{exps.map((e) => <option key={e.id} value={e.id}>{label(e)}</option>)}</select>
            </label>
            <button type="button" className="btn primary" onClick={doCompare} disabled={!a || !b || a === b} data-testid="cmp-run">{t("arena.compareBtn")}</button>
          </div>
          {err && <div className="callout bad">{err}</div>}
        </>
      )}
      {cmp && (
        <div data-testid="comparison" style={{ marginTop: 12 }}>
          <div className={`callout ${cmp.comparability.comparable ? "" : "warn"}`}>
            <strong>{cmp.comparability.comparable ? t("arena.comparable") : t("arena.notComparable")}</strong>
            <div className="small">{t("arena.differences")}: <span className="mono">{cmp.comparability.differences.join(", ") || "—"}</span></div>
            {cmp.comparability.warnings.map((w: string) => <div key={w} className="small">⚠ {t(`arena.warn.${w}`, { defaultValue: w })}</div>)}
          </div>
          <table className="data" style={{ marginTop: 10 }}>
            <thead><tr><th>{t("arena.metric")}</th><th className="num">{t("charts.baseline")}</th><th className="num">{t("charts.candidate")}</th><th className="num">{t("arena.change")}</th><th>{t("arena.noise")}</th></tr></thead>
            <tbody>
              {METRICS.map(({ key }) => {
                const m = cmp.metrics[key];
                if (!m) return null;
                return (
                  <tr key={key}>
                    <td className="mono small">{key}</td>
                    <td className="num">{fmt(m.baseline)}</td>
                    <td className="num">{fmt(m.candidate)}</td>
                    <td className={`num ${m.better === true ? "good" : m.better === false ? "bad" : ""}`}>{m.change_pct == null ? "—" : `${m.change_pct > 0 ? "+" : ""}${fmt(m.change_pct, 0)}%`}</td>
                    <td className="small">{m.ranges_overlap == null ? "" : m.ranges_overlap ? t("arena.overlap") : t("arena.separated")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <CompareBars rows={METRICS.filter((m) => cmp.metrics[m.key]).map((m) => ({ key: m.key, label: m.key, baseline: cmp.metrics[m.key].baseline, candidate: cmp.metrics[m.key].candidate, lowerBetter: m.lowerBetter }))} />
          <div className="grid two">
            {raw.a?.result?.raw_samples && <LatencyStrip raw={raw.a.result.raw_samples} title={`${t("charts.baseline")} · ${t("arena.perRequest")}`} />}
            {raw.b?.result?.raw_samples && <LatencyStrip raw={raw.b.result.raw_samples} title={`${t("charts.candidate")} · ${t("arena.perRequest")}`} />}
          </div>
          <h3>{t("arena.suggestions")}</h3>
          {cmp.suggestions.length === 0 ? <Empty>{t("arena.noSuggestions")}</Empty> : cmp.suggestions.map((s: any) => (
            <div key={s.id} className="callout" data-testid={`suggestion-${s.id}`} style={{ marginBottom: 8 }}>
              <div className="row"><strong>{t(`arena.sugg.${s.id}`, { defaultValue: s.id })}</strong><span className="spacer" /><span className="badge violet">{t(`claim.${s.claim_type}`)}</span></div>
              <dl className="kv">
                {(["evidence", "cause", "change", "impact", "drawbacks", "validation"] as const).map((f) => (
                  <div key={f}><dt>{t(`arena.sf.${f}`)}</dt><dd>{s[f]}</dd></div>
                ))}
              </dl>
            </div>
          ))}
          <p className="small dim">{t("arena.suggestNote")}</p>
        </div>
      )}
    </section>
  );
}

function SweepPanel() {
  const { t } = useTranslation();
  const { refreshKey } = useApp();
  const [demo, setDemo] = useState<any>(null);
  const [live, setLive] = useState<{ x: number; y: number }[]>([]);
  useEffect(() => {
    api.demo().then(setDemo);
    api.experiments().then((e) => {
      // Live points: measured benchmarks of the same model + max_tokens as the newest one, one point per concurrency (newest wins).
      const benches = e.filter((x) => x.kind === "benchmark" && (x.provenance === "LIVE_MEASURED" || x.provenance === "VERIFIED_IMPORTED") && x.headline?.ttft_p50_ms != null);
      if (!benches.length) { setLive([]); return; }
      const ref = benches[0];
      const pts = new Map<number, number>();
      for (const x of benches) {
        if (x.model?.id !== ref.model?.id || x.params?.max_tokens !== ref.params?.max_tokens) continue;
        const c = x.params?.concurrency;
        if (c && !pts.has(c)) pts.set(c, x.headline.ttft_p50_ms);
      }
      setLive([...pts.entries()].sort((p, q) => p[0] - q[0]).map(([x, y]) => ({ x, y })));
    });
  }, [refreshKey]);
  const series = [];
  if (demo) series.push({ label: `${t("arena.demoSeries")} (${t("provenance.DEMO_SAMPLE.label")})`, demo: true, color: "var(--amber)", points: demo.rows.map((r: any) => ({ x: r.concurrency, y: r.ttft_p50_ms })) });
  if (live.length) series.push({ label: `${t("arena.liveSeries")} (${t("provenance.LIVE_MEASURED.label")})`, demo: false, color: "var(--cyan)", points: live });
  return (
    <section className="panel" aria-labelledby="sweep-h">
      <div className="row"><h2 id="sweep-h">{t("arena.sweep")}</h2><span className="spacer" />{demo && <ProvenanceBadge value="DEMO_SAMPLE" />}{live.length > 0 && <ProvenanceBadge value="LIVE_MEASURED" />}</div>
      <p className="sub">{t("arena.sweepSub")}</p>
      <SweepChart series={series} />
      {demo && <p className="small dim">{t("arena.demoAssumptions")}: {demo.assumptions.join("; ")}</p>}
      {live.length < 2 && <p className="small">{t("arena.sweepHint")}</p>}
    </section>
  );
}

export function ArenaPage() {
  return (
    <>
      <div className="grid two">
        <ServerPanel />
        <BenchPanel />
      </div>
      <ComparePanel />
      <SweepPanel />
    </>
  );
}
