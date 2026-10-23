import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, CommandBox, Empty } from "../components/common";
import { RunView } from "../components/RunView";
import { SourceViewer } from "../components/SourceViewer";
import { ConceptExplainer } from "../components/Tutor";
import { api, waitForRun, type CheckResult, type Mission, type MissionsResponse, type Run, type Step } from "../lib/api";
import { useLoc } from "../lib/loc";
import { useApp } from "../lib/state";

let actionsCache: Promise<any[]> | null = null;
export const getActions = () => (actionsCache ??= fetch("/api/actions").then((r) => r.json()));

export function useMissions() {
  const { refreshKey } = useApp();
  const [data, setData] = useState<MissionsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const reload = useCallback(() => api.missions().then(setData).catch((e) => setErr(String(e))), []);
  useEffect(() => { void reload(); }, [reload, refreshKey]);
  return { data, err, reload };
}

const STATE_BADGE: Record<string, string> = { complete: "live", in_progress: "cyan", available: "violet", locked: "neutral", not_available: "notrun" };

export function MissionCard({ m, data }: { m: Mission; data: MissionsResponse }) {
  const { t } = useTranslation();
  const loc = useLoc();
  const st = data.status[m.id];
  return (
    <a href={`#/missions/${m.id}`} className={`panel mission-card state-${st.state}`} data-testid={`mission-card-${m.number}`} data-state={st.state}>
      <div className="row">
        <span className="mission-num">{t("missions.number", { n: String(m.number).padStart(2, "0") })}</span>
        <span className="spacer" />
        <span className={`badge ${STATE_BADGE[st.state]}`}>{t(`missionState.${st.state}`)}</span>
      </div>
      <h2>{loc(m.title)}</h2>
      <p className="sub" style={{ margin: 0 }}>{loc(m.tagline)}</p>
      <div className="meter" aria-label={t("missions.progressAria", { v: st.verified, r: st.required })}><span style={{ width: `${(st.verified / st.required) * 100}%` }} /></div>
      <div className="row small dim">
        <span>{t("missions.verifiedSteps", { v: st.verified, r: st.required })}</span>
        <span className="spacer" />
        {st.mastery !== "none" && <span className="badge violet">{t(`mastery.${st.mastery}`)}</span>}
      </div>
    </a>
  );
}

export function MissionsPage() {
  const { t } = useTranslation();
  const { data, err } = useMissions();
  if (err) return <div className="callout err">{err}</div>;
  if (!data) return <div className="dim">{t("common.loading")}</div>;
  return (
    <>
      {!data.scanned && <div className="callout warn">{t("missions.scanFirst")}</div>}
      <div className="grid auto">{data.missions.map((m) => <MissionCard key={m.id} m={m} data={data} />)}</div>
      <p className="small dim">{t("missions.lockNote")}</p>
    </>
  );
}

