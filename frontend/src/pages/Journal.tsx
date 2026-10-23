import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Empty, ProvenanceBadge, StatusBadge, Tabs, fmt } from "../components/common";
import { RunView } from "../components/RunView";
import { api, ApiError, waitForRun, type Run } from "../lib/api";
import { useApp } from "../lib/state";

const NOTE_FIELDS = ["hypothesis", "observation", "decision", "lesson"] as const;

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ExperimentDetail({ id }: { id: string }) {
  const { t } = useTranslation();
  const { bump } = useApp();
  const [rec, setRec] = useState<any>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.experiment(id).then((r) => { setRec(r); setNotes(r.notes ?? {}); }).catch((e) => setErr(e instanceof ApiError ? String(e.detail) : String(e)));
  }, [id]);
  if (err) return <div className="callout bad">{err}</div>;
  if (!rec) return <div className="dim">{t("common.loading")}</div>;
  const agg = rec.result?.aggregate;
  return (
    <section className="panel" data-testid="experiment-detail">
      <div className="row">
        <h2 className="mono" style={{ fontSize: 15 }}>{rec.id}</h2>
        <span className="spacer" />
        <ProvenanceBadge value={rec.provenance} />
        <button type="button" className="btn tiny" onClick={() => download(`${rec.id}.json`, JSON.stringify(rec, null, 2), "application/json")}>{t("journal.export")}</button>
      </div>
      <dl className="kv">
        <div><dt>{t("journal.kind")}</dt><dd>{t(`kinds.${rec.kind}`)}</dd></div>
        <div><dt>{t("garage.model")}</dt><dd className="mono">{rec.model?.id ?? "—"} {rec.model?.revision ? `@ ${rec.model.revision}` : ""}</dd></div>
        <div><dt>{t("journal.engine")}</dt><dd className="mono">{rec.engine?.name ?? "—"} {rec.engine?.version ?? ""}</dd></div>
        <div><dt>{t("journal.hardware")}</dt><dd className="mono small">{rec.hardware?.cpu_model ?? ""} {rec.hardware?.gpus?.length ? `· ${rec.hardware.gpus.join(", ")}` : `· ${t("lab.noGpu")}`}</dd></div>
        <div><dt>{t("journal.params")}</dt><dd className="mono small">{Object.entries(rec.params ?? {}).map(([k, v]) => `${k}=${typeof v === "string" && v.length > 30 ? v.slice(0, 30) + "…" : v}`).join("  ")}</dd></div>
        <div><dt>{t("journal.created")}</dt><dd>{new Date(rec.created_at * 1000).toLocaleString()}</dd></div>
        <div><dt>{t("journal.checksum")}</dt><dd className="mono small">{rec.checksum?.slice(0, 16)}…</dd></div>
        {rec.error && <div><dt>{t("run.errorDetail")}</dt><dd className="mono small bad">{rec.error}</dd></div>}
      </dl>
      {agg && (
        <table className="data" style={{ marginTop: 10 }}>
          <thead><tr><th>{t("arena.metric")}</th><th className="num">{t("journal.median")}</th><th className="num">min</th><th className="num">max</th></tr></thead>
          <tbody>{Object.entries(agg).map(([k, v]: [string, any]) => (
            <tr key={k}><td className="mono small">{k}</td><td className="num">{fmt(v.median)}</td><td className="num">{fmt(v.min)}</td><td className="num">{fmt(v.max)}</td></tr>
          ))}</tbody>
        </table>
      )}
      {!agg && rec.result?.timing && (
        <div className="mono small" style={{ marginTop: 8 }}>{Object.entries(rec.result.timing).map(([k, v]) => `${k}=${fmt(v)}`).join("  ")}</div>
      )}
      <h3>{t("journal.notes")}</h3>
      <p className="small dim">{t("journal.notesSub")}</p>
      {NOTE_FIELDS.map((f) => (
        <label key={f} className="field" style={{ marginBottom: 8 }}>{t(`journal.note.${f}`)}
          <textarea rows={2} value={notes[f] ?? ""} onChange={(e) => { setNotes({ ...notes, [f]: e.target.value }); setSaved(false); }} data-testid={`note-${f}`} />
        </label>
      ))}
      <div className="row">
        <button type="button" className="btn primary" onClick={async () => { await api.notes(id, notes); setSaved(true); bump(); }} data-testid="save-notes">{t("journal.save")}</button>
        {saved && <span className="small good" role="status">{t("journal.saved")}</span>}
      </div>
    </section>
  );
}

