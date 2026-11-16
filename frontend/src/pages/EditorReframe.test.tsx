import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CropTrack } from "@/api/types";
import { toast } from "@/lib/toast";
import { mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import {
  callsTo,
  DEFAULTS,
  json,
  project,
  REFRAME_PRESETS,
} from "@/testing/mockApi";

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

const PROJECT = project({
  id: 1,
  duration: 60,
  settings: { ...DEFAULTS, reframe_preset: "podcast-2" },
});

async function openLayout(user: ReturnType<typeof userEvent.setup>) {
  const fetchMock = renderEditor(undefined, undefined, {
    "GET /api/projects/1": () => json(PROJECT),
    "GET /api/reframe-presets": () => json(REFRAME_PRESETS),
    "GET /api/clips/7/crop": () => json(TRACK),
    "GET /api/clips/7/scenes": () => json({ cuts: [], scenes: [] }),
    "PUT /api/projects/1/camera-motion": () =>
      json({ project: PROJECT, clip_ids: [7, 8] }),
  });
  await user.click(await screen.findByRole("button", { name: "Layout" }));
  return {
    fetchMock,
    panel: screen.getByRole("complementary", { name: "Layout panel" }),
  };
}

describe("reframe controls", () => {
  it("sets a custom ratio on the clip and lists it in the toolbar", async () => {
    const user = userEvent.setup();
    const { panel } = await openLayout(user);

    await user.type(within(panel).getByLabelText("Custom ratio"), "3:4");
    await user.click(within(panel).getByRole("button", { name: "Set" }));

    const toolbar = screen.getByRole("toolbar", { name: "Player" });
    await user.click(
      within(toolbar).getByRole("button", { name: "Aspect ratio: 3:4 Custom" }),
    );
    expect(screen.getByRole("menuitem", { name: /3:4 Custom/ })).toBeVisible();
    expect(within(panel).getByText(/The clip is 3:4 now/)).toBeVisible();
  });

  it("rejects a ratio the backend would", async () => {
    const user = userEvent.setup();
    const { panel } = await openLayout(user);

    await user.type(within(panel).getByLabelText("Custom ratio"), "9:1");
    await user.click(within(panel).getByRole("button", { name: "Set" }));

    expect(within(panel).getByRole("alert")).toHaveTextContent("no wider");
    expect(
      screen.getByRole("button", { name: /^Aspect ratio: 9:16/ }),
    ).toBeVisible();
  });

  it("shows the project's reframe style", async () => {
    const user = userEvent.setup();
    const { panel } = await openLayout(user);

    expect(
      await within(panel).findByText(
        /Reframe style: Podcast \(two speakers\)\. Splits the frame/,
      ),
    ).toBeVisible();
  });

  it("saves the project's camera motion and re-tracks its clips", async () => {
    const user = userEvent.setup();
    const success = vi.spyOn(toast, "success");
    const { fetchMock, panel } = await openLayout(user);
    const motion = within(panel).getByRole("radiogroup", {
      name: "Camera motion",
    });

    expect(within(motion).getByRole("radio", { name: "Calm" })).toBeChecked();
    await user.click(within(motion).getByRole("radio", { name: "Fast" }));

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "PUT", "/api/projects/1/camera-motion"),
      ).toHaveLength(1),
    );
    const [, init] = callsTo(
      fetchMock,
      "PUT",
      "/api/projects/1/camera-motion",
    )[0];
    expect(JSON.parse(String(init?.body))).toEqual({ camera_motion: "fast" });
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(
        "Camera motion saved. 2 clips re-tracked. Render them to apply.",
      ),
    );
  });
});
