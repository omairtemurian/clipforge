import { describe, expect, it } from "vitest";
import { clip } from "@/testing/mockApi";
import { previewUrl } from "@/lib/previewUrl";

describe("previewUrl", () => {
  it("changes with the clip's edits but not with its render status", () => {
    const saved = clip({ id: 7 });
    const url = previewUrl(saved);

    expect(url).toMatch(/^\/api\/clips\/7\/preview\?v=[0-9a-z]+$/);
    expect(previewUrl({ ...saved })).toBe(url);
    expect(
      previewUrl({ ...saved, status: "rendered", output_path: "/x.mp4" }),
    ).toBe(url);
    expect(previewUrl({ ...saved, layout: "fit" })).not.toBe(url);
  });
});
