import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Mode = "observe" | "guided" | "expert";
const MODE_KEY = "inference-lab.mode";

function readMode(): Mode {
  try {
    const m = window.localStorage.getItem(MODE_KEY);
    if (m === "observe" || m === "guided" || m === "expert") return m;
  } catch { /* ignore */ }
  return "guided";
}

/** Hash routes: #/lab, #/garage, #/missions, #/missions/<id>, #/code?path=..&symbol=.., ... */
export function parseHash(h: string): { page: string; arg?: string; query: URLSearchParams } {
  const raw = h.replace(/^#\/?/, "");
  const [path, qs] = raw.split("?");
  const [page, arg] = path.split("/");
  return { page: page || "lab", arg, query: new URLSearchParams(qs || "") };
}

interface AppState {
  mode: Mode;
  setMode: (m: Mode) => void;
  route: ReturnType<typeof parseHash>;
  go: (hash: string) => void;
  refreshKey: number;
  bump: () => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(readMode);
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  const [refreshKey, setRefresh] = useState(0);
  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const setMode = useCallback((m: Mode) => {
    setModeState(m);
    try { window.localStorage.setItem(MODE_KEY, m); } catch { /* ignore */ }
  }, []);
  const go = useCallback((hash: string) => { window.location.hash = hash; }, []);
  const bump = useCallback(() => setRefresh((k) => k + 1), []);
  return <Ctx.Provider value={{ mode, setMode, route, go, refreshKey, bump }}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}