export function MissionDetail({ id }: { id: string }) {
  const { t } = useTranslation();
  const loc = useLoc();
  const { mode, bump } = useApp();
  const { data, reload } = useMissions();
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [autoplay, setAutoplay] = useState(false);

  const m = data?.missions.find((x) => x.id === id);

  const startStep = useCallback(async (step: Step, params: Record<string, unknown>, approve: boolean) => {
    const r = await api.runStep(id, step.id, params, approve);
    setRuns((prev) => ({ ...prev, [step.id]: r }));
    const fin = await waitForRun(r.id, (x) => setRuns((prev) => ({ ...prev, [step.id]: x })));
    await reload();
    bump();
    return fin;
  }, [id, reload, bump]);

  const observeAll = async () => {
    if (!m || !data) return;
    setAutoplay(true);
    try {
      for (const s of m.steps) {
        if (!s.action) continue;
        const pv = await api.preview(s.action.id, s.action.params).catch(() => null);
        if (!pv || pv.approval_required || pv.missing_capabilities.length) continue; // never auto-approve, never fake
        const fin = await startStep(s, {}, false);
        if (fin.status !== "succeeded" && !s.optional) break;
      }
    } finally { setAutoplay(false); }
  };

  if (!data) return <div className="dim">{t("common.loading")}</div>;
  if (!m) return <Empty>{t("missions.notFound")}</Empty>;
  const st = data.status[m.id];
  const prog = data.progress.missions[m.id];

  return (
    <>
      <div className="panel glow">
        <div className="row">
          <a href="#/missions" className="small">← {t("missions.all")}</a>
          <span className="spacer" />
          <span className={`badge ${STATE_BADGE[st.state]}`} data-testid="mission-state">{t(`missionState.${st.state}`)}</span>
          <span className="badge neutral">v{m.version}</span>
        </div>
        <div className="mission-num" style={{ marginTop: 10 }}>{t("missions.number", { n: String(m.number).padStart(2, "0") })}</div>
        <h2 style={{ fontSize: 24 }}>{loc(m.title)}</h2>
        <p className="sub">{loc(m.tagline)}</p>
        {st.blocked_by.length > 0 && <div className="callout warn small">{t("missions.prereq", { list: st.blocked_by.join(", ") })}</div>}
        <div className="grid two" style={{ marginTop: 12 }}>
          <div>
            <h3>{t("missions.objectives")}</h3>
            <ul>{m.objectives.map((o, i) => <li key={i}>{loc(o)}</li>)}</ul>
          </div>
          <div>
            <h3>{t("missions.evidence")}</h3>
            <p>{loc(m.completion_evidence)}</p>
            <div className="meter"><span style={{ width: `${(st.verified / st.required) * 100}%` }} /></div>
            <div className="small dim" style={{ marginTop: 4 }}>{t("missions.verifiedSteps", { v: st.verified, r: st.required })} · {t(`mastery.${st.mastery}`)}</div>
          </div>
        </div>
        {mode === "observe" && (
          <div className="callout" style={{ marginTop: 12 }}>
            <div className="row">
              <span>{t("missions.observeIntro")}</span>
              <span className="spacer" />
              <button type="button" className="btn primary" onClick={observeAll} disabled={autoplay} data-testid="observe-run-all">
                {autoplay ? t("missions.observeRunning") : t("missions.observeRun")}
              </button>
            </div>
          </div>
        )}
      </div>

      {m.steps.map((s, i) => (
        <StepCard key={s.id} mission={m} step={s} index={i} status={st.steps[s.id]} progress={prog?.steps?.[s.id]}
          run={runs[s.id]} onRun={(p, a) => startStep(s, p, a)} capabilities={data.capabilities} afterQuiz={reload} />
      ))}

      {m.challenge && <ChallengeCard mission={m} done={st.challenge_verified} result={prog?.challenge} onDone={reload} />}

      {m.optional_experiments.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>{t("missions.optionalExperiments")}</h3>
          <ul>{m.optional_experiments.map((o, i) => <li key={i}>{loc(o)}</li>)}</ul>
        </div>
      )}
    </>
  );
}

