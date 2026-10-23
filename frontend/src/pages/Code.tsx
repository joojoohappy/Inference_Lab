import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Empty } from "../components/common";
import { SourceViewer } from "../components/SourceViewer";
import { api } from "../lib/api";
import { useApp } from "../lib/state";

/** Read-only explorer of the code that actually runs. Selecting a file updates the URL so links are shareable. */
export function CodePage() {
  const { t } = useTranslation();
  const { route, go } = useApp();
  const [files, setFiles] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  useEffect(() => { api.sourceTree().then(setFiles).catch(() => setFiles([])); }, []);
  const path = route.query.get("path");
  const symbol = route.query.get("symbol");
  const groups = useMemo(() => {
    const g: Record<string, string[]> = {};
    for (const f of files.filter((x) => x.toLowerCase().includes(filter.toLowerCase()))) {
      const dir = f.includes("/") ? f.slice(0, f.lastIndexOf("/")) : ".";
      (g[dir] ??= []).push(f);
    }
    return g;
  }, [files, filter]);
  return (
    <div className="grid code-layout">
      <nav className="panel" aria-label={t("code.files")} style={{ alignSelf: "start", maxHeight: "80vh", overflow: "auto" }}>
        <h2>{t("code.files")}</h2>
        <label className="field">{t("code.filter")}
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="bench/" data-testid="code-filter" />
        </label>
        {Object.entries(groups).map(([dir, fs]) => (
          <div key={dir} style={{ marginTop: 10 }}>
            <div className="small dim mono">{dir}/</div>
            <ul className="filelist">
              {fs.map((f) => (
                <li key={f}>
                  <a href={`#/code?path=${encodeURIComponent(f)}`} aria-current={f === path ? "page" : undefined} className="mono small"
                    onClick={(e) => { e.preventDefault(); go(`#/code?path=${encodeURIComponent(f)}`); }}>
                    {f.slice(f.lastIndexOf("/") + 1)}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div>
        <div className="callout" style={{ marginBottom: 12 }}>
          <strong>{t("code.legendTitle")}</strong>
          <ul className="small" style={{ margin: "6px 0 0 18px" }}>
            <li><span className="badge live">{t("source.executed")}</span> {t("code.legendExecuted")}</li>
            <li><span className="badge demo">{t("code.illustrative")}</span> {t("code.legendIllustrative")}</li>
            <li><span className="badge violet">{t("code.suggested")}</span> {t("code.legendSuggested")}</li>
          </ul>
          <p className="small dim" style={{ marginBottom: 0 }}>{t("code.readOnly")}</p>
        </div>
        {path ? <SourceViewer key={`${path}#${symbol}`} path={path} symbol={symbol} /> : <Empty>{t("code.pick")}</Empty>}
      </div>
    </div>
  );
}
