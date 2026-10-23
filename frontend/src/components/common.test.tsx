import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import "../i18n";
import { ProvenanceBadge, StatusBadge, fmt } from "./common";

describe("provenance badges", () => {
  it.each(["LIVE_MEASURED", "VERIFIED_IMPORTED", "DEMO_SAMPLE", "NOT_RUN", "FAILED"])("%s renders a distinct labelled badge", (p) => {
    render(<ProvenanceBadge value={p} />);
    const el = document.querySelector(`[data-provenance="${p}"]`)!;
    expect(el).toBeInTheDocument();
    expect(el.textContent).not.toBe(p); // translated label, not the raw enum
    expect(el.getAttribute("title")).toBeTruthy();
  });

  it("demo and live never share a style", () => {
    render(<><ProvenanceBadge value="DEMO_SAMPLE" /><ProvenanceBadge value="LIVE_MEASURED" /></>);
    const demo = document.querySelector('[data-provenance="DEMO_SAMPLE"]')!.className;
    const live = document.querySelector('[data-provenance="LIVE_MEASURED"]')!.className;
    expect(demo).not.toBe(live);
  });

  it("failed runs show as failed", () => {
    render(<StatusBadge run={{ status: "failed" }} />);
    expect(screen.getByText("Failed")).toHaveAttribute("data-status", "failed");
  });
});

describe("fmt", () => {
  it("formats numbers and missing values", () => {
    expect(fmt(null)).toBe("—");
    expect(fmt(3)).toBe("3");
    expect(fmt(2.345, 2)).toBe("2.35");
  });
});
