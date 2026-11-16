import { describe, expect, it } from "vitest";
import { checkVideoUrl, firstVideoFile, isVideoFile } from "./videoSource";

describe("checkVideoUrl", () => {
  it.each([
    "https://www.youtube.com/watch?v=abc123",
    "http://example.com/video.mp4",
    "  https://youtu.be/abc  ",
  ])("accepts %s", (text) => {
    expect(checkVideoUrl(text)).toEqual({ ok: true, url: text.trim() });
  });

  it("adds https:// to a link typed without a scheme", () => {
    expect(checkVideoUrl("youtube.com/watch?v=abc")).toEqual({
      ok: true,
      url: "https://youtube.com/watch?v=abc",
    });
  });

  it.each([
    "",
    "   ",
    "hello",
    "ftp://example.com/a.mp4",
    "/tmp/a.mp4",
    "http://",
  ])("rejects %j", (text) => {
    const result = checkVideoUrl(text);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.message).not.toBe("");
  });

  it("asks for a link when the input is empty", () => {
    expect(checkVideoUrl(" ")).toEqual({
      ok: false,
      message: "Paste a video link first.",
    });
  });
});

describe("video files", () => {
  const file = (name: string, type = "") => new File(["x"], name, { type });

  it("recognizes a video by MIME type or extension", () => {
    expect(isVideoFile(file("a.bin", "video/mp4"))).toBe(true);
    expect(isVideoFile(file("Clip.MKV"))).toBe(true);
    expect(isVideoFile(file("notes.txt", "text/plain"))).toBe(false);
  });

  it("picks the first video", () => {
    const video = file("b.mp4", "video/mp4");
    expect(firstVideoFile([file("a.txt"), video])).toBe(video);
    expect(firstVideoFile([file("a.txt")])).toBeNull();
  });
});
