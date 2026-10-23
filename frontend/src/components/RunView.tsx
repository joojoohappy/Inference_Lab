import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Diagnosis, type Run } from "../lib/api";
import { useApp } from "../lib/state";
import { CommandBox, ProvenanceBadge, StatusBadge } from "./common";

/** Everything about one execution: command, live log, status, provenance, failure help, stuck check, raw output. */
export function RunView({ run, showRaw }: { run: Run; showRaw?: boolean }) {
  const { t, i18n } = useTranslation();
  const { mode } = useApp();
  const [help, setHelp] = useState<{ what: string; why: string; next: string } | null>(null);
  const [diag, setDiag] = useState<Diagnosis | null>(null);
  const running = run.status === "running" || run.status === "pending";

  useEffect(() => {
    setHelp(null);
    if (run.error?.code) api.errorHelp(run.error.code, i18n.language).then(setHelp).catch(() => setHelp(null));
  }, [run.error?.code, i18n.language]);

  useEffect(() => { if (!running) setDiag(null); }, [running]);

  const elapsed = run.started_at ? ((run.finished_at ?? Date.now() / 1000) - run.started_at).toFixed(1) : null;

  return (
    <div className="grid" style={{ gap: 10 }} data-testid="run-view" data-run-status={run.status}>
      <div className="row">
        <StatusBadge run={run} />
        <ProvenanceBadge value={run.provenance} />
        {elapsed && <span className="small dim">{t("run.elapsed", { s: elapsed })}</span>}
        {run.experiment_id && <a className="small" href={`#/journal/${run.experiment_id}`}>{t("run.evidence")}: {run.experiment_id}</a>}
        <span className="spacer" />
        {running && (
          <button type="button" className="btn tiny" onClick={() => api.diagnosis(run.id, i18n.language).then(setDiag)}>
            {t("run.isItStuck")}
          </button>
        )}
      </div>
      {running && (
        <div className={`progressbar ${run.progress == null ? "indeterminate" : ""}`} role="progressbar"
          aria-valuenow={run.progress == null ? undefined : Math.round(run.progress * 100)} aria-valuemin={0} aria-valuemax={100}
          aria-label={t("run.progress")}>
          <span style={run.progress == null ? undefined : { width: `${run.progress * 100}%` }} />
        </div>
      )}
      <CommandBox command={run.command} label={t("run.command")} />
      {run.approval && <div className="small dim">{t("run.approved", { reason: t(`approval.${run.approval.reason}`) })}</div>}
      <div className="log" aria-live="polite" aria-label={t("run.log")}>
        {run.logs.length === 0 && <span className="dim">{t("run.noLog")}</span>}
        {run.logs.map((l, i) => (
          <div key={i} className={`l-${l.level}`}>
            <span className="t">{new Date(l.t * 1000).toLocaleTimeString()}</span>{l.msg}
          </div>
        ))}
      </div>
      {diag && (
        <div className={`callout ${diag.state === "working" ? "ok" : "warn"}`} data-testid="diagnosis">
          <strong>{diag.summary}</strong>
          <h4 style={{ margin: "8px 0 2px" }}>{t("run.evidenceSeen")}</h4>
          <ul>{diag.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
          {diag.causes.length > 0 && (<><h4 style={{ margin: "8px 0 2px" }}>{t("run.possibleCauses")}</h4><ul>{diag.causes.map((e, i) => <li key={i}>{e}</li>)}</ul></>)}
          <h4 style={{ margin: "8px 0 2px" }}>{t("run.nextSteps")}</h4>
          <ul>{diag.next.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </div>
      )}
      {run.error && (
        <div className={`callout ${run.status === "failed" ? "err" : "warn"}`} role="status" data-testid="run-error">
          <div><strong>{help?.what ?? run.error.code}</strong> <code className="dim">{run.error.code}</code></div>
          {help && <p style={{ margin: "6px 0" }}><span className="muted">{t("run.why")}:</span> {help.why}</p>}
          {help && <p style={{ margin: "6px 0" }}><span className="muted">{t("run.tryNext")}:</span> {help.next}</p>}
          {run.error.detail && <details><summary>{t("run.errorDetail")}</summary><pre className="raw">{run.error.detail}</pre></details>}
        </div>
      )}
      {run.result != null && (
        <details open={showRaw ?? mode === "expert"}>
          <summary>{t("run.rawOutput")}</summary>
          <pre className="raw">{JSON.stringify(run.result, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
