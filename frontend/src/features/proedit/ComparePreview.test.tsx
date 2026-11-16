import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CLIP, mockLayoutAndMedia } from "@/testing/editor";
import { ComparePreview } from "./ComparePreview";

/** Mock play and pause with each video's own paused state (the shared
 * mock has one for all). */
function mockPerVideoPlayback() {
  const playing = new WeakSet<HTMLMediaElement>();
  vi.spyOn(HTMLMediaElement.prototype, "paused", "get").mockImplementation(
    function (this: HTMLMediaElement) {
      return !playing.has(this);
    },
  );
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    playing.add(this);
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    playing.delete(this);
  });
}

beforeEach(() => {
  mockLayoutAndMedia();
  mockPerVideoPlayback();
});
afterEach(() => vi.restoreAllMocks());

const VARIANT = {
  ...CLIP,
  id: 12,
  parent_clip_id: 7,
  variant: "pro_edit" as const,
  status: "rendered" as const,
};

/** Show the original clip 7 next to variant 12 (rendered unless
 * videoVersion is null); returns the onTime spy. */
function show(videoVersion: string | null = "v1") {
  const onTime = vi.fn();
  render(
    <ComparePreview
      original={CLIP}
      variant={VARIANT}
      videoVersion={videoVersion}
      seek={{ t: 0, n: 0 }}
      time={0}
      onTime={onTime}
    />,
  );
  return onTime;
}

/** Give video a loaded state at time t of a duration-long video. */
function loaded(video: HTMLElement, t: number, duration = 30) {
  Object.defineProperty(video, "readyState", {
    configurable: true,
    value: HTMLMediaElement.HAVE_ENOUGH_DATA,
  });
  Object.defineProperty(video, "duration", {
    configurable: true,
    value: duration,
  });
  Object.defineProperty(video, "currentTime", {
    configurable: true,
    writable: true,
    value: t,
  });
}

const original = () => screen.getByLabelText("Original preview");
const proEdit = () => screen.getByLabelText("Pro Edit preview");

describe("ComparePreview", () => {
  it("loads the original's preview, with a spinner until it can play", () => {
    show();

    expect(original().getAttribute("src")).toMatch(
      /^\/api\/clips\/7\/preview\?v=\w+$/,
    );
    expect(original()).toHaveAttribute("preload", "auto");
    expect(screen.getByText("Making the preview…")).toBeInTheDocument();

    fireEvent.loadedData(original());
    expect(screen.queryByText("Making the preview…")).not.toBeInTheDocument();
  });

  it("says when the original's preview could not be made", () => {
    show();

    fireEvent.error(original());

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The preview could not be made",
    );
  });

  it("plays the original in sync with the Pro Edit on Play both", async () => {
    const onTime = show();
    loaded(original(), 0);
    loaded(proEdit(), 0);
    const play = vi.mocked(HTMLMediaElement.prototype.play);

    await userEvent.click(screen.getByRole("button", { name: "Play both" }));
    expect(play.mock.contexts).toEqual([proEdit()]);

    // The Pro Edit plays from 2 s: the original is sought there and played.
    (proEdit() as HTMLVideoElement).currentTime = 2;
    fireEvent.playing(proEdit());
    expect((original() as HTMLVideoElement).currentTime).toBe(2);
    expect(play.mock.contexts).toEqual([proEdit(), original()]);

    // It drifts behind: the next time update brings it back.
    (original() as HTMLVideoElement).currentTime = 2.1;
    (proEdit() as HTMLVideoElement).currentTime = 3;
    fireEvent.timeUpdate(proEdit());
    expect(onTime).toHaveBeenLastCalledWith(3);
    expect((original() as HTMLVideoElement).currentTime).toBe(3);

    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect((original() as HTMLVideoElement).paused).toBe(true);
  });

  it("catches up when the original loads after Play both", async () => {
    show();
    loaded(proEdit(), 0);
    await userEvent.click(screen.getByRole("button", { name: "Play both" }));
    fireEvent.playing(proEdit());
    const play = vi.mocked(HTMLMediaElement.prototype.play);
    expect(play.mock.contexts).toEqual([proEdit()]);

    // The original's preview arrives while the Pro Edit is at 4 s.
    (proEdit() as HTMLVideoElement).currentTime = 4;
    loaded(original(), 0);
    act(() => {
      fireEvent.loadedData(original());
    });

    expect((original() as HTMLVideoElement).currentTime).toBe(4);
    expect(play.mock.contexts).toEqual([proEdit(), original()]);
  });

  it("leads with the original while the Pro Edit has no video", () => {
    const onTime = show(null);
    loaded(original(), 1.5);

    fireEvent.timeUpdate(original());

    expect(onTime).toHaveBeenCalledWith(1.5);
    expect(screen.getByText("The Pro Edit is not rendered yet.")).toBeVisible();
  });
});
