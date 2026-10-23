import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";
import yaml from "highlight.js/lib/languages/yaml";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type SourceFile } from "../lib/api";
import { Tabs } from "./common";
import { AskTutor } from "./Tutor";

hljs.registerLanguage("python", python);
hljs.registerLanguage("yaml", yaml);
hljs.registerLanguage("json", json);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("typescript", typescript);

type Level = "simple" | "logic" | "design" | "tradeoffs";

/** Highlight a whole file, then split into lines while keeping open spans balanced per line. */
function highlightLines(code: string, language: string): string[] {
  const html = hljs.getLanguage(language) ? hljs.highlight(code, { language }).value : escapeHtml(code);
  const out: string[] = [];
  let open: string[] = [];
  for (const line of html.split("\n")) {
    const prefix = open.join("");
    const tags = line.match(/<span[^>]*>|<\/span>/g) || [];
    for (const tg of tags) {
      if (tg.startsWith("</")) open.pop(); else open.push(tg);
    }
    out.push(prefix + line + "</span>".repeat(open.length));
  }
  return out;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function SourceViewer({ path, symbol }: { path: string; symbol?: string | null }) {
  const { t, i18n } = useTranslation();
  const [file, setFile] = useState<SourceFile | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [level, setLevel] = useState<Level>("simple");
  const [expl, setExpl] = useState<any>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setFile(null); setErr(null); setSelected(null);
    api.source(path, symbol).then(setFile).catch((e) => setErr(String(e.message ?? e)));
  }, [path, symbol]);

  useEffect(() => {
    if (!symbol) { setExpl(null); return; }
    api.explain({ kind: "code", file: path, symbol, level, lang: i18n.language }).then(setExpl).catch(() => setExpl(null));
  }, [path, symbol, level, i18n.language]);

  const lines = useMemo(() => (file ? highlightLines(file.content, file.language) : []), [file]);

  useEffect(() => {
    if (file?.range && box.current) {
      const row = box.current.querySelector(`[data-line="${file.range[0]}"]`);
      row?.scrollIntoView({ block: "center" });
    }
  }, [file]);

  if (err) return <div className="callout err">{err}</div>;
  if (!file) return <div className="dim">{t("common.loading")}</div>;
  const [a, b] = file.range ?? [0, -1];
  const selectedText = selected ? file.content.split("\n")[selected - 1] : null;
  const rangeText = file.range ? file.content.split("\n").slice(a - 1, b).join("\n") : "";

  return (
    <div className="grid" style={{ gap: 12 }} data-testid="source-viewer">
      <div className="row">
        <span className="badge live" title={t("source.executedHelp")}>{t("source.executed")}</span>
        <code>{file.path}</code>
        {file.range && <span className="small dim">{symbol} · {t("source.lines", { a, b })}</span>}
      </div>
      <div className="source" ref={box} role="region" aria-label={t("source.codeRegion", { path: file.path })}>
        <table>
          <tbody>
            {lines.map((html, i) => {
              const n = i + 1;
              const cls = [n >= a && n <= b ? "hl" : "", selected === n ? "sel" : ""].join(" ");
              return (
                <tr key={n} data-line={n} className={cls} onClick={() => setSelected(n)}>
                  <td className="ln">{n}</td>
                  <td dangerouslySetInnerHTML={{ __html: html || " " }} />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {symbol && (
        <div className="panel">
          <div className="row">
            <h3 style={{ margin: 0 }}>{t("source.explain")}</h3>
            <span className="spacer" />
            <Tabs<Level> value={level} onChange={setLevel} label={t("source.explainLevel")} options={[
              { value: "simple", label: t("levels.simple") }, { value: "logic", label: t("levels.logic") },
              { value: "design", label: t("levels.design") }, { value: "tradeoffs", label: t("levels.tradeoffs") },
            ]} />
          </div>
          {expl && (
            <>
              <p data-testid="code-explanation">{expl.text}</p>
              <div className="small dim">{t(`tutor.source.${expl.source}`)}{expl.note ? ` · ${expl.note}` : ""}</div>
            </>
          )}
        </div>
      )}
      <AskTutor
        context={{ file: file.path, symbol, code: selectedText ?? rangeText }}
        suggestions={[t("source.q.line"), t("source.q.why"), t("source.q.change"), t("source.q.alternative"), t("source.q.docs")]}
        prefix={selected ? t("source.selectedLine", { n: selected }) : undefined}
      />
      <div className="callout small">
        <strong>{t("source.modifyTitle")}</strong> {t("source.modifyBody")}
      </div>
    </div>
  );
}
