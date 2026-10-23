import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import zhTW from "./locales/zh-TW.json";

export const LANGS = ["en", "zh-TW"] as const;
export type Lang = (typeof LANGS)[number];
export const LANG_KEY = "inference-lab.lang";

/** English unless the user explicitly picked a language before. Never read navigator.language. */
export function initialLanguage(): Lang {
  try {
    const saved = window.localStorage.getItem(LANG_KEY);
    if (saved === "en" || saved === "zh-TW") return saved;
  } catch {
    /* storage blocked: fall back to English */
  }
  return "en";
}

export function setLanguage(lang: Lang): void {
  try {
    window.localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* ignore */
  }
  void i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, "zh-TW": { translation: zhTW } },
  lng: initialLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
