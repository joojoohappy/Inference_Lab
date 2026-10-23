import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "./locales/en.json";
import zh from "./locales/zh-TW.json";

const flat = (o: any, p = ""): string[] => Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? flat(v, `${p}${k}.`) : [`${p}${k}`]));

describe("language selection", () => {
  beforeEach(() => { localStorage.clear(); vi.resetModules(); });

  it("defaults to English even when the browser prefers zh-TW", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("zh-TW");
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["zh-TW", "zh"]);
    const { initialLanguage } = await import("./i18n");
    expect(initialLanguage()).toBe("en");
  });

  it("uses the saved explicit choice", async () => {
    localStorage.setItem("inference-lab.lang", "zh-TW");
    const { initialLanguage } = await import("./i18n");
    expect(initialLanguage()).toBe("zh-TW");
  });

  it("ignores garbage in storage", async () => {
    localStorage.setItem("inference-lab.lang", "fr");
    const { initialLanguage } = await import("./i18n");
    expect(initialLanguage()).toBe("en");
  });

  it("setLanguage persists and updates <html lang>", async () => {
    const mod = await import("./i18n");
    act(() => mod.setLanguage("zh-TW"));
    expect(localStorage.getItem("inference-lab.lang")).toBe("zh-TW");
    expect(document.documentElement.lang).toBe("zh-TW");
    expect(mod.default.language).toBe("zh-TW");
    act(() => mod.setLanguage("en"));
    expect(localStorage.getItem("inference-lab.lang")).toBe("en");
  });
});

describe("translation resources", () => {
  it("have identical key sets with no empty strings", () => {
    const a = flat(en).sort(), b = flat(zh).sort();
    expect(b).toEqual(a);
    const get = (o: any, k: string) => k.split(".").reduce((x, p) => x[p], o);
    for (const k of a) { expect(String(get(en, k)).trim(), k).not.toBe(""); expect(String(get(zh, k)).trim(), k).not.toBe(""); }
  });

  it("keep code identifiers untranslated", () => {
    expect((zh as any).arena.p.max_tokens).toBe("max_tokens");
    expect((zh as any).caps.cpu_inference).toContain("torch + transformers");
  });
});

describe("shell", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ missions: [], status: {}, progress: { missions: {} }, capabilities: {}, scanned: false, scan: null }), { status: 200 })));
  });

  it("switching language keeps the selected mode", async () => {
    const i18n = (await import("./i18n")).default;
    await i18n.changeLanguage("en");
    const { ModeSwitcher, LanguageSwitcher } = await import("./App");
    const { AppStateProvider } = await import("./lib/state");
    render(<AppStateProvider><ModeSwitcher /><LanguageSwitcher /></AppStateProvider>);
    fireEvent.click(screen.getByTestId("mode-expert"));
    fireEvent.click(screen.getByTestId("lang-zh-TW"));
    expect(await screen.findByText("專家")).toBeInTheDocument();
    expect(screen.getByTestId("mode-expert")).toHaveAttribute("aria-pressed", "true");
    expect(localStorage.getItem("inference-lab.mode")).toBe("expert");
    fireEvent.click(screen.getByTestId("lang-en"));
    expect(await screen.findByText("Expert")).toBeInTheDocument();
  });
});
