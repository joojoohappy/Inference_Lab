import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../lib/api";
import { Tabs } from "./common";

type Level = "simple" | "logic" | "design" | "tradeoffs";

/** "Teach me this": curated, progressive explanation of one concept in the selected language. */
export function ConceptExplainer({ concept, initial = "simple" }: { concept: string; initial?: Level }) {
  const { t, i18n } = useTranslation();
  const [level, setLevel] = useState<Level>(initial);
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    api.explain({ kind: "concept", id: concept, level, lang: i18n.language }).then(setData).catch(() => setData(null));
  }, [concept, level, i18n.language]);
  if (!data) return null;
  return (
    <div className="panel" data-testid="concept-explainer">
      <div className="row">
        <span className="badge violet">{t("tutor.teachMe")}</span>
        <strong>{data.title}</strong>
        <span className="spacer" />
        <Tabs<Level> value={level} onChange={setLevel} label={t("source.explainLevel")} options={[
          { value: "simple", label: t("levels.simple") }, { value: "logic", label: t("levels.logic") },
          { value: "design", label: t("levels.design") }, { value: "tradeoffs", label: t("levels.tradeoffs") },
        ]} />
      </div>
      <p>{data.text}</p>
      {data.analogy && level === "simple" && <p className="muted"><em>{t("tutor.analogy")}:</em> {data.analogy}</p>}
      <div className="row small dim">
        <span>{t(`tutor.source.${data.source}`)}</span>
        <span>·</span>
        <span>{t(`claim.${data.claim_type}`)}</span>
        {data.references?.length > 0 && (<><span>·</span>{data.references.map((r: string) => <a key={r} href={`#/research/${r}`}>{r}</a>)}</>)}
      </div>
    </div>
  );
}

/** Free-form question. Uses the configured AI provider if any; otherwise curated matches. Never affects completion. */
export function AskTutor({ context, suggestions = [], prefix }: { context: Record<string, unknown>; suggestions?: string[]; prefix?: string }) {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  const [ans, setAns] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    try { setAns(await api.ask(prefix ? `${prefix} ${question}` : question, context, i18n.language)); }
    finally { setBusy(false); }
  };
  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>{t("tutor.ask")}</h3>
      {prefix && <div className="small dim">{prefix}</div>}
      <div className="row" style={{ margin: "6px 0" }}>
        {suggestions.map((s) => <button key={s} type="button" className="btn tiny" onClick={() => { setQ(s); void ask(s); }}>{s}</button>)}
      </div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); void ask(q); }}>
        <input type="text" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("tutor.placeholder")} aria-label={t("tutor.ask")} style={{ flex: 1 }} />
        <button className="btn" type="submit" disabled={busy}>{busy ? t("common.loading") : t("tutor.askButton")}</button>
      </form>
      {ans && (
        <div className={`callout ${ans.source === "ai" ? "warn" : ""}`} style={{ marginTop: 10 }} data-testid="tutor-answer">
          <div className="small dim">{t(`tutor.source.${ans.source}`)}{ans.provider ? ` · ${ans.provider}` : ""}</div>
          <p style={{ whiteSpace: "pre-wrap" }}>{ans.text}</p>
          {ans.warning && <div className="small">{ans.warning}</div>}
          {ans.matches?.length > 0 && (
            <ul>{ans.matches.map((m: any) => <li key={m.id}><a href={`#/research?concept=${m.id}`}>{m.title}</a></li>)}</ul>
          )}
        </div>
      )}
    </div>
  );
}
