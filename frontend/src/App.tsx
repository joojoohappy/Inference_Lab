import { useTranslation } from "react-i18next";
import { setLanguage, type Lang } from "./i18n";
import { AppStateProvider, useApp, type Mode } from "./lib/state";
import { ArenaPage } from "./pages/Arena";
import { CodePage } from "./pages/Code";
import { GaragePage } from "./pages/Garage";
import { JournalPage } from "./pages/Journal";
import { LabPage } from "./pages/Lab";
import { MissionDetail, MissionsPage } from "./pages/Missions";
import { ResearchPage } from "./pages/Research";

const AREAS = [
  { id: "lab", glyph: "◎" },
  { id: "garage", glyph: "⬢" },
  { id: "missions", glyph: "▲" },
  { id: "code", glyph: "{}" },
  { id: "research", glyph: "¶" },
  { id: "arena", glyph: "⚡" },
  { id: "journal", glyph: "✎" },
] as const;

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const langs: { value: Lang; label: string }[] = [{ value: "en", label: "English" }, { value: "zh-TW", label: "繁體中文" }];
  return (
    <div className="row" style={{ gap: 4 }}>
      <span className="seg-label" id="lang-label">{t("shell.language")}</span>
      <div className="seg" role="group" aria-labelledby="lang-label">
        {langs.map((l) => (
          <button key={l.value} type="button" lang={l.value} aria-pressed={i18n.language === l.value} onClick={() => setLanguage(l.value)}
            data-testid={`lang-${l.value}`}>
            {l.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ModeSwitcher() {
  const { t } = useTranslation();
  const { mode, setMode } = useApp();
  const modes: Mode[] = ["observe", "guided", "expert"];
  return (
    <div className="row" style={{ gap: 4 }}>
      <span className="seg-label" id="mode-label">{t("shell.mode")}</span>
      <div className="seg" role="group" aria-labelledby="mode-label">
        {modes.map((m) => (
          <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)} title={t(`modes.${m}.help`)} data-testid={`mode-${m}`}>
            {t(`modes.${m}.label`)}
          </button>
        ))}
      </div>
    </div>
  );
}

function Shell() {
  const { t } = useTranslation();
  const { route } = useApp();
  const page = route.page;
  let body;
  switch (page) {
    case "garage": body = <GaragePage />; break;
    case "missions": body = route.arg ? <MissionDetail id={route.arg} /> : <MissionsPage />; break;
    case "code": body = <CodePage />; break;
    case "research": body = <ResearchPage />; break;
    case "arena": body = <ArenaPage />; break;
    case "journal": body = <JournalPage />; break;
    default: body = <LabPage />;
  }
  const current = AREAS.find((a) => a.id === page) ? page : "lab";
  return (
    <div className="shell">
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>{t("shell.skip")}</a>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden><span>IL</span></div>
          <div>
            <div className="brand-name">Inference Lab</div>
            <div className="brand-tag">{t("shell.tagline")}</div>
          </div>
        </div>
        <nav className="nav" aria-label={t("shell.nav")}>
          {AREAS.map((a) => (
            <a key={a.id} href={`#/${a.id}`} aria-current={current === a.id ? "page" : undefined} data-testid={`nav-${a.id}`}>
              <span className="glyph" aria-hidden>{a.glyph}</span>{t(`areas.${a.id}.name`)}
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">{t("shell.localOnly")}</div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div>
            <h1>{t(`areas.${current}.name`)}</h1>
            <div className="small dim">{t(`areas.${current}.desc`)}</div>
          </div>
          <div className="controls">
            <ModeSwitcher />
            <LanguageSwitcher />
          </div>
        </header>
        <main className="content" id="main" tabIndex={-1}>{body}</main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AppStateProvider>
      <Shell />
    </AppStateProvider>
  );
}
