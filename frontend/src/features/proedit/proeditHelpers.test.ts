import { describe, expect, it } from "vitest";
import type { Clip } from "@/api/types";
import { clip } from "@/testing/mockApi";
import { DEFAULT_OPTIONS, estimateQuery, intensitiesUpTo } from "./options";
import { criticRound, overallPercent, progressSteps } from "./progress";
import { heavyEditsWarning } from "./useProEditForm";
import { groupVariants } from "./variants";

const START = { mode: "start" as const, options: DEFAULT_OPTIONS };

function event(step: string, progress: number, status = "running") {
  return {
    step,
    progress,
    status: status as "running" | "done" | "failed",
    message: "",
    overall_progress: 0.4,
  };
}

describe("progressSteps", () => {
  it("lists plan, proxy, critic round 1/N and final before any event", () => {
    const steps = progressSteps(START, null, 3);
    expect(steps.map((step) => [step.label, step.state])).toEqual([
      ["Plan", "running"],
      ["Proxy", "pending"],
      ["Critic round 1/3", "pending"],
      ["Final render", "pending"],
    ]);
  });

  it("counts the critic's round from its progress", () => {
    expect(criticRound(0, 2)).toBe(1);
    expect(criticRound(0.5, 2)).toBe(2);
    expect(criticRound(1, 2)).toBe(2);
    expect(criticRound(2 / 3, 3)).toBe(3);
  });

  it("drops the critic steps without the critic and the plan of a critic run", () => {
    const noCritic = {
      ...START,
      options: { ...DEFAULT_OPTIONS, use_critic: false },
    };
    expect(progressSteps(noCritic, null, 2).map((step) => step.key)).toEqual([
      "plan",
      "final",
    ]);
    expect(
      progressSteps({ mode: "critic", options: null }, null, 2).map(
        (step) => step.key,
      ),
    ).toEqual(["proxy", "critic", "final"]);
    expect(
      progressSteps({ mode: "render", options: null }, null, 2).map(
        (step) => step.key,
      ),
    ).toEqual(["final"]);
  });

  it("marks the job's step failed and every step done at the end", () => {
    const failed = progressSteps(START, event("proxy", 0.2, "failed"), 2);
    expect(failed.map((step) => step.state)).toEqual([
      "done",
      "failed",
      "pending",
      "pending",
    ]);
    const done = progressSteps(START, event("final", 1, "done"), 2);
    expect(done.every((step) => step.state === "done")).toBe(true);
  });

  it("gives the overall percent, 100 once done", () => {
    expect(overallPercent(null)).toBe(0);
    expect(overallPercent(event("plan", 0.1))).toBe(40);
    expect(overallPercent(event("final", 1, "done"))).toBe(100);
  });
});

describe("options", () => {
  it("caps the intensities and writes the estimate query", () => {
    expect(intensitiesUpTo("standard")).toEqual(["clean", "standard"]);
    expect(intensitiesUpTo("extreme")).toHaveLength(4);
    expect(estimateQuery(DEFAULT_OPTIONS)).toBe(
      "preset=clean_pro&intensity=standard&music=auto&use_critic=true&loop_ending=false",
    );
  });

  it("warns unless the campaign allows heavy edits", () => {
    const base = { campaign_id: 1, campaign_name: "Pizza Clips" };
    expect(
      heavyEditsWarning({ ...base, allow_heavy_edits: "true" }),
    ).toBeNull();
    expect(
      heavyEditsWarning({
        campaign_id: null,
        campaign_name: null,
        allow_heavy_edits: null,
      }),
    ).toBeNull();
    expect(heavyEditsWarning({ ...base, allow_heavy_edits: "false" })).toMatch(
      /^Pizza Clips does not allow heavy edits/,
    );
    expect(
      heavyEditsWarning({ ...base, allow_heavy_edits: "unknown" }),
    ).toMatch(/^Pizza Clips does not say whether heavy edits are allowed/);
  });
});

describe("groupVariants", () => {
  const variant = (id: number, parent: number): Clip =>
    clip({ id, parent_clip_id: parent, variant: "pro_edit" });

  it("puts each variant right after its original, oldest first", () => {
    const clips = [
      variant(21, 2),
      clip({ id: 1 }),
      variant(20, 2),
      clip({ id: 2 }),
      variant(30, 99),
    ];
    expect(groupVariants(clips).map((item) => item.id)).toEqual([
      1, 2, 20, 21, 30,
    ]);
  });
});
