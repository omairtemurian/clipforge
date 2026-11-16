import { describe, expect, it } from "vitest";
import { localIso, post } from "@/testing/postFixtures";
import {
  NO_FILTERS,
  canDrag,
  dayKey,
  filterPosts,
  monthWeeks,
  movedTime,
  postTime,
  postTitle,
  postsByDay,
  rangeTitle,
  shiftAnchor,
  weekDays,
} from "./calendar";

const keys = (days: Date[]) => days.map(dayKey);

describe("calendar days", () => {
  it("covers a month with Sunday-first weeks", () => {
    const weeks = monthWeeks(new Date(2026, 10, 18));

    expect(weeks).toHaveLength(5);
    expect(keys(weeks[0])).toEqual([
      "2026-11-01",
      "2026-11-02",
      "2026-11-03",
      "2026-11-04",
      "2026-11-05",
      "2026-11-06",
      "2026-11-07",
    ]);
    expect(keys(weeks[4])[0]).toBe("2026-11-29");
    expect(keys(weeks[4])[6]).toBe("2026-12-05");
  });

  it("starts with the days of the previous month when the 1st is not a Sunday", () => {
    const weeks = monthWeeks(new Date(2026, 9, 1));

    expect(keys(weeks[0])[0]).toBe("2026-09-27");
    expect(keys(weeks.at(-1)!)[6]).toBe("2026-10-31");
    expect(weeks).toHaveLength(5);
    expect(monthWeeks(new Date(2026, 1, 10))).toHaveLength(4);
  });

  it("gives the week of a day and steps by month or week", () => {
    expect(keys(weekDays(new Date(2026, 10, 4)))[0]).toBe("2026-11-01");
    expect(dayKey(shiftAnchor(new Date(2026, 10, 30), "month", 1))).toBe(
      "2026-12-01",
    );
    expect(dayKey(shiftAnchor(new Date(2026, 0, 15), "month", -1))).toBe(
      "2025-12-01",
    );
    expect(dayKey(shiftAnchor(new Date(2026, 10, 30), "week", 1))).toBe(
      "2026-12-07",
    );
  });

  it("titles a month and a week", () => {
    expect(rangeTitle(new Date(2026, 10, 2), "month")).toMatch(/November 2026/);
    expect(rangeTitle(new Date(2026, 10, 4), "week")).toMatch(/Nov.*1.*7/);
  });
});

describe("calendar posts", () => {
  it("puts each post on its local day, earliest first", () => {
    const late = post({ id: 1, scheduled_at: localIso(2026, 11, 3, 18) });
    const early = post({ id: 2, scheduled_at: localIso(2026, 11, 3, 6) });
    const other = post({ id: 3, scheduled_at: localIso(2026, 11, 4, 9) });
    const unscheduled = post({ id: 4, status: "draft", scheduled_at: null });

    const days = postsByDay([late, early, other, unscheduled]);

    expect(days.get("2026-11-03")?.map((p) => p.id)).toEqual([2, 1]);
    expect(days.get("2026-11-04")?.map((p) => p.id)).toEqual([3]);
    expect([...days.keys()]).toHaveLength(2);
  });

  it("places a post sent right away on the day it was sent", () => {
    const sent = post({
      status: "published",
      scheduled_at: null,
      attempted_at: "2026-11-02T10:36:00Z",
    });

    expect(postTime(sent)?.toISOString()).toBe("2026-11-02T10:36:00.000Z");
  });

  it("hides canceled posts unless asked for, and filters", () => {
    const posts = [
      post({ id: 1 }),
      post({ id: 2, status: "canceled" }),
      post({ id: 3, platform: "tiktok", account_id: 2, status: "published" }),
    ];
    const ids = (shown: typeof posts) => shown.map((p) => p.id);

    expect(ids(filterPosts(posts, NO_FILTERS))).toEqual([1, 3]);
    expect(
      ids(filterPosts(posts, { ...NO_FILTERS, status: "canceled" })),
    ).toEqual([2]);
    expect(
      ids(filterPosts(posts, { ...NO_FILTERS, platform: "tiktok" })),
    ).toEqual([3]);
    expect(ids(filterPosts(posts, { ...NO_FILTERS, accountId: 1 }))).toEqual([
      1,
    ]);
  });

  it("titles a card by the title, else the caption's first line", () => {
    expect(postTitle(post())).toBe("Pizza night");
    expect(
      postTitle(post({ payload: { caption: "Big news\n\n#pizza" } })),
    ).toBe("Big news");
    expect(postTitle(post({ payload: {} }))).toBe("Untitled post");
  });

  it("drags only scheduled posts and keeps the time of day", () => {
    expect(canDrag(post({ status: "queued" }))).toBe(true);
    expect(canDrag(post({ status: "published" }))).toBe(false);
    expect(canDrag(post({ status: "draft" }))).toBe(false);

    const moved = movedTime(
      new Date(2026, 10, 3, 18, 30),
      new Date(2026, 10, 9),
    );
    expect(moved).toEqual(new Date(2026, 10, 9, 18, 30));
  });
});
