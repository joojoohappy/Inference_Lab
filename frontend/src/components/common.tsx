import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { Provenance, Run } from "../lib/api";

const PROV_CLASS: Record<string, string> = {
  LIVE_MEASURED: "live", VERIFIED_IMPORTED: "imported", DEMO_SAMPLE: "demo", NOT_RUN: "notrun", FAILED: "failed",
};

export function ProvenanceBadge({ value }: { value: Provenance | string | null | undefined }) {
  const { t } = useTranslation();
  if (!value) return null;
  return (
    <span className={`badge ${PROV_CLASS[value] ?? "neutral"}`} title={t(`provenance.${value}.help`)} data-provenance={value}>
      {t(`provenance.${value}.label`)}
    </span>
  );
}

const STATUS_CLASS: Record<string, string> = {
  succeeded: "live", failed: "failed", blocked: "demo", not_run: "notrun", running: "cyan", pending: "neutral",
};

export function StatusBadge({ run }: { run: Pick<Run, "status"> }) {
  const { t } = useTranslation();
  return (
    <span className={`badge ${STATUS_CLASS[run.status] ?? "neutral"}`} data-status={run.status}>
      {run.status === "running" && <span className="dot pulse" aria-hidden />}
      {t(`status.${run.status}`)}
    </span>
  );
}

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const { t } = useTranslation();
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="btn tiny ghost"
      onClick={async () => {
        try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* clipboard blocked */ }
      }}
      aria-label={label ?? t("common.copy")}
    >
      {done ? t("common.copied") : t("common.copy")}
    </button>
  );
}

export function CommandBox({ command, label }: { command: string; label?: string }) {
  const { t } = useTranslation();
  return (
    <div>
      {label && <div className="small dim" style={{ marginBottom: 4 }}>{label}</div>}
      <div className="cmd" role="group" aria-label={label ?? t("run.command")}>
        <span className="prompt" aria-hidden>$</span>
        <pre>{command}</pre>
        <CopyButton text={command} />
      </div>
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); prev?.focus(); };
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <div className="row" style={{ marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 17 }}>{title}</h2>
          <span className="spacer" />
          <button type="button" className="btn tiny" onClick={onClose}>{t("common.close")}</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function fmt(x: unknown, digits = 1): string {
  if (x === null || x === undefined) return "—";
  if (typeof x === "number") return Number.isInteger(x) ? String(x) : x.toFixed(digits);
  return String(x);
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="callout muted">{children}</div>;
}
