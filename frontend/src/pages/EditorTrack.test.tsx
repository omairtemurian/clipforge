import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, CropTrack, SceneTrack } from "@/api/types";
import {
  CLIP,
  mockLayoutAndMedia,
  renderEditor,
  video,
} from "@/testing/editor";
import { callsTo, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const TRACK: CropTrack = {
  aspect: "9:16",
  frame_width: 1280,
  frame_height: 720,
  width: 404,
  height: 720,
  y: 0,
  times: [10, 40],
  xs: [100, 500],
  facecam: null,
};

const TRACKED: SceneTrack = {
  keyframes: [
    { t: 10, x: 0.4, y: 0.5 },
    { t: 29.9, x: 0.6, y: 0.5 },
  ],
  seed: { t: 10, x: 0.45, y: 0.4, width: 0.1, height: 0.2 },
};

/** The editor of CLIP (10-40 s) whose source cuts at 30 s, where tracking
 * returns TRACKED. */
function renderTrack() {
  return renderEditor(undefined, undefined, {
    "GET /api/clips/7/scenes": () => json({ cuts: [30], scenes: [] }),
    "GET /api/clips/7/crop": () => json(TRACK),
    "POST /api/clips/7/scenes/track": () => json(TRACKED),
    "PATCH /api/clips/7": (_url, init) =>
      json({ ...CLIP, ...JSON.parse(String(init?.body)) } satisfies Clip),
  });
}

describe("click to track", () => {
  it("tracks the clicked subject through the scene and saves it", async () => {
    const user = userEvent.setup();
    const fetchMock = renderTrack();
    await user.click(await screen.findByRole("button", { name: "Layout" }));
    const before = video().getAttribute("src");
    const panel = screen.getByRole("complementary", { name: "Layout panel" });
    await within(panel).findByText("Scene 1 of 2 · 00:10.00 – 00:30.00");

    await user.click(within(panel).getByRole("radio", { name: "Track" }));
    const picker = await screen.findByRole("application", {
      name: "Pick the subject to track",
    });
    expect(
      within(panel).getByText(/follows the subject you click/),
    ).toBeVisible();

    // The frame is 600x56 on screen: a click at (300, 14) is (0.5, 0.25).
    fireEvent.pointerDown(picker, { button: 0, clientX: 300, clientY: 14 });
    fireEvent.pointerUp(picker, { clientX: 301, clientY: 14 });

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
    );
    const [[, track]] = callsTo(fetchMock, "POST", "/api/clips/7/scenes/track");
    expect(JSON.parse(String(track?.body))).toEqual({
      start: 10,
      end: 30,
      seed: { t: 10, x: 0.5, y: 0.25, width: 0, height: 0 },
    });
    const patch = JSON.parse(
      String(callsTo(fetchMock, "PATCH", "/api/clips/7")[0][1]?.body),
    );
    expect(patch.scene_reframes[0]).toEqual({
      start: 10,
      end: 30,
      mode: "track",
      layout: "fill",
      crop_keyframes: TRACKED.keyframes,
      scale: 1,
      track_seed: TRACKED.seed,
    });
    expect(patch.scene_reframes[1].mode).toBe("auto");

    await waitFor(() =>
      expect(
        screen.queryByRole("application", {
          name: "Pick the subject to track",
        }),
      ).toBe(null),
    );
    expect(video().getAttribute("src")).not.toBe(before);
    const keys = screen.getByLabelText("Keyframes");
    expect(within(keys).getAllByRole("button")).toHaveLength(2);
    expect(
      within(panel).getByRole("button", { name: "Pick another subject" }),
    ).toBeEnabled();
  });

  it("tracks a box dragged around the subject", async () => {
    const user = userEvent.setup();
    const fetchMock = renderTrack();
    await user.click(await screen.findByRole("button", { name: "Layout" }));
    const panel = screen.getByRole("complementary", { name: "Layout panel" });
    await within(panel).findByText("Scene 1 of 2 · 00:10.00 – 00:30.00");
    await user.click(within(panel).getByRole("radio", { name: "Track" }));
    const picker = await screen.findByRole("application", {
      name: "Pick the subject to track",
    });

    fireEvent.pointerDown(picker, { button: 0, clientX: 300, clientY: 42 });
    fireEvent.pointerMove(picker, { clientX: 240, clientY: 14 });
    fireEvent.pointerUp(picker, { clientX: 240, clientY: 14 });

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/clips/7/scenes/track"),
      ).toHaveLength(1),
    );
    const [[, track]] = callsTo(fetchMock, "POST", "/api/clips/7/scenes/track");
    expect(JSON.parse(String(track?.body)).seed).toEqual({
      t: 10,
      x: 0.4,
      y: 0.25,
      width: 0.1,
      height: 0.5,
    });
  });
});
