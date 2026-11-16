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

// A 1280x720 source drawn 600 px wide (2.133 source px/px); reframe found
// the facecam box at the frame's middle top (x 640, 320 px wide).
const TRACK: CropTrack = {
  aspect: "9:16",
  frame_width: 1280,
  frame_height: 720,
  width: 404,
  height: 720,
  y: 0,
  times: [10, 40],
  xs: [100, 500],
  facecam: { x: 0.5, y: 0.1, width: 0.25, height: 0.4 },
};

/** The editor of CLIP (10-40 s, 20-25 cut) whose source cuts at 30 s. */
function renderLayouts() {
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

/** The tooltips of the segment chips: they keep the label a narrow chip drops. */
function segmentTitles() {
  const row = screen.getByLabelText("Segments");
  return within(row)
    .getAllByRole("button")
    .map((block) => block.getAttribute("title"));
}

async function choose(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(await screen.findByRole("button", { name: "Layout" }));
  const panel = screen.getByRole("complementary", { name: "Layout panel" });
  await within(panel).findByText("Scene 1 of 2 · 00:10.00 – 00:30.00");
  await user.click(within(panel).getByRole("radio", { name }));
  return panel;
}

async function savedBody(fetchMock: ReturnType<typeof renderLayouts>) {
  await waitFor(() =>
    expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
  );
  return JSON.parse(
    String(callsTo(fetchMock, "PATCH", "/api/clips/7")[0][1]?.body),
  );
}

describe("layout picker", () => {
  it("offers every layout and frames the scene at the playhead in one", async () => {
    const user = userEvent.setup();
    const fetchMock = renderLayouts();

    const panel = await choose(user, "Grid");
    const radios = within(
      within(panel).getByRole("radiogroup", { name: "Layout" }),
    ).getAllByRole("radio");
    expect(radios.map((radio) => radio.textContent)).toEqual([
      "Auto",
      "Track",
      "Fixed",
      "Fit",
      "Square",
      "Split",
      "Grid",
      "Picture in picture",
      "Screenshare + facecam",
      "Gameplay + facecam",
    ]);
    expect(within(panel).getByRole("radio", { name: "Grid" })).toBeChecked();
    expect(within(panel).getByText(/middle and right speaker/)).toBeVisible();
    expect(segmentLabels()).toEqual(["Grid", "Grid", "Fill"]);
    // The crop tool frames fill and facecam scenes only.
    expect(screen.queryByRole("button", { name: "Crop" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const body = await savedBody(fetchMock);
    expect(
      body.scene_reframes.map((scene: { layout: string }) => scene.layout),
    ).toEqual(["grid", "fill"]);
  });

  it("lists every layout in the player toolbar", async () => {
    const user = userEvent.setup();
    renderLayouts();

    await user.click(
      await screen.findByRole("button", { name: "Layout: Fill" }),
    );
    await user.click(
      screen.getByRole("menuitem", { name: "Picture in picture" }),
    );

    expect(
      screen.getByRole("button", { name: "Layout: Picture in picture" }),
    ).toBeVisible();
    await waitFor(() =>
      expect(segmentTitles()).toEqual([
        "Picture in picture",
        "Picture in picture",
        "Picture in picture",
      ]),
    );
  });
});

describe("facecam box", () => {
  it("moves and resizes the facecam box of a screenshare scene", async () => {
    const user = userEvent.setup();
    const fetchMock = renderLayouts();
    await choose(user, "Screenshare + facecam");
    expect(screen.queryByRole("button", { name: /^Tracker/ })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Crop" }));
    const box = await screen.findByRole("group", { name: "Facecam box" });
    expect(box.style.left).toBe("50%");
    expect(box.style.width).toBe("25%");
    expect(screen.getByText(/found around the speaker's face/)).toBeVisible();
    const reset = screen.getByRole("button", { name: "Use the found box" });
    expect(reset).toBeDisabled();

    // 60 px is 128 source px (0.1 of the width).
    fireEvent.pointerDown(box, { button: 0, clientX: 100, pointerId: 1 });
    fireEvent.pointerMove(box, { clientX: 160, pointerId: 1 });
    fireEvent.pointerUp(box, { pointerId: 1 });
    expect(box.style.left).toBe("60%");
    const corner = screen.getByRole("button", {
      name: "Resize from the bottom right corner",
    });
    // 30 px wider is 64 source px: 384 px, 0.3 of the width; same height.
    fireEvent.pointerDown(corner, { button: 0, clientX: 0, pointerId: 2 });
    fireEvent.pointerMove(corner, { clientX: 30, pointerId: 2 });
    fireEvent.pointerUp(corner, { pointerId: 2 });
    expect(box.style.width).toBe("30%");
    expect(box.style.height).toBe("40%");
    expect(screen.getByText(/Your facecam box/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const body = await savedBody(fetchMock);
    expect(body.framing.facecam).toEqual({
      x: 0.6,
      y: 0.1,
      width: 0.3,
      height: 0.4,
    });
    expect(body.scene_reframes[0].layout).toBe("screenshare");

    await user.click(reset);
    expect(box.style.left).toBe("50%");
    expect(reset).toBeDisabled();
  });
});
