import { describe, expect, it } from "vitest";
import { localIso, post } from "@/testing/postFixtures";
import { historyTime, historyWhen } from "./postHistory";

describe("historyTime", () => {
  it("is when the latest upload started, else the scheduled time", () => {
    const tried = post({
      attempted_at: localIso(2026, 11, 2, 9, 30),
      scheduled_at: localIso(2026, 11, 2, 9),
    });
    const skipped = post({ status: "skipped" });

    expect(historyTime(tried)).toEqual(new Date(2026, 10, 2, 9, 30));
    expect(historyTime(skipped)?.toISOString()).toBe(
      "2030-01-14T08:00:00.000Z",
    );
    expect(historyTime(post({ scheduled_at: null }))).toBeNull();
  });
});

describe("historyWhen", () => {
  it("says what happened and when", () => {
    const at = localIso(2026, 11, 2, 15, 4);
    const time = new Date(at).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });

    expect(historyWhen(post({ status: "published", attempted_at: at }))).toBe(
      `Posted ${time}`,
    );
    expect(historyWhen(post({ status: "failed", attempted_at: at }))).toBe(
      `Failed ${time}`,
    );
    expect(historyWhen(post({ status: "skipped", scheduled_at: at }))).toBe(
      `Skipped, was due ${time}`,
    );
    expect(historyWhen(post({ status: "failed", scheduled_at: null }))).toBe(
      "Failed",
    );
  });
});
