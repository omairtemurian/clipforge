import { describe, expect, it } from "vitest";
import type { ClipVersionInfo } from "@/api/types";
import { fieldsLabel, versionSummary } from "./versions";

function version(overrides: Partial<ClipVersionInfo>): ClipVersionInfo {
  return {
    number: 2,
    kind: "edit",
    created_at: "2026-11-01T20:00:00",
    fields: [],
    restored_from: null,
    ...overrides,
  };
}

describe("version labels", () => {
  it("names the changed fields in words, once each", () => {
    expect(fieldsLabel(["segments", "cut_ranges"])).toBe("trim, cuts");
    expect(fieldsLabel(["caption_style", "caption_template"])).toBe("captions");
    expect(
      fieldsLabel(["title", "hook_text", "layout", "tracks", "brand_new"]),
    ).toBe("title, hook, layout, +2 more");
  });

  it("summarizes what a version did", () => {
    expect(versionSummary(version({ kind: "original", number: 1 }))).toBe(
      "Original clip",
    );
    expect(versionSummary(version({ kind: "restore", restored_from: 1 }))).toBe(
      "Restored version 1",
    );
    expect(versionSummary(version({ fields: ["title"] }))).toBe("Edited title");
  });
});