function ReportPanel({ exps }: { exps: any[] }) {
  const { t, i18n } = useTranslation();
  const { bump } = useApp();
  const [sel, setSel] = useState<string[]>([]);
  const [lang, setLang] = useState(i18n.language === "zh-TW" ? "zh-TW" : "en");
  const [decision, setDecision] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const gen = async () => {
    const r = await api.submit("report.generate", { experiment_ids: sel, lang, decision: decision || undefined });
    setRun(r);
    await waitForRun(r.id, setRun);
    bump();
  };
  const md: string | undefined = run?.result?.markdown;
  return (
    <section className="panel" aria-labelledby="rep-h">
      <h2 id="rep-h">{t("journal.report")}</h2>
      <p className="sub">{t("journal.reportSub")}</p>
      <fieldset className="checklist">
        <legend className="small dim">{t("journal.pick")}</legend>
        {exps.slice(0, 20).map((e) => (
          <label key={e.id} className="row small">
            <input type="checkbox" checked={sel.includes(e.id)} onChange={(ev) => setSel(ev.target.checked ? [...sel, e.id] : sel.filter((x) => x !== e.id))} />
            <span className="mono">{e.id}</span> <ProvenanceBadge value={e.provenance} />
          </label>
        ))}
      </fieldset>
      <div className="row" style={{ marginTop: 8 }}>
        <label className="field">{t("journal.reportLang")}
          <select value={lang} onChange={(e) => setLang(e.target.value)} data-testid="report-lang">
            <option value="en">English</option><option value="zh-TW">繁體中文</option>
          </select>
        </label>
      </div>
      <label className="field" style={{ marginTop: 8 }}>{t("journal.decision")}
        <textarea rows={3} value={decision} onChange={(e) => setDecision(e.target.value)} placeholder={t("journal.decisionPh")} />
      </label>
      <div className="row" style={{ marginTop: 8 }}>
        <button type="button" className="btn primary" disabled={!sel.length} onClick={gen} data-testid="report-generate">{t("journal.generate")}</button>
        {md && <button type="button" className="btn" onClick={() => download(`inference-lab-report-${lang}.md`, md, "text/markdown")}>{t("journal.downloadMd")}</button>}
      </div>
      {run && !md && <div style={{ marginTop: 10 }}><RunView run={run} /></div>}
      {md && (
        <>
          <div className="small dim" style={{ marginTop: 8 }}>{t("journal.claimed", { n: run!.result.claimed_ids.length })} · {t("journal.excluded", { n: run!.result.excluded_ids.length })}</div>
          <pre className="report" data-testid="report-md">{md}</pre>
        </>
      )}
    </section>
  );
}

export function JournalPage() {
  const { t } = useTranslation();
  const { route, refreshKey, bump } = useApp();
  const [tab, setTab] = useState<"experiments" | "runs">("experiments");
  const [exps, setExps] = useState<any[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [importMsg, setImportMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { api.experiments().then(setExps); api.runs().then(setRuns); }, [refreshKey]);
  const onImport = async (f: File | undefined) => {
    if (!f) return;
    try {
      const rec = await api.importExperiment(JSON.parse(await f.text()));
      setImportMsg({ ok: true, text: t("journal.imported", { id: rec.id }) });
      bump();
    } catch (e) {
      setImportMsg({ ok: false, text: `${t("journal.importFailed")}: ${e instanceof ApiError ? String(e.detail) : String(e)}` });
    }
  };
  return (
    <>
      <div className="grid two">
        <section className="panel">
          <Tabs value={tab} onChange={setTab} label={t("journal.tabs")} options={[{ value: "experiments", label: t("journal.experiments", { n: exps.length }) }, { value: "runs", label: t("journal.runs", { n: runs.length }) }]} />
          {tab === "experiments" ? (
            exps.length === 0 ? <Empty>{t("lab.noResults")}</Empty> : (
              <table className="data" data-testid="experiments-table"><tbody>
                {exps.map((e) => (
                  <tr key={e.id} aria-current={route.arg === e.id ? "true" : undefined}>
                    <td><a href={`#/journal/${e.id}`} className="mono small">{e.id}</a><div className="small dim">{t(`kinds.${e.kind}`)} · {e.model?.id ?? ""}</div></td>
                    <td><ProvenanceBadge value={e.provenance} /></td>
                    <td className="small">{e.notes?.hypothesis ? `“${e.notes.hypothesis.slice(0, 40)}”` : ""}</td>
                  </tr>
                ))}
              </tbody></table>
            )
          ) : (
            runs.length === 0 ? <Empty>{t("lab.noRuns")}</Empty> : (
              <>
                <p className="small dim">{t("journal.runsSub")}</p>
                <table className="data" data-testid="runs-table"><tbody>
                  {runs.map((r) => (
                    <tr key={r.id}>
                      <td className="mono small">{r.action}<div className="dim">{new Date(r.created_at * 1000).toLocaleString()}</div></td>
                      <td><StatusBadge run={r} /></td>
                      <td><ProvenanceBadge value={r.provenance} /></td>
                      <td className="small">{r.error ? <span className="mono bad">{r.error.code}</span> : r.experiment_id ? <a href={`#/journal/${r.experiment_id}`}>{t("journal.record")}</a> : ""}</td>
                    </tr>
                  ))}
                </tbody></table>
              </>
            )
          )}
          <div className="row" style={{ marginTop: 12 }}>
            <label className="btn tiny">{t("journal.import")}
              <input type="file" accept="application/json,.json" className="sr-only" onChange={(e) => onImport(e.target.files?.[0])} data-testid="import-file" />
            </label>
            <span className="small dim">{t("journal.importNote")}</span>
          </div>
          {importMsg && <div className={`callout ${importMsg.ok ? "" : "bad"}`} role="status">{importMsg.text}</div>}
        </section>
        {route.arg ? <ExperimentDetail key={route.arg} id={route.arg} /> : <section className="panel"><Empty>{t("journal.pickExp")}</Empty></section>}
      </div>
      <ReportPanel exps={exps} />
    </>
  );
}
