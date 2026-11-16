import { describe, expect, it } from "vitest";
import type { WatchedChannel, WatchedVideo } from "@/api/types";
import {
  channelName,
  importedVideos,
  lastCheckedLabel,
  newProjectsLabel,
} from "./autoImport";

const NOW = new Date("2026-10-31T12:00:00Z");

describe("lastCheckedLabel", () => {
  it.each([
    [null, "Not checked yet"],
    ["2026-10-31T11:59:40", "Checked just now"],
    ["2026-10-31T11:55:00", "Checked 5 min ago"],
    ["2026-10-31T09:00:00+00:00", "Checked 3 h ago"],
    ["not a date", "Not checked yet"],
  ])("%s -> %s", (iso, label) => {
    expect(lastCheckedLabel(iso, NOW)).toBe(label);
  });

  it("gives the date after a day", () => {
    expect(lastCheckedLabel("2026-10-29T12:00:00", NOW)).toMatch(
      /^Checked 2026\.10\.(29|30)$/,
    );
  });
});

describe("channelName", () => {
  it("is the title, or the id before the feed was read", () => {
    const base = { channel_id: "UCBR8-60-B28hp2BmDPdntcQ" } as WatchedChannel;
    expect(channelName({ ...base, title: "YouTube" })).toBe("YouTube");
    expect(channelName({ ...base, title: "" })).toBe(base.channel_id);
  });
});

describe("importedVideos and newProjectsLabel", () => {
  it("keeps the videos that have a project", () => {
    const video = (id: string, project_id: number | null) =>
      ({ video_id: id, project_id }) as WatchedVideo;
    const videos = [video("a", 4), video("b", null), video("c", 2)];

    expect(importedVideos(videos).map((v) => v.video_id)).toEqual(["a", "c"]);
    expect([0, 1, 3].map(newProjectsLabel)).toEqual([
      "No new projects yet",
      "1 new project",
      "3 new projects",
    ]);
  });
});
