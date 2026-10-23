import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CommandBox, Empty, Modal, ProvenanceBadge, fmt } from "../components/common";
import { RunView } from "../components/RunView";
import { api, waitForRun, type Run } from "../lib/api";
import { useLoc } from "../lib/loc";
import { useApp } from "../lib/state";

function bytes(n: number | null | undefined): string {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 ? 2 : 1)} ${u[i]}`;
}

function ModelReport({ info }: { info: any }) {
  const { t } = useTranslation();
  const s = info.summary;
  const est = info.memory_estimate;
  const comp = info.compatibility;
  return (
    <div className="grid two" data-testid="model-report">
      <div>
        <h3>{t("garage.metadata")}</h3>
        <dl className="kv">
          <dt>{t("garage.f.id")}</dt><dd><code>{s.id}</code></dd>
          <dt>{t("garage.f.source")}</dt><dd>{t(`garage.source.${info.source}`)}</dd>
          {s.revision && (<><dt>{t("garage.f.revision")}</dt><dd><code>{s.revision}</code></dd></>)}
          <dt>{t("garage.f.task")}</dt><dd>{s.task ?? "—"}</dd>
          <dt>{t("garage.f.arch")}</dt><dd>{(s.architectures ?? []).join(", ") || "—"} {s.model_type && <span className="dim">({s.model_type})</span>}</dd>
          <dt>{t("garage.f.params")}</dt><dd>{s.parameters ? s.parameters.toLocaleString() : "—"} {s.parameter_dtypes && <span className="dim">{JSON.stringify(s.parameter_dtypes)}</span>}</dd>
          <dt>{t("garage.f.license")}</dt><dd>{s.license ?? t("garage.unknown")}</dd>
          <dt>{t("garage.f.gated")}</dt><dd>{s.gated ? <span className="badge demo">{String(s.gated)}</span> : t("common.no")}</dd>
          <dt>{t("garage.f.formats")}</dt><dd>{(s.weight_formats ?? []).join(", ") || "—"} {s.pickle_only && <span className="badge failed">{t("garage.pickleOnly")}</span>}</dd>
          <dt>{t("garage.f.size")}</dt><dd>{bytes(s.repo_size_bytes)}{s.download_bytes ? ` · ${t("garage.downloadSize", { size: bytes(s.download_bytes) })}` : ""}</dd>
          <dt>{t("garage.f.tokenizer")}</dt><dd>{s.has_tokenizer ? t("common.yes") : t("common.no")}{s.tokenizer_vocab_size ? ` · vocab ${s.tokenizer_vocab_size}` : ""}</dd>
          <dt>{t("garage.f.chat")}</dt><dd>{s.has_chat_template ? t("common.yes") : t("common.no")}</dd>
          <dt>{t("garage.f.remoteCode")}</dt><dd>{s.needs_remote_code ? <span className="badge failed">{t("garage.remoteCodeYes")}</span> : t("common.no")}</dd>
          {s.framework_support && (<><dt>{t("garage.f.frameworks")}</dt><dd>Transformers: {s.framework_support.transformers ? t("common.yes") : t("garage.unknown")} · <a href={s.framework_support.vllm_check} target="_blank" rel="noreferrer">{t("garage.vllmCheck")}</a></dd></>)}
        </dl>
      </div>
      <div>
        <h3>{t("garage.memory")} <span className="badge neutral">{t("garage.estimate")}</span></h3>
        {est?.known ? (
          <dl className="kv">
            <dt>{t("garage.weights")}</dt><dd>{fmt(est.weights_gb, 3)} GB <span className="dim">({est.dtype})</span></dd>
            <dt>{t("garage.kv")}</dt><dd>{est.kv_cache_gb != null ? `${fmt(est.kv_cache_gb, 3)} GB` : "—"}</dd>
            <dt>{t("garage.total")}</dt><dd><strong>{fmt(est.total_gb, 2)} GB</strong></dd>
          </dl>
        ) : <Empty>{t("garage.noEstimate")}</Empty>}
        {est?.assumptions && <details><summary>{t("garage.assumptions")}</summary><ul className="small">{est.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul></details>}
        <h3>{t("garage.compat")}</h3>
        <div className={`callout ${comp.verdict === "too_large" ? "err" : comp.verdict === "unknown" ? "" : "ok"}`} data-testid="compat">
          <strong>{t(`garage.verdict.${comp.verdict}`)}</strong>
          <ul className="small">{comp.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
          {comp.paths.length > 0 && <div className="small">{t("garage.paths")}: {comp.paths.map((p: string) => t(`garage.path.${p}`)).join(" · ")}</div>}
        </div>
      </div>
      {s.model_card && <details style={{ gridColumn: "1 / -1" }}><summary>{t("garage.card")}</summary><pre className="raw">{s.model_card}</pre></details>}
    </div>
  );
}

export function GaragePage() {
  const { t } = useTranslation();
  const loc = useLoc();
  const { bump } = useApp();
  const [catalog, setCatalog] = useState<any[]>([]);
  const [local, setLocal] = useState<string[]>([]);
  const [ref, setRef] = useState("HuggingFaceTB/SmolLM2-135M-Instruct");
  const [run, setRun] = useState<Run | null>(null);
  const [info, setInfo] = useState<any>(null);
  const [inputErr, setInputErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [prevModel, setPrevModel] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("The KV cache stores");
  const [inferModel, setInferModel] = useState("lab/tiny-random");
  const [inferRun, setInferRun] = useState<Run | null>(null);

  const loadLocal = () => api.localModels().then(setLocal);
  useEffect(() => { api.catalog().then(setCatalog); void loadLocal(); }, []);

  const go = async (action: string, params: Record<string, unknown>, approve = false, setter = setRun) => {
    setInputErr(null);
    try {
      const r = await api.submit(action, params, approve);
      setter(r);
      const fin = await waitForRun(r.id, setter);
      if (fin.status === "succeeded" && (action === "hub.inspect" || action === "model.inspect_local")) {
        if (info && info.summary.id !== fin.result.summary.id) setPrevModel(info.summary.id);
        setInfo(fin.result);
      }
      if (action === "model.download" || action === "model.prepare_tiny") void loadLocal();
      bump();
    } catch (e: any) {
      setInputErr(typeof e.detail === "string" ? e.detail : Array.isArray(e.detail) ? e.detail.map((d: any) => d.msg).join("; ") : String(e));
    }
  };

  return (
    <>
      <div className="callout">{t("garage.twoWorkflows")}</div>
      <section className="panel">
        <h2>{t("garage.inspectTitle")}</h2>
        <p className="sub">{t("garage.inspectSub")}</p>
        <form className="row" onSubmit={(e) => { e.preventDefault(); void go("hub.inspect", { model: ref }); }}>
          <input type="text" value={ref} onChange={(e) => setRef(e.target.value)} style={{ flex: 1, minWidth: 260 }} aria-label={t("garage.inputLabel")} data-testid="model-input" />
          <button type="submit" className="btn primary" data-testid="inspect-hub">{t("garage.inspectHub")}</button>
          <button type="button" className="btn" onClick={() => go("model.inspect_local", { model: ref })}>{t("garage.inspectLocal")}</button>
        </form>
        {inputErr && <div className="callout err small" style={{ marginTop: 8 }} data-testid="input-error">{t("garage.invalidInput")}: {inputErr}</div>}
        {run && <div style={{ marginTop: 12 }}><RunView run={run} /></div>}
      </section>

      {info && (
        <section className="panel glow">
          <div className="row"><h2>{info.summary.id}</h2><ProvenanceBadge value="LIVE_MEASURED" /><span className="spacer" />
            {info.download_plan && (info.download_plan.allowed ? (
              <button type="button" className="btn warn" onClick={() => setConfirm(info.summary.id)} data-testid="download">{t("garage.download")}</button>
            ) : <span className="badge failed">{t("garage.downloadRefused", { reason: info.download_plan.reason })}</span>)}
          </div>
          {prevModel && <div className="callout warn small">{t("garage.modelChanged", { prev: prevModel })}</div>}
          <ModelReport info={info} />
        </section>
      )}

      <div className="grid two">
        <section className="panel">
          <h2>{t("garage.catalog")}</h2>
          <p className="sub">{t("garage.catalogSub")}</p>
          {catalog.map((c) => (
            <div key={c.id} className="row" style={{ borderTop: "1px solid var(--line)", padding: "8px 0" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <code>{c.id}</code> <span className="badge neutral">{t(`garage.size.${c.size_class}`)}</span>
                <div className="small muted">{loc(c.note)}</div>
              </div>
              {c.kind === "local"
                ? <button type="button" className="btn tiny" onClick={() => go("model.prepare_tiny", {})}>{t("garage.build")}</button>
                : <button type="button" className="btn tiny" onClick={() => { setRef(c.id); void go("hub.inspect", { model: c.id }); }}>{t("garage.inspectHub")}</button>}
              <button type="button" className="btn tiny" onClick={() => { setRef(c.id); void go("model.inspect_local", { model: c.id }); }}>{t("garage.inspectLocal")}</button>
            </div>
          ))}
        </section>
        <section className="panel">
          <h2>{t("garage.local")}</h2>
          {local.length === 0 ? <Empty>{t("garage.noLocal")}</Empty> : <ul>{local.map((m) => <li key={m}><code>{m}</code></li>)}</ul>}
          <h3>{t("garage.tryInference")}</h3>
          <div className="row">
            <select value={inferModel} onChange={(e) => setInferModel(e.target.value)} aria-label={t("garage.model")}>
              {[...new Set(["lab/tiny-random", ...local])].map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <input type="text" value={prompt} onChange={(e) => setPrompt(e.target.value)} style={{ flex: 1 }} aria-label={t("garage.prompt")} />
            <button type="button" className="btn primary" onClick={() => go("inference.run", { model: inferModel, prompt, max_new_tokens: 16 }, false, setInferRun as any)}>{t("garage.generate")}</button>
          </div>
          {inferRun && (
            <div style={{ marginTop: 10 }}>
              {inferRun.result && <TokenView result={inferRun.result} />}
              <RunView run={inferRun} />
            </div>
          )}
        </section>
      </div>

      {confirm && info && (
        <Modal title={t("approval.title")} onClose={() => setConfirm(null)}>
          <p>{t("approval.model_download_uses_network_and_disk")}</p>
          <dl className="kv">
            <dt>{t("garage.f.id")}</dt><dd><code>{confirm}</code></dd>
            <dt>{t("garage.f.revision")}</dt><dd><code>{info.summary.revision}</code></dd>
            <dt>{t("garage.expectedDisk")}</dt><dd>{bytes(info.download_plan.estimated_bytes)}</dd>
            <dt>{t("garage.files")}</dt><dd><code>{info.download_plan.allow_patterns.join(" ")}</code></dd>
          </dl>
          <CommandBox command={`inference-lab download ${confirm} --approve`} />
          <div className="row" style={{ marginTop: 10 }}>
            <button type="button" className="btn warn" data-testid="approve-download" onClick={() => { setConfirm(null); void go("model.download", { model: confirm, revision: info.summary.revision }, true); }}>{t("approval.approve")}</button>
            <button type="button" className="btn" onClick={() => setConfirm(null)}>{t("common.cancel")}</button>
          </div>
        </Modal>
      )}
    </>
  );
}

export function TokenView({ result }: { result: any }) {
  const { t } = useTranslation();
  return (
    <div className="grid" style={{ gap: 8, marginBottom: 10 }} data-testid="token-view">
      <div className="small muted">{t("garage.inputTokens", { n: result.input.count })}</div>
      <div className="row" style={{ gap: 4 }}>
        {result.input.tokens.map((tok: string, i: number) => <span key={i} className="badge cyan mono" title={`id ${result.input.token_ids[i]}`}>{tok}<span className="dim">·{result.input.token_ids[i]}</span></span>)}
      </div>
      <div className="small muted">{t("garage.outputTokens", { n: result.output.count })}</div>
      <div className="row" style={{ gap: 4 }}>
        {result.output.tokens.map((tok: string, i: number) => <span key={i} className="badge violet mono" title={`id ${result.output.token_ids[i]}`}>{tok}</span>)}
      </div>
      <div className="cmd"><pre>{result.output.text}</pre></div>
      <div className="row small">
        {Object.entries(result.timing).map(([k, v]) => <span key={k} className="badge neutral">{k}: {fmt(v as number, 2)}</span>)}
        <span className="badge neutral">{result.device} · {result.dtype}</span>
      </div>
      {result.is_random_teaching_model && <div className="callout small">{t("garage.randomNote")}</div>}
    </div>
  );
}
