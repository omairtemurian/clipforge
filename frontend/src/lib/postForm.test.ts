import { describe, expect, it } from "vitest";
import type { SocialAccount } from "@/api/types";
import {
  DEFAULT_BULK,
  bulkBody,
  draftsOf,
  fieldsOf,
  futureTime,
  parseTimes,
  postProblem,
  postText,
  targetsOf,
  whenProblem,
} from "./postForm";

const TEXTS = {
  title: "Pizza night",
  description: "A man and a whole pizza.",
  hashtags: ["pizza", "funny"],
};

function account(
  id: number,
  platform: SocialAccount["platform"],
): SocialAccount {
  return {
    id,
    platform,
    external_id: `${platform}-${id}`,
    display_name: `${platform} ${id}`,
    token_ref: "ref",
    scopes: [],
    connected_at: "2026-11-01T10:00:00",
    restrictions: [],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
  };
}

describe("post form", () => {
  it("fills each platform from the clip, the title in the caption where there is no title", () => {
    expect(fieldsOf("youtube", TEXTS)).toEqual({
      title: "Pizza night",
      caption: "A man and a whole pizza.",
      hashtags: "#pizza #funny",
      privacy: "public",
    });
    expect(fieldsOf("tiktok", TEXTS)).toEqual({
      title: "",
      caption: "Pizza night\n\nA man and a whole pizza.",
      hashtags: "#pizza #funny",
      privacy: "",
    });
  });

  it("sends the typed text; title-less platforms send an empty title", () => {
    const drafts = draftsOf(TEXTS);
    drafts.tiktok.privacy = "SELF_ONLY";
    drafts.tiktok.hashtags = "#food, eat";

    const targets = targetsOf(
      [account(1, "youtube"), account(2, "tiktok"), account(3, "x")],
      drafts,
    );

    expect(targets).toHaveLength(2);
    expect(targets[1]).toEqual({
      account_id: 2,
      text: {
        title: "",
        caption: "Pizza night\n\nA man and a whole pizza.",
        hashtags: ["food", "eat"],
        link: null,
        privacy: "SELF_ONLY",
        collaborators: [],
        options: {},
      },
    });
    expect(postText("youtube", drafts.youtube).title).toBe("Pizza night");
  });

  it("says what keeps the posts from going out", () => {
    const drafts = draftsOf(TEXTS);
    drafts.youtube.title = " ";

    expect(postProblem([], drafts)).toMatch(/Choose an account/);
    expect(postProblem([account(1, "youtube")], drafts)).toMatch(/title/);
    expect(postProblem([account(2, "tiktok")], drafts)).toMatch(/TikTok/);
    drafts.tiktok.privacy = "SELF_ONLY";
    expect(postProblem([account(2, "tiktok")], drafts)).toBeNull();
  });

  it("takes only valid times of day, sorted and once", () => {
    expect(parseTimes("18:00, 09:00 9:00 25:00 09:00")).toEqual([
      "09:00",
      "18:00",
    ]);
  });

  it("builds the bulk body in the browser's timezone and queues it", () => {
    const targets = targetsOf([account(1, "youtube")], draftsOf(TEXTS));
    const body = bulkBody(
      [7],
      targets,
      { ...DEFAULT_BULK, skipDays: ["sun"], startDate: "2030-01-14" },
      "Europe/Zurich",
    );

    expect(body).toEqual({
      clip_ids: [7],
      targets,
      rules: {
        timezone: "Europe/Zurich",
        times: ["09:00", "18:00"],
        posts_per_day: 1,
        skip_days: ["sun"],
        start_date: "2030-01-14",
      },
      queue: true,
    });
    expect(
      bulkBody([7], targets, { ...DEFAULT_BULK, times: "soon" }),
    ).toBeNull();
    expect(bulkBody([], targets, DEFAULT_BULK)).toBeNull();
  });

  it("needs a time later than now to schedule", () => {
    const now = new Date("2030-01-14T12:00:00Z");

    expect(futureTime("", now)).toBeNull();
    expect(futureTime("2020-01-01T09:00", now)).toBeNull();
    expect(futureTime("2031-01-01T09:00", now)).toMatch(/^2031-01-01T/);
    expect(whenProblem("at", "", DEFAULT_BULK, now)).toMatch(/later/);
    expect(
      whenProblem("bulk", "", { ...DEFAULT_BULK, times: "" }, now),
    ).toMatch(/time of day/);
    expect(whenProblem("now", "", DEFAULT_BULK, now)).toBeNull();
  });
});
