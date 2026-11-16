import { describe, expect, it } from "vitest";
import { DEFAULTS } from "@/testing/mockApi";
import type { ProcessingSettings } from "@/api/types";
import {
  parseTime,
  settingsToSend,
  templateLabel,
  timeframeFields,
  timeframeRange,
  toggleLength,
} from "./processingSettings";

describe("timeframe", () => {
  it("shows unset sides as the whole video, clamped to its length", () => {
    expect(timeframeRange(DEFAULTS, 600)).toEqual([0, 600]);
    expect(
      timeframeRange(
        { ...DEFAULTS, timeframe_start: 30, timeframe_end: 900 },
        600,
      ),
    ).toEqual([30, 600]);
  });

  it("leaves a side unset when the range reaches the video's edge", () => {
    expect(timeframeFields([0, 600], 600)).toEqual({
      timeframe_start: null,
      timeframe_end: null,
    });
    expect(timeframeFields([12, 300], 600)).toEqual({
      timeframe_start: 12,
      timeframe_end: 300,
    });
  });
});

describe("settingsToSend", () => {
  it("trims the keyword prompt and sends an empty one as null", () => {
    expect(
      settingsToSend({ ...DEFAULTS, keyword_prompt: "  dentist  " })
        .keyword_prompt,
    ).toBe("dentist");
    expect(settingsToSend({ ...DEFAULTS, keyword_prompt: "   " })).toEqual(
      DEFAULTS,
    );
  });
});

describe("toggleLength", () => {
  it("adds and removes ranges in the order of the chips", () => {
    expect(toggleLength(["auto"], "60_90")).toEqual(["60_90"]);
    expect(toggleLength(["60_90"], "lt30")).toEqual(["lt30", "60_90"]);
    expect(toggleLength(["lt30", "60_90"], "lt30")).toEqual(["60_90"]);
  });

  it("keeps Auto on its own and falls back to it when nothing is left", () => {
    expect(toggleLength(["lt30", "600_900"], "auto")).toEqual(["auto"]);
    expect(toggleLength(["auto"], "auto")).toEqual(["auto"]);
    expect(toggleLength(["180_300"], "180_300")).toEqual(["auto"]);
  });
});

describe("parseTime", () => {
  it("reads seconds, m:ss and h:mm:ss", () => {
    expect(parseTime("75")).toBe(75);
    expect(parseTime(" 1:15 ")).toBe(75);
    expect(parseTime("1:01:15")).toBe(3675);
    expect(parseTime("0:02.5")).toBe(2.5);
  });

  it("is null for text that is not a time", () => {
    for (const text of ["", "1:", "a:10", "-5", "1:2:3:4", "1,5"]) {
      expect(parseTime(text)).toBeNull();
    }
  });
});

describe("settingsToSend payload", () => {
  it("keeps every panel setting and sends at least one length", () => {
    const chosen: ProcessingSettings = {
      ...DEFAULTS,
      genre: "sports_commentary",
      length_presets: ["lt30", "300_600"],
      auto_headline: false,
      auto_color: true,
      captions: false,
      language: "es",
      subtitles_id: "ab".repeat(16),
      clipping: "captions_only",
    };
    expect(settingsToSend(chosen)).toEqual(chosen);
    const empty = {
      ...DEFAULTS,
      length_presets: [],
    } as unknown as ProcessingSettings;
    expect(settingsToSend(empty).length_presets).toEqual(["auto"]);
  });
});

describe("templateLabel", () => {
  it("turns a template name into words", () => {
    expect(templateLabel("karaoke_bold")).toBe("Karaoke bold");
    expect(templateLabel("clean_subtitle")).toBe("Clean subtitle");
  });
});