function ChecksList({ checks, step }: { checks: CheckResult[]; step: { checks: { id: string; description: any }[] } }) {
  const { t } = useTranslation();
  const loc = useLoc();
  const { mode } = useApp();
  return (
    <ul className="checks" data-testid="checks">
      {checks.map((c) => {
        const def = step.checks.find((d) => d.id === c.id);
        return (
          <li key={c.id} data-passed={c.passed}>
            <span className={c.passed ? "ok" : "no"} aria-hidden>{c.passed ? "✔" : "✘"}</span>
            <span>{def ? loc(def.description) : c.id}<span className="sr-only">{c.passed ? t("checks.passed") : t("checks.failed")}</span></span>
            {mode !== "guided" && (
              <code className="dim small">{c.path} {c.op} {JSON.stringify(c.expected)} → {c.missing ? t("checks.missing") : JSON.stringify(c.actual)}</code>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function StepCard({ mission, step, index, status, progress, run, onRun, capabilities, afterQuiz }: {
  mission: Mission; step: Step; index: number; status: string; progress: any; run?: Run;
  onRun: (params: Record<string, unknown>, approve: boolean) => Promise<Run>; capabilities: Record<string, boolean>; afterQuiz: () => void;
}) {
  const { t, i18n } = useTranslation();
  const loc = useLoc();
  const { mode } = useApp();
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [preview, setPreview] = useState<{ command: string; approval_required: string | null; missing_capabilities: string[] } | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [teach, setTeach] = useState(false);
  const [sources, setSources] = useState<{ file: string; symbol: string | null }[]>([]);
  const [viewSource, setViewSource] = useState<{ file: string; symbol: string | null } | null>(null);
  const [hints, setHints] = useState<any[]>([]);
  const [quizPick, setQuizPick] = useState<number | null>(null);
  const [quizRes, setQuizRes] = useState<{ correct: boolean; explanation: any } | null>(null);

  const merged = { ...(step.action?.params ?? {}), ...params };
  const placeholder = (v: unknown) => typeof v === "string" && v.startsWith("${");

  useEffect(() => {
    if (!step.action) return;
    // Placeholders like ${m05-...:s2-baseline} are filled by the server from earlier verified steps.
    const show = (v: unknown) => placeholder(v) ? `<${String(v).slice(2, -1).replace(/^(m0\d)-[a-z0-9-]+/, "$1")}>` : v;
    const resolvable = Object.fromEntries(Object.entries(merged).map(([k, v]) => [k, Array.isArray(v) ? v.map(show) : show(v)]));
    api.preview(step.action.id, resolvable).then((p) => { setPreview(p); setPreviewErr(null); }).catch((e) => setPreviewErr(String(e.message ?? e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step.action?.id, JSON.stringify(params)]);

  useEffect(() => {
    getActions().then((acts) => {
      const spec = acts.find((a: any) => a.id === step.action?.id);
      const all = [...step.sources, ...(spec?.sources ?? [])];
      const uniq = all.filter((s, i) => all.findIndex((x) => x.file === s.file && x.symbol === s.symbol) === i);
      setSources(uniq);
    });
  }, [step]);

  const evaluation = progress?.evaluation;
  const running = run && (run.status === "running" || run.status === "pending");
  const verified = status === "verified";
  const missingCaps = step.requires_capabilities.filter((c) => !capabilities[c]);
  const explain = mode !== "expert";

  const doRun = async (approve: boolean) => { setConfirm(false); await onRun(params, approve); };

  return (
    <section className={`panel step ${status}`} aria-labelledby={`step-${step.id}`} data-testid={`step-${step.id}`} data-step-status={status}>
      <div className="row">
        <span className="mission-num">{t("missions.step", { n: index + 1 })}</span>
        <h2 id={`step-${step.id}`} style={{ margin: 0 }}>{loc(step.title)}</h2>
        {step.optional && <span className="badge neutral">{t("missions.optional")}</span>}
        <span className="spacer" />
        <span className={`badge ${verified ? "live" : status === "not_available" ? "notrun" : "neutral"}`} data-testid="step-status">{t(`stepStatus.${status}`)}</span>
      </div>

      {(explain || teach) ? (
        <div className="grid two" style={{ marginTop: 10 }}>
          <div><h3>{t("missions.what")}</h3><p>{loc(step.what)}</p></div>
          <div><h3>{t("missions.why")}</h3><p>{loc(step.why)}</p></div>
        </div>
      ) : (
        <details><summary>{t("missions.whatWhy")}</summary><p>{loc(step.what)}</p><p>{loc(step.why)}</p></details>
      )}

      {missingCaps.length > 0 && (
        <div className="callout warn small" data-testid="capability-warning">
          {t("missions.missingCaps", { caps: missingCaps.map((c) => t(`caps.${c}`)).join(", ") })}
        </div>
      )}

      <div className="row" style={{ margin: "8px 0" }}>
        {step.concept && <button type="button" className="btn tiny" onClick={() => setTeach((v) => !v)} aria-expanded={teach}>{t("tutor.teachMe")}</button>}
        {sources.length > 0 && <button type="button" className="btn tiny" onClick={() => setViewSource(sources[0])} data-testid="view-source">{t("source.view")}</button>}
      </div>
      {teach && step.concept && <ConceptExplainer concept={step.concept} />}

      {step.action && (
        <div className="grid" style={{ gap: 10 }}>
          {(step.action.editable.length > 0 || mode === "expert") && (
            <div className="row">
              {(mode === "expert" ? Object.keys(merged) : step.action.editable).map((k) => {
                const v = merged[k];
                const editable = step.action!.editable.includes(k);
                if (Array.isArray(v) || placeholder(v)) {
                  return <label key={k} className="field"><code>{k}</code><input type="text" value={JSON.stringify(v)} disabled aria-label={k} /></label>;
                }
                return (
                  <label key={k} className="field">
                    <code>{k}</code>
                    {k === "lang" ? (
                      <select value={String(v)} disabled={!editable} onChange={(e) => setParams({ ...params, [k]: e.target.value })}>
                        <option value="en">en</option><option value="zh-TW">zh-TW</option>
                      </select>
                    ) : (
                      <input type={typeof v === "number" ? "number" : "text"} value={String(v ?? "")} disabled={!editable}
                        onChange={(e) => setParams({ ...params, [k]: typeof v === "number" ? Number(e.target.value) : e.target.value })}
                        style={{ minWidth: k === "prompt" || k === "hypothesis" || k === "decision" ? 320 : 90 }} />
                    )}
                  </label>
                );
              })}
            </div>
          )}
          {preview && <CommandBox command={preview.command} label={t("missions.willRun")} />}
          {previewErr && <div className="callout err small">{previewErr}</div>}
          {explain && <div className="small"><span className="muted">{t("missions.expected")}:</span> {loc(step.expected)}</div>}
          <div className="row">
            {preview?.approval_required ? (
              <button type="button" className="btn warn" disabled={!!running} onClick={() => setConfirm(true)} data-testid="run-step">
                {t("missions.approveRun")}
              </button>
            ) : (
              <button type="button" className="btn primary" disabled={!!running} onClick={() => doRun(false)} data-testid="run-step">
                {running ? t("missions.running") : verified ? t("missions.runAgain") : t("missions.run")}
              </button>
            )}
            {preview?.approval_required && (
              <button type="button" className="btn ghost tiny" disabled={!!running} onClick={() => doRun(false)} data-testid="run-without-approval">
                {t("missions.runWithoutApproval")}
              </button>
            )}
          </div>
          {run && <RunView run={run} />}
          {evaluation && evaluation.checks?.length > 0 && (
            <div>
              <h3>{t("missions.validation")}</h3>
              <ChecksList checks={evaluation.checks} step={step} />
              <div className="small dim">{t("missions.validationNote")}</div>
            </div>
          )}
          {evaluation && !evaluation.checks?.length && evaluation.status !== "verified" && (
            <div className="small dim">{t("missions.lastAttempt", { status: t(`status.${evaluation.status}`, { defaultValue: evaluation.status }) })}</div>
          )}
        </div>
      )}

      {step.quiz && (
        <fieldset style={{ border: 0, padding: 0, margin: "10px 0" }} data-testid="quiz">
          <legend style={{ fontWeight: 600, marginBottom: 6 }}>{loc(step.quiz.question)}</legend>
          {step.quiz.options.map((o, i) => (
            <label key={i} className="row" style={{ margin: "4px 0", cursor: "pointer" }}>
              <input type="radio" name={`quiz-${step.id}`} checked={quizPick === i} onChange={() => setQuizPick(i)} />
              <span>{loc(o)}</span>
            </label>
          ))}
          <div className="row" style={{ marginTop: 6 }}>
            <button type="button" className="btn" disabled={quizPick === null}
              onClick={async () => { const r = await api.quiz(mission.id, step.id, quizPick!); setQuizRes(r); afterQuiz(); }} data-testid="quiz-submit">
              {t("quiz.check")}
            </button>
            {progress?.quiz?.correct && !quizRes && <span className="badge live">{t("quiz.alreadyCorrect")}</span>}
          </div>
          {quizRes && (
            <div className={`callout ${quizRes.correct ? "ok" : "warn"}`} style={{ marginTop: 8 }} data-testid="quiz-result">
              <strong>{quizRes.correct ? t("quiz.correct") : t("quiz.tryAgain")}</strong>
              {quizRes.explanation && <p style={{ margin: "6px 0 0" }}>{loc(quizRes.explanation)}</p>}
            </div>
          )}
        </fieldset>
      )}

      {mode === "guided" && step.hints.length > 0 && !verified && (
        <div style={{ marginTop: 8 }}>
          {hints.map((h, i) => <div key={i} className="callout small" style={{ marginBottom: 6 }}>💡 {t("hints.n", { n: i + 1 })}: {loc(h)}</div>)}
          {hints.length < step.hints.length && (
            <button type="button" className="btn tiny ghost" data-testid="hint"
              onClick={async () => { const r = await api.hint(mission.id, step.id); setHints(r.hints); }}>
              {hints.length === 0 ? t("hints.first") : t("hints.more", { left: step.hints.length - hints.length })}
            </button>
          )}
        </div>
      )}

      {(mode !== "observe" || run) && (step.reproduce || step.alternatives) && (
        <details style={{ marginTop: 10 }}>
          <summary>{t("missions.reproduceAlternatives")}</summary>
          {step.reproduce && <CommandBox command={loc(step.reproduce)} label={t("missions.reproduce")} />}
          {step.alternatives && <p className="small" style={{ marginTop: 8 }}><span className="muted">{t("missions.alternatives")}:</span> {loc(step.alternatives)}</p>}
          <p className="small"><span className="muted">{t("missions.failure")}:</span> {loc(step.failure)}</p>
        </details>
      )}

      {confirm && preview && (
        <Modal title={t("approval.title")} onClose={() => setConfirm(false)}>
          <p>{t(`approval.${preview.approval_required}`)}</p>
          <CommandBox command={preview.command} label={t("missions.willRun")} />
          <p className="small muted">{t("approval.note")}</p>
          <div className="row">
            <button type="button" className="btn warn" onClick={() => doRun(true)} data-testid="approve-confirm">{t("approval.approve")}</button>
            <button type="button" className="btn" onClick={() => setConfirm(false)}>{t("common.cancel")}</button>
          </div>
        </Modal>
      )}
      {viewSource && (
        <Modal title={t("source.title")} onClose={() => setViewSource(null)}>
          <div className="row" style={{ marginBottom: 10 }}>
            {sources.map((s) => (
              <button key={`${s.file}:${s.symbol}`} type="button" className="btn tiny" aria-pressed={s === viewSource} onClick={() => setViewSource(s)}>
                {s.symbol ?? s.file.split("/").pop()}
              </button>
            ))}
          </div>
          <SourceViewer path={viewSource.file} symbol={viewSource.symbol} />
          {i18n.language && <div className="small dim" style={{ marginTop: 8 }}><a href={`#/code?path=${encodeURIComponent(viewSource.file)}${viewSource.symbol ? `&symbol=${viewSource.symbol}` : ""}`} onClick={() => setViewSource(null)}>{t("source.openInExplorer")}</a></div>}
        </Modal>
      )}
    </section>
  );
}

function ChallengeCard({ mission, done, result, onDone }: { mission: Mission; done: boolean; result: any; onDone: () => void }) {
  const { t } = useTranslation();
  const loc = useLoc();
  const ch = mission.challenge!;
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [run, setRun] = useState<Run | null>(null);
  const merged = { ...ch.action.params, ...params };
  return (
    <section className="panel" data-testid="challenge">
      <div className="row">
        <span className="badge violet">{t("challenge.label")}</span>
        <h2 style={{ margin: 0 }}>{t("challenge.title")}</h2>
        <span className="spacer" />
        {done && <span className="badge live">{t("challenge.done")}</span>}
      </div>
      <p>{loc(ch.prompt)}</p>
      <p className="small dim">{t("challenge.noHints")}</p>
      <div className="row">
        {ch.action.editable.map((k) => {
          const v = merged[k];
          if (Array.isArray(v)) return null;
          return (
            <label key={k} className="field"><code>{k}</code>
              {k === "lang" ? (
                <select value={String(v)} onChange={(e) => setParams({ ...params, [k]: e.target.value })}><option value="en">en</option><option value="zh-TW">zh-TW</option></select>
              ) : (
                <input type={typeof v === "number" ? "number" : "text"} value={String(v ?? "")}
                  onChange={(e) => setParams({ ...params, [k]: typeof v === "number" ? Number(e.target.value) : e.target.value })} />
              )}
            </label>
          );
        })}
        <button type="button" className="btn primary" onClick={async () => {
          const r = await api.runChallenge(mission.id, params, false);
          setRun(r);
          await waitForRun(r.id, setRun);
          onDone();
        }}>{t("challenge.submit")}</button>
      </div>
      {run && <div style={{ marginTop: 10 }}><RunView run={run} /></div>}
      {result?.checks && <ChecksList checks={result.checks} step={ch} />}
    </section>
  );
}
