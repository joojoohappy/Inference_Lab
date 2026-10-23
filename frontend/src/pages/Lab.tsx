import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Empty, ProvenanceBadge, StatusBadge, fmt } from "../components/common";
import { RunView } from "../components/RunView";
import { api, waitForRun, type Run } from "../lib/api";
import { useApp } from "../lib/state";
import { MissionCard, useMissions } from "./Missions";

export function MachinePanel() {
  const { t } = useTranslation();
  const { refreshKey, bump } = useApp();
  const [scan, setScan] = useState<any>(null);
  const [run, setRun] = useState<Run | null>(null);
  useEffect(() => { api.hardware().then((h) => setScan(h.scan)); }, [refreshKey]);
  const doScan = async () => {
    // Scanning from the Lab counts as Mission 01's first step: same action, same evidence.
    const r = await api.runStep("m01-meet-your-machine", "s1-scan", {}, false);
    setRun(r);
    const fin = await waitForRun(r.id, setRun);
    if (fin.result) setScan(fin.result);
    bump();
  };
  const s = scan?.summary;
  const caps = scan?.capabilities ?? {};
  const gpus = scan?.probes?.gpu?.data?.gpus ?? [];
  const docker = scan?.probes?.docker?.data;
  return (
    <section className="panel glow" aria-labelledby="machine-h">
      <div className="row">
        <h2 id="machine-h">{t("lab.machine")}</h2>
        <span className="spacer" />
        {scan && <ProvenanceBadge value="LIVE_MEASURED" />}
        <button type="button" className="btn primary" onClick={doScan} data-testid="scan">{scan ? t("lab.rescan") : t("lab.scan")}</button>
      </div>
      {!scan && <p className="sub">{t("lab.machineIntro")}</p>}
      {s && (
        <div className="machine" style={{ marginTop: 10 }} data-testid="machine">
          <div className="chip on"><div className="k">CPU</div><div className="v">{s.cpu_model}</div><div className="small dim">{t("lab.threads", { n: s.logical_cores })}</div></div>
          <div className="chip on"><div className="k">RAM</div><div className="v">{fmt(s.ram_total_gb)} GB</div></div>
          <div className={`chip ${gpus.length ? "on" : "off"}`}><div className="k">GPU / VRAM</div>
            <div className="v">{gpus.length ? gpus.map((g: any) => g.name).join(", ") : t("lab.noGpu")}</div>
            <div className="small dim">{gpus.length ? `${fmt(s.vram_total_gb)} GB · driver ${gpus[0].driver_version}` : t("lab.noGpuHelp")}</div></div>
          <div className={`chip ${docker?.daemon_running ? "on" : "off"}`}><div className="k">Docker</div>
            <div className="v">{docker?.daemon_running ? docker.server : docker?.client ? t("lab.dockerNoDaemon") : t("lab.notFound")}</div></div>
        </div>
      )}
      {scan && (
        <div className="row" style={{ marginTop: 12 }} data-testid="capabilities">
          {Object.entries(caps).map(([k, v]) => (
            <span key={k} className={`badge ${v ? "live" : "notrun"}`} title={t(`caps.${k}`)}>{v ? "✔" : "—"} {t(`caps.${k}`)}</span>
          ))}
        </div>
      )}
      {run && <div style={{ marginTop: 12 }}><RunView run={run} /></div>}
    </section>
  );
}

export function LabPage() {
  const { t } = useTranslation();
  const { data } = useMissions();
  const { refreshKey } = useApp();
  const [exps, setExps] = useState<any[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  useEffect(() => {
    api.experiments().then((e) => setExps(e.slice(0, 6)));
    api.runs().then((r) => setRuns(r.slice(0, 6)));
  }, [refreshKey]);
  const next = data?.missions.find((m) => ["available", "in_progress"].includes(data.status[m.id].state));
  const skills = data ? data.missions.filter((m) => data.status[m.id].mastery !== "none") : [];
  return (
    <>
      <div className="panel" style={{ background: "linear-gradient(120deg, rgba(8,145,178,0.18), rgba(79,70,229,0.14))" }}>
        <h2 style={{ fontSize: 22 }}>{t("lab.welcome")}</h2>
        <p className="sub" style={{ marginBottom: 6 }}>{t("lab.welcomeSub")}</p>
        <div className="row">
          {next && <a className="btn primary" href={`#/missions/${next.id}`} data-testid="continue-mission">{t("lab.continue")}</a>}
          <a className="btn" href="#/missions">{t("lab.allMissions")}</a>
        </div>
      </div>
      <MachinePanel />
      <div className="grid two">
        <section className="panel">
          <h2>{t("lab.missions")}</h2>
          {data && (
            <div className="grid" style={{ gap: 8, marginTop: 8 }}>
              {data.missions.map((m) => <MissionCard key={m.id} m={m} data={data} />)}
            </div>
          )}
        </section>
        <div className="grid" style={{ alignContent: "start" }}>
          <section className="panel">
            <h2>{t("lab.skills")}</h2>
            <p className="sub">{t("lab.skillsSub")}</p>
            {skills.length === 0 ? <Empty>{t("lab.noSkills")}</Empty> : (
              <ul className="checks">{skills.map((m) => (
                <li key={m.id}><span className="badge violet">{t(`mastery.${data!.status[m.id].mastery}`)}</span> {t(`skills.${m.id}`)}</li>
              ))}</ul>
            )}
          </section>
          <section className="panel">
            <h2>{t("lab.recent")}</h2>
            {exps.length === 0 ? <Empty>{t("lab.noResults")}</Empty> : (
              <table className="data"><tbody>
                {exps.map((e) => (
                  <tr key={e.id}>
                    <td><a href={`#/journal/${e.id}`}>{t(`kinds.${e.kind}`)}</a><div className="small dim">{new Date(e.created_at * 1000).toLocaleString()}</div></td>
                    <td><ProvenanceBadge value={e.provenance} /></td>
                    <td className="small mono">{e.headline ? Object.entries(e.headline).filter(([, v]) => v != null).slice(0, 2).map(([k, v]) => `${k}=${fmt(v)}`).join(" ") : ""}</td>
                  </tr>
                ))}
              </tbody></table>
            )}
          </section>
          <section className="panel">
            <h2>{t("lab.activity")}</h2>
            {runs.length === 0 ? <Empty>{t("lab.noRuns")}</Empty> : (
              <table className="data"><tbody>
                {runs.map((r) => (<tr key={r.id}><td className="mono small">{r.action}</td><td><StatusBadge run={r} /></td><td><ProvenanceBadge value={r.provenance} /></td></tr>))}
              </tbody></table>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
