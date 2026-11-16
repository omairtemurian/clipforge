import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProgressPill } from "./ProgressPill";

describe("ProgressPill", () => {
  it("shows the percent and the ETA and fills up to the percent", () => {
    render(
      <ProgressPill
        name="Talk"
        progress={{ label: "Transcribe", percent: 48, etaSeconds: 300 }}
      />,
    );

    const bar = screen.getByRole("progressbar", { name: "Talk progress" });
    expect(bar).toHaveTextContent("48% (ETA 5m)");
    expect(bar).toHaveAttribute("aria-valuenow", "48");
    expect(screen.getByTestId("progress-fill")).toHaveStyle({ width: "48%" });
  });

  it("shows an ellipsis while the ETA is unknown", () => {
    render(
      <ProgressPill
        name="Talk"
        progress={{ label: "Starting", percent: 2, etaSeconds: null }}
      />,
    );

    expect(screen.getByRole("progressbar")).toHaveTextContent("2% (ETA …)");
  });
});
