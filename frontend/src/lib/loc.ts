import { useTranslation } from "react-i18next";

export type Loc = { en: string; "zh-TW": string };

/** Pick the current language from a {en, zh-TW} object coming from mission / research data. */
export function useLoc() {
  const { i18n } = useTranslation();
  return (v?: Loc | null): string => {
    if (!v) return "";
    return (i18n.language === "zh-TW" ? v["zh-TW"] : v.en) || v.en;
  };
}
