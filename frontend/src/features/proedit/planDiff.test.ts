import { describe, expect, it } from "vitest";
import { PLAN, PLAN_V2 } from "@/testing/proeditFixtures";
import { diffPlans } from "./planDiff";

describe("diffPlans", () => {
  it("lists changed, added and removed items by id", () => {
    expect(diffPlans(PLAN, PLAN_V2)).toEqual([
      {
        op: "changed",
        itemId: 1,
        label: "Zoom punch",
        details: [
          "00:02.00–00:02.50 → 00:02.20–00:02.70",
          "scale unset → 1.3",
          "ease unset → ease_in_out",
          "ease_frames unset → 0",
        ],
      },
      { op: "added", itemId: 3, label: "Flash", details: [] },
      { op: "removed", itemId: 2, label: "SFX", details: [] },
    ]);
  });

  it("finds nothing between a plan and itself", () => {
    expect(diffPlans(PLAN, { ...PLAN, version: 2 })).toEqual([]);
  });
});
