import { describe, expect, it } from "vitest";
import {
  clipCountLabel,
  formatBytes,
  formatDate,
  formatDuration,
  formatTimecode,
  projectName,
  timeAgo,
} from "./format";
import type { Project } from "@/api/types";

describe("format", () => {
  it("formats a UTC date without zone as local yyyy.mm.dd", () => {
    expect(formatDate("2026-10-30T12:00:00")).toBe("2026.10.30");
    expect(formatDate("2026-10-30T12:00:00+00:00")).toBe("2026.10.30");
    expect(formatDate("nonsense")).toBe("");
  });

  it("pluralizes clips", () => {
    expect(clipCountLabel(1)).toBe("1 clip");
    expect(clipCountLabel(0)).toBe("0 clips");
    expect(clipCountLabel(19)).toBe("19 clips");
  });

  it("names a project by title, link or file name", () => {
    const base = {
      title: "",
      source_url: null,
      source_path: "",
    } as Project;
    expect(projectName({ ...base, title: "Talk" })).toBe("Talk");
    expect(projectName({ ...base, source_url: "https://x.io/v" })).toBe(
      "https://x.io/v",
    );
    expect(projectName({ ...base, source_path: "/a/b/demo.mp4" })).toBe(
      "demo.mp4",
    );
    expect(projectName(base)).toBe("Untitled video");
  });
});

describe("formatDuration", () => {
  it("shows mm:ss below an hour and h:mm:ss from one hour on", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(754.4)).toBe("12:34");
    expect(formatDuration(3725)).toBe("1:02:05");
  });
});

describe("formatTimecode", () => {
  it("shows mm:ss.cc with hundredths", () => {
    expect(formatTimecode(0)).toBe("00:00.00");
    expect(formatTimecode(34.186)).toBe("00:34.19");
    expect(formatTimecode(100.18)).toBe("01:40.18");
    expect(formatTimecode(59.999)).toBe("01:00.00");
    expect(formatTimecode(-3)).toBe("00:00.00");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-11-01T12:00:00Z");
  it("says how long ago a timestamp was", () => {
    expect(timeAgo("2026-11-01T11:59:30", now)).toBe("just now");
    expect(timeAgo("2026-11-01T11:55:00", now)).toBe("5 min ago");
    expect(timeAgo("2026-11-01T09:00:00", now)).toBe("3 h ago");
    expect(timeAgo("2026-10-30T12:00:00", now)).toMatch(/^2026\.10\.(29|30)$/);
    expect(timeAgo("not a date", now)).toBe("");
  });
});

describe("formatBytes", () => {
  it("names the size in decimal units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(999)).toBe("999 B");
    expect(formatBytes(1_500)).toBe("1.5 KB");
    expect(formatBytes(2_000_000)).toBe("2 MB");
    expect(formatBytes(12_340_000_000)).toBe("12 GB");
    expect(formatBytes(3_456_000_000_000)).toBe("3.5 TB");
  });
});
