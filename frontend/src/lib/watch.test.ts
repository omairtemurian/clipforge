import { describe, expect, it } from "vitest";
import { watchEvent } from "@/testing/watchFixtures";
import {
  alertText,
  durationLabel,
  watchModeLabel,
  watchStatusLine,
} from "./watch";

describe("watch labels", () => {
  it.each([
    [0, "0 s"],
    [42_400, "42 s"],
    [61_000, "1 min"],
    [3_600_000, "1 h"],
    [7_500_000, "2 h 5 min"],
    [3 * 86_400_000, "3 d"],
    [-5000, "0 s"],
  ])("durationLabel(%i) is %s", (ms, label) => {
    expect(durationLabel(ms)).toBe(label);
  });

  it.each([
    ["subscribed", "Push"],
    ["pending", "Push pending"],
    ["off", "Polling every 45 s"],
    ["revoked", "Polling every 45 s (push revoked)"],
  ] as const)("watchModeLabel(%s)", (state, label) => {
    expect(watchModeLabel(state, 45)).toBe(label);
  });

  it("says whether push is on", () => {
    const status = {
      push_available: false,
      poll_interval_s: 30,
      twitch_configured: false,
      handles_supported: false,
    };
    expect(watchStatusLine(status)).toMatch(/^Polling every 30 s\./);
    expect(watchStatusLine({ ...status, push_available: true })).toMatch(
      /^Push is on/,
    );
  });

  it("words an upload and a go-live with the time since publish", () => {
    expect(alertText(watchEvent())).toEqual({
      title: "New upload from YouTube",
      body: "Big news (42 s after publish)",
    });
    expect(
      alertText(
        watchEvent({
          kind: "live",
          platform: "twitch",
          source_name: "Afro",
          title: "",
          published_at: "2026-10-31T13:58:00",
        }),
      ),
    ).toEqual({
      title: "Afro is live",
      body: "Live on Twitch (live for 2 min)",
    });
    expect(alertText(watchEvent({ published_at: null })).body).toBe("Big news");
  });
});
