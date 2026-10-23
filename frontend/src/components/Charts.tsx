import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { fmt } from "./common";

/** Horizontal paired bars: baseline vs candidate for each metric. */
export function CompareBars({ rows }: { rows: { key: string; label: string; baseline: number | null; candidate: number | null; lowerBetter: boolean }[] }) {
  const { t } = useTranslation();
  return (
    <div className="viz" role="img" aria-label={t("charts.compareAria")}>
      <div className="legend"><span><i style={{ background: "var(--blue)" }} />{t("charts.baseline")}</span><span><i style={{ background: "var(--violet)" }} />{t("charts.candidate")}</span></div>
      {rows.map((r) => {
        const max = Math.max(r.baseline ?? 0, r.candidate ?? 0) || 1;
        return (
          <div key={r.key} style={{ margin: "10px 0" }}>
            <div className="row small"><span>{r.label}</span><span className="spacer" /><span className="dim">{r.lowerBetter ? t("charts.lowerBetter") : t("charts.higherBetter")}</span></div>
            {(["baseline", "candidate"] as const).map((k) => (
              <div key={k} className="row" style={{ gap: 8 }}>
                <div style={{ flex: 1, background: "var(--bg-2)", borderRadius: 6, height: 14 }}>
                  <div style={{ width: `${((r[k] ?? 0) / max) * 100}%`, height: "100%", borderRadius: 6, background: k === "baseline" ? "var(--blue)" : "var(--violet)" }} />
                </div>
                <span className="mono small" style={{ width: 80, textAlign: "right" }}>{fmt(r[k], 1)}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/** Dot strip of per-request latencies from raw samples, one row per trial. */
export function LatencyStrip({ raw, title }: { raw: (number | string | null)[][][]; title: string }) {
  const { t } = useTranslation();
  const trials = raw.map((rows) => rows.filter((r) => r[1] != null && r[4] == null).map((r) => ((r[1] as number) - (r[0] as number)) * 1000));
  const all = trials.flat();
  if (!all.length) return null;
  const max = Math.max(...all) * 1.05;
  const W = 600, rowH = 26, H = trials.length * rowH + 24;
  return (
    <figure className="viz" style={{ margin: 0 }}>
      <figcaption className="small muted">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("charts.stripAria")}>
        {trials.map((xs, i) => (
          <g key={i} transform={`translate(0 ${i * rowH + 6})`}>
            <text x={0} y={12} fill="var(--dim)" fontSize={11}>{t("charts.trial", { n: i + 1 })}</text>
            <line x1={60} x2={W - 10} y1={8} y2={8} stroke="var(--line)" />
            {xs.map((x, j) => <circle key={j} cx={60 + (x / max) * (W - 70)} cy={8} r={4} fill="var(--cyan)" fillOpacity={0.7} />)}
          </g>
        ))}
        <text x={60} y={H - 4} fill="var(--dim)" fontSize={11}>0 ms</text>
        <text x={W - 10} y={H - 4} fill="var(--dim)" fontSize={11} textAnchor="end">{fmt(max, 0)} ms (E2E)</text>
      </svg>
    </figure>
  );
}

/** Line chart for a concurrency sweep. Points carry their provenance; demo points are drawn dashed. */
export function SweepChart({ series }: { series: { label: string; demo: boolean; color: string; points: { x: number; y: number }[] }[] }) {
  const { t } = useTranslation();
  const W = 600, H = 240, P = 40;
  const xs = series.flatMap((s) => s.points.map((p) => p.x));
  const ys = series.flatMap((s) => s.points.map((p) => p.y));
  if (!xs.length) return null;
  const xmax = Math.max(...xs), ymax = Math.max(...ys) * 1.1 || 1;
  const sx = (x: number) => P + (Math.log2(x) / Math.log2(Math.max(2, xmax))) * (W - P - 10);
  const sy = (y: number) => H - P + 10 - (y / ymax) * (H - P - 10);
  return (
    <div className="viz">
      <div className="legend">{series.map((s) => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("charts.sweepAria")}>
        <line x1={P} x2={W - 10} y1={H - P + 10} y2={H - P + 10} stroke="var(--line-2)" />
        <line x1={P} x2={P} y1={10} y2={H - P + 10} stroke="var(--line-2)" />
        {[...new Set(xs)].map((x) => <text key={x} x={sx(x)} y={H - 14} fill="var(--dim)" fontSize={11} textAnchor="middle">{x}</text>)}
        <text x={W / 2} y={H - 1} fill="var(--dim)" fontSize={11} textAnchor="middle">{t("charts.concurrency")}</text>
        <text x={4} y={14} fill="var(--dim)" fontSize={11}>{fmt(ymax, 0)}</text>
        {series.map((s) => (
          <g key={s.label}>
            <polyline fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.demo ? "6 5" : undefined}
              points={s.points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")} />
            {s.points.map((p, i) => <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={4} fill={s.color}><title>{`${p.x}: ${fmt(p.y)}`}</title></circle>)}
          </g>
        ))}
      </svg>
    </div>
  );
}

/** Interactive: contiguous KV-cache reservation vs paged blocks (illustrative arithmetic, not a measurement). */
export function KvCacheViz() {
  const { t } = useTranslation();
  const [reqs, setReqs] = useState(4);
  const [maxLen, setMaxLen] = useState(64);
  const blockSize = 8;
  const lengths = useMemo(() => Array.from({ length: reqs }, (_, i) => Math.max(4, Math.round(maxLen * (0.25 + ((i * 37) % 70) / 100)))), [reqs, maxLen]);
  const contiguous = reqs * maxLen;
  const used = lengths.reduce((a, b) => a + b, 0);
  const paged = lengths.reduce((a, l) => a + Math.ceil(l / blockSize) * blockSize, 0);
  const cell = 6;
  return (
    <div className="panel" data-testid="kv-viz">
      <div className="row"><h2>{t("viz.kv.title")}</h2><span className="badge demo">{t("viz.illustrative")}</span></div>
      <p className="sub">{t("viz.kv.sub")}</p>
      <div className="row">
        <label className="field">{t("viz.kv.requests", { n: reqs })}<input type="range" min={1} max={8} value={reqs} onChange={(e) => setReqs(+e.target.value)} /></label>
        <label className="field">{t("viz.kv.maxLen", { n: maxLen })}<input type="range" min={16} max={128} step={8} value={maxLen} onChange={(e) => setMaxLen(+e.target.value)} /></label>
      </div>
      <div className="grid two">
        {(["contiguous", "paged"] as const).map((kind) => (
          <div key={kind}>
            <h3>{t(`viz.kv.${kind}`)}</h3>
            <svg viewBox={`0 0 ${128 * cell + 4} ${reqs * (cell * 2 + 4) + 4}`} role="img" aria-label={t(`viz.kv.${kind}`)}>
              {lengths.map((l, r) => {
                const reserved = kind === "contiguous" ? maxLen : Math.ceil(l / blockSize) * blockSize;
                return (
                  <g key={r} transform={`translate(2 ${r * (cell * 2 + 4) + 2})`}>
                    <rect width={reserved * cell} height={cell * 2} fill="rgba(248,113,113,0.25)" rx={2} />
                    <rect width={l * cell} height={cell * 2} fill="var(--cyan)" rx={2} />
                    {kind === "paged" && Array.from({ length: reserved / blockSize }, (_, b) => <line key={b} x1={b * blockSize * cell} x2={b * blockSize * cell} y1={0} y2={cell * 2} stroke="var(--bg)" />)}
                  </g>
                );
              })}
            </svg>
            <div className="small muted">{t("viz.kv.waste", { pct: fmt((1 - used / (kind === "contiguous" ? contiguous : paged)) * 100, 0) })}</div>
          </div>
        ))}
      </div>
      <div className="legend"><span><i style={{ background: "var(--cyan)" }} />{t("viz.kv.usedLegend")}</span><span><i style={{ background: "rgba(248,113,113,0.5)" }} />{t("viz.kv.wasteLegend")}</span></div>
    </div>
  );
}

/** Interactive: toy model of latency vs throughput for a serial server vs a batching server. */
export function LatencyThroughputViz() {
  const { t } = useTranslation();
  const [c, setC] = useState(4);
  const service = 40; // ms per request when alone (assumption)
  const serial = { latency: service * c, tput: 1000 / service };
  // Batching toy model: a step costs a bit more with each extra request in the batch (assumption: +15%).
  const batchStep = service * (1 + 0.15 * (c - 1));
  const batched = { latency: batchStep, tput: (1000 / batchStep) * c };
  return (
    <div className="panel" data-testid="lt-viz">
      <div className="row"><h2>{t("viz.lt.title")}</h2><span className="badge demo">{t("viz.illustrative")}</span></div>
      <p className="sub">{t("viz.lt.sub")}</p>
      <label className="field">{t("viz.lt.concurrency", { n: c })}<input type="range" min={1} max={16} value={c} onChange={(e) => setC(+e.target.value)} /></label>
      <table className="data" style={{ marginTop: 10 }}>
        <thead><tr><th /><th>{t("viz.lt.latency")}</th><th>{t("viz.lt.throughput")}</th></tr></thead>
        <tbody>
          <tr><td>{t("viz.lt.serial")}</td><td className="num">{fmt(serial.latency, 0)} ms</td><td className="num">{fmt(serial.tput, 1)} req/s</td></tr>
          <tr><td>{t("viz.lt.batched")}</td><td className="num">{fmt(batched.latency, 0)} ms</td><td className="num">{fmt(batched.tput, 1)} req/s</td></tr>
        </tbody>
      </table>
      <p className="small dim">{t("viz.lt.assumptions")}</p>
    </div>
  );
}
