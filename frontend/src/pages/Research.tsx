import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { KvCacheViz, LatencyThroughputViz } from "../components/Charts";
import { Empty } from "../components/common";
import { ConceptExplainer } from "../components/Tutor";
import { api } from "../lib/api";
import { useLoc, type Loc } from "../lib/loc";
import { useApp } from "../lib/state";

interface Rec {
  id: string; title: string; authors: string[]; kind: string; year?: number; venue?: string; url: string;
  concepts: string[]; related_missions: string[]; verification: { method: string; date?: string; checked?: string[]; note?: string };
  beginner: Loc; engineering: Loc; contributions: Loc; practical: Loc; limitations: Loc;
}

const SECTIONS = ["beginner", "engineering", "contributions", "practical", "limitations"] as const;

export function ResearchPage() {
  const { t } = useTranslation();
  const loc = useLoc();
  const { route, go } = useApp();
  const [recs, setRecs] = useState<Rec[]>([]);
  const [concepts, setConcepts] = useState<Record<string, any>>({});
  const [teach, setTeach] = useState<string | null>(null);
  useEffect(() => {
    api.research().then(setRecs);
    api.concepts().then(setConcepts).catch(() => setConcepts({}));
  }, []);
  const concept = route.query.get("concept");
  const selected = route.arg ? recs.find((r) => r.id === route.arg) : null;
  const shown = concept ? recs.filter((r) => r.concepts.includes(concept)) : recs;
  const allConcepts = [...new Set(recs.flatMap((r) => r.concepts))].sort();

  return (
    <>
      <div className="callout">{t("research.intro")}</div>
      <div className="row" role="group" aria-label={t("research.filter")} style={{ margin: "12px 0", flexWrap: "wrap" }}>
        <button type="button" className="btn tiny" aria-pressed={!concept} onClick={() => go("#/research")}>{t("research.all")}</button>
        {allConcepts.map((c) => (
          <button key={c} type="button" className="btn tiny" aria-pressed={concept === c} onClick={() => go(`#/research?concept=${c}`)}>
            {concepts[c] ? loc(concepts[c].title) : c}
          </button>
        ))}
      </div>
      <div className="grid two">
        <section className="panel" aria-labelledby="sources-h">
          <h2 id="sources-h">{t("research.sources", { n: shown.length })}</h2>
          {shown.length === 0 ? <Empty>{t("research.none")}</Empty> : (
            <ul className="reslist">
              {shown.map((r) => (
                <li key={r.id}>
                  <a href={`#/research/${r.id}`} aria-current={selected?.id === r.id ? "true" : undefined} data-testid={`res-${r.id}`}>{r.title}</a>
                  <div className="small dim">
                    {t(`research.kind.${r.kind}`, { defaultValue: r.kind })} · {r.year ?? ""} {r.venue ? `· ${r.venue}` : ""}
                    {" "}<span className={`badge ${r.verification.method === "fetched" ? "live" : "demo"}`}>{t(`research.verification.${r.verification.method}`)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel" aria-live="polite">
          {!selected ? <Empty>{t("research.pick")}</Empty> : (
            <article data-testid="research-detail">
              <h2>{selected.title}</h2>
              <div className="small muted">{selected.authors.join(", ")}</div>
              <div className="small dim">{selected.venue} {selected.year ? `(${selected.year})` : ""}</div>
              <p><a href={selected.url} target="_blank" rel="noreferrer noopener" className="mono small">{selected.url}</a></p>
              <div className="small">
                <span className={`badge ${selected.verification.method === "fetched" ? "live" : "demo"}`}>{t(`research.verification.${selected.verification.method}`)}</span>{" "}
                {selected.verification.date && t("research.checkedOn", { date: selected.verification.date, fields: (selected.verification.checked ?? []).join(", ") })}
                {selected.verification.note && <div className="dim">{selected.verification.note}</div>}
              </div>
              {SECTIONS.map((s) => (
                <div key={s} style={{ marginTop: 10 }}>
                  <h3>{t(`research.section.${s}`)}</h3>
                  <p>{loc(selected[s])}</p>
                </div>
              ))}
              <h3>{t("research.concepts")}</h3>
              <div className="row" style={{ flexWrap: "wrap" }}>
                {selected.concepts.map((c) => (
                  <button key={c} type="button" className="btn tiny" onClick={() => setTeach(c)} aria-pressed={teach === c}>
                    {t("tutor.teachMe")}: {concepts[c] ? loc(concepts[c].title) : c}
                  </button>
                ))}
              </div>
              {teach && selected.concepts.includes(teach) && <div style={{ marginTop: 10 }}><ConceptExplainer key={teach} concept={teach} /></div>}
              <h3>{t("research.missions")}</h3>
              <ul>
                {selected.related_missions.map((m) => <li key={m}><a href={`#/missions/${m}`}>{m}</a></li>)}
              </ul>
            </article>
          )}
        </section>
      </div>
      <h2 style={{ marginTop: 20 }}>{t("research.visuals")}</h2>
      <div className="grid two">
        <KvCacheViz />
        <LatencyThroughputViz />
      </div>
    </>
  );
}
