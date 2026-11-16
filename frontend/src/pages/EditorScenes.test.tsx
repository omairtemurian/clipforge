import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, CropTrack } from "@/api/types";
import { CLIP, mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { callsTo, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// The 9:16 window (404x720) of a 1280x720 source starts at x 100 at 10 s.
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

/** The editor of CLIP (10-40 s, 20-25 cut) whose source cuts at 30 s. */
function renderScenes() {
  return renderEditor(undefined, undefined, {
    "GET /api/clips/7/scenes": () => json({ cuts: [30], scenes: [] }),
    "GET /api/clips/7/crop": () => json(TRACK),
    "PATCH /api/clips/7": (_url, init) =>
      json({ ...CLIP, ...JSON.parse(String(init?.body)) } satisfies Clip),
  });
}

function segmentLabels() {
  const row = screen.getByLabelText("Segments");
  return within(row)
    .getAllByRole("button")
    .map((block) => block.textContent);
}

async function chooseFixed(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Layout" }));
  const panel = screen.getByRole("complementary", { name: "Layout panel" });
  await within(panel).findByText("Scene 1 of 2 · 00:10.00 – 00:30.00");
  await user.click(within(panel).getByRole("radio", { name: "Fixed" }));
  return panel;
}

describe("scenes", () => {
  it("splits the segment row at the scene cut and frames a scene as fixed", async () => {
    const user = userEvent.setup();
    renderScenes();
    await waitFor(() =>
      expect(segmentLabels()).toEqual(["Fill", "Fill", "Fill"]),
    );

    const panel = await chooseFixed(user);
    expect(within(panel).getByRole("radio", { name: "Fixed" })).toBeChecked();
    expect(segmentLabels()).toEqual(["Fixed", "Fixed", "Fill"]);

    await user.click(
      within(panel).getByRole("button", { name: "Apply to all scenes" }),
    );
    expect(segmentLabels()).toEqual(["Fixed", "Fixed", "Fixed"]);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await user.click(within(panel).getByRole("radio", { name: "Auto" }));
    expect(segmentLabels()).toEqual(["Fill", "Fill", "Fill"]);
  });

  it("sets, moves and deletes a fixed scene's keyframes, and saves them", async () => {
    const user = userEvent.setup();
    const fetchMock = renderScenes();
    await chooseFixed(user);
    await user.click(screen.getByRole("button", { name: "Crop" }));
    const box = await screen.findByRole("group", { name: "Crop window" });
    // Without keyframes the scene holds the window of its start.
    expect(box.style.left).toBe("7.8125%");

    fireEvent.pointerDown(box, { button: 0, clientX: 100, pointerId: 1 });
    fireEvent.pointerMove(box, { clientX: 160, pointerId: 1 });
    fireEvent.pointerUp(box, { pointerId: 1 });
    // 60 px is 128 source px: the window starts at x 228.
    expect(box.style.left).toBe("17.8125%");

    const keys = screen.getByLabelText("Keyframes");
    const diamond = within(keys).getByRole("button", {
      name: "Keyframe 00:10.00",
    });
    // 10 px per second: dragging 50 px moves the keyframe to 15 s.
    fireEvent.pointerDown(diamond, { button: 0, clientX: 100, pointerId: 2 });
    fireEvent.pointerMove(diamond, { clientX: 150, pointerId: 2 });
    fireEvent.pointerUp(diamond, { pointerId: 2 });
    expect(
      within(keys).getByRole("button", { name: "Keyframe 00:15.00" }),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
    );
    const body = JSON.parse(
      String(callsTo(fetchMock, "PATCH", "/api/clips/7")[0][1]?.body),
    );
    expect(body.layout).toBe("fill");
    expect(body.scene_reframes).toEqual([
      {
        start: 10,
        end: 30,
        mode: "fixed",
        layout: "fill",
        // (228 + 202) / 1280, to 4 digits.
        crop_keyframes: [{ t: 15, x: 0.3359, y: 0.5 }],
        scale: 1,
        track_seed: null,
      },
      {
        start: 30,
        end: 40,
        mode: "auto",
        layout: "fill",
        crop_keyframes: [],
        scale: 1,
        track_seed: null,
      },
    ]);

    within(keys).getByRole("button", { name: "Keyframe 00:15.00" }).focus();
    await user.keyboard("{Delete}");
    expect(within(keys).queryAllByRole("button")).toHaveLength(0);
    expect(box.style.left).toBe("7.8125%");
  });
});
