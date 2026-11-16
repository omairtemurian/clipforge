import { describe, expect, it } from "vitest";
import { formatEta, progressText } from "./projectEta";

describe("formatEta", () => {
  it("is an ellipsis while the ETA is unknown", () => {
    expect(formatEta(null)).toBe("ETA …");
    expect(formatEta(undefined)).toBe("ETA …");
  });

  it("says under a minute, then minutes, then hours and minutes", () => {
    expect(formatEta(0)).toBe("ETA <1m");
    expect(formatEta(59)).toBe("ETA <1m");
    expect(formatEta(60)).toBe("ETA 1m");
    expect(formatEta(300)).toBe("ETA 5m");
    expect(formatEta(3600)).toBe("ETA 1h");
    expect(formatEta(4200)).toBe("ETA 1h 10m");
    expect(formatEta(7500)).toBe("ETA 2h 5m");
  });
});

describe("progressText", () => {
  it("joins the percent and the ETA", () => {
    expect(progressText(48, 300)).toBe("48% (ETA 5m)");
    expect(progressText(3, null)).toBe("3% (ETA …)");
  });
});
