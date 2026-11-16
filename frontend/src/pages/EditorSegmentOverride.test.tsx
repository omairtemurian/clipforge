import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip } from "@/api/types";
import { CLIP, mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { toast } from "@/lib/toast";
import { callsTo, DEFAULTS, json, project } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** The editor of CLIP (10-40 s, 20-25 cut) whose source cuts at 30 s. */
function renderOverrides() {
  const planned = project({ id: 1, duration: 60, settings: DEFAULTS });
  return renderEditor(undefined, undefined, {
    "GET /api/projects/1": () => json(planned),
    "GET /api/clips/7/scenes": () => json({ cuts: [30], scenes: [] }),
    "PATCH /api/clips/7": (_url, init) =>
      json({ ...CLIP, ...JSON.parse(String(init?.body)) } satisfies Clip),
    "PUT /api/projects/1/zoom-out": (_url, init) =>
      json({
        project: planned,
        clip_ids: [7, 8],
        intensity: JSON.parse(String(init?.body)).intensity,
      }),
  });
}

function segmentLabels() {
  return within(screen.getByLabelText("Segments"))
    .getAllByRole("button")
    .map((block) => block.textContent);
}

describe("segment strip override", () => {
  it("frames the selected segment's scene in one click and saves it", async () => {
    const user = userEvent.setup();
    const fetchMock = renderOverrides();
    await waitFor(() =>
      expect(segmentLabels()).toEqual(["Fill", "Fill", "Fill"]),
    );
    expect(
      screen.queryByRole("radiogroup", { name: "Segment layout" }),
    ).toBeNull();

    await user.click(
      screen.getByRole("button", { name: "Segment 00:30.00 - 00:40.00" }),
    );
    const group = screen.getByRole("radiogroup", { name: "Segment layout" });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((radio) => radio.textContent),
    ).toEqual(["Fill", "Square", "Fit", "Split", "Track"]);
    expect(within(group).getByRole("radio", { name: "Fill" })).toBeChecked();

    await user.click(within(group).getByRole("radio", { name: "Square" }));
    expect(segmentLabels()).toEqual(["Fill", "Fill", "Square"]);
    expect(within(group).getByRole("radio", { name: "Square" })).toBeChecked();

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
    );
    const body = JSON.parse(
      String(callsTo(fetchMock, "PATCH", "/api/clips/7")[0][1]?.body),
    );
    expect(
      body.scene_reframes.map((scene: { layout: string }) => scene.layout),
    ).toEqual(["fill", "square_blur"]);
  });
});

describe("zoom-out moments in the reframe panel", () => {
  async function openLayoutPanel(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: "Layout" }));
    return screen.getByRole("complementary", { name: "Layout panel" });
  }

  it("saves the intensity for the project", async () => {
    const user = userEvent.setup();
    const success = vi.spyOn(toast, "success");
    const fetchMock = renderOverrides();
    const panel = await openLayoutPanel(user);

    expect(
      within(panel).getByRole("switch", { name: "Zoom-out moments" }),
    ).toBeChecked();
    await user.click(within(panel).getByRole("radio", { name: "Subtle" }));

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "PUT", "/api/projects/1/zoom-out"),
      ).toHaveLength(1),
    );
    expect(
      JSON.parse(
        String(
          callsTo(fetchMock, "PUT", "/api/projects/1/zoom-out")[0][1]?.body,
        ),
      ),
    ).toEqual({ intensity: "subtle" });
    await waitFor(() =>
      expect(success).toHaveBeenCalledWith(
        expect.stringMatching(/again for 2 clips/),
      ),
    );
  });

  it("switches off with the toggle", async () => {
    const user = userEvent.setup();
    const fetchMock = renderOverrides();
    const panel = await openLayoutPanel(user);

    await user.click(
      within(panel).getByRole("switch", { name: "Zoom-out moments" }),
    );

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "PUT", "/api/projects/1/zoom-out"),
      ).toHaveLength(1),
    );
    expect(
      JSON.parse(
        String(
          callsTo(fetchMock, "PUT", "/api/projects/1/zoom-out")[0][1]?.body,
        ),
      ),
    ).toEqual({ intensity: "off" });
  });

  it("waits for unsaved edits to be saved", async () => {
    const user = userEvent.setup();
    renderOverrides();
    const panel = await openLayoutPanel(user);
    await user.click(
      within(panel).getByRole("button", { name: "Nudge crop right" }),
    );

    expect(
      within(panel).getByRole("switch", { name: "Zoom-out moments" }),
    ).toBeDisabled();
    expect(within(panel).getByText(/Save this clip first/)).toBeVisible();
  });
});
