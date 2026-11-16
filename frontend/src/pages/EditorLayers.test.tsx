import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, TrackItem } from "@/api/types";
import { CLIP, mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { callsTo, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function textItem(id: string, start: number, end: number): TrackItem {
  return { id, kind: "text", asset_id: null, start, end, props: { text: id } };
}

// Clip 10-40 s with the cut 20-25 s: 25 s long; the timeline shows 0-60 s
// at 10 px per second, so clip time 2 s (source 12 s) is at 120 px.
const LAYERED: Clip = {
  ...CLIP,
  tracks: {
    ...CLIP.tracks,
    text: [textItem("Hi", 2, 4)],
    broll: [
      {
        id: "b1",
        kind: "image",
        asset_id: 3,
        start: 12,
        end: 14,
        props: { offset: 0 },
      },
    ],
  },
};

/** Press item at fromX and drag it to toX (px). */
function drag(element: Element, fromX: number, toX: number) {
  fireEvent.pointerDown(element, { button: 0, clientX: fromX, pointerId: 1 });
  fireEvent.pointerMove(element, { clientX: toX, pointerId: 1 });
  fireEvent.pointerUp(element, { pointerId: 1 });
}

const textBlock = () =>
  within(screen.getByRole("group", { name: "Text track" })).getByRole("button");

describe("timeline layer tracks", () => {
  it("shows the video row and the six layer tracks with their items", async () => {
    renderEditor(LAYERED);
    await screen.findByRole("heading", { name: "Pizza night" });
    for (const name of [
      "B-roll",
      "Overlays",
      "Text",
      "Music",
      "SFX",
      "Voiceover",
    ]) {
      expect(
        screen.getByRole("group", { name: `${name} track` }),
      ).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Timeline")).toBeInTheDocument();
    expect(screen.getByText("Video")).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "B-roll: Image #3, 00:12.00 - 00:14.00",
      }),
    ).toBeInTheDocument();
    // Clip time 2-4 s is source 12-14 s: 20% to 23.3% of 0-60 s.
    expect(textBlock().style.left).toBe("20%");
  });

  it("drags an item, snapping its end to the segment edge, and undoes it", async () => {
    const user = userEvent.setup();
    renderEditor(LAYERED);
    await screen.findByRole("heading", { name: "Pizza night" });

    // Grabbed 1 s in; dropped at source 19.5 s = clip 9.5 s: 8.5-10.5 s,
    // whose end snaps to the cut at clip 10 s.
    drag(textBlock(), 130, 195);
    expect(textBlock()).toHaveAccessibleName("Text: Hi, 00:08.00 - 00:10.00");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(textBlock()).toHaveAccessibleName("Text: Hi, 00:02.00 - 00:04.00");
  });

  it("does not snap with snapping off and trims an item by its end", async () => {
    const user = userEvent.setup();
    renderEditor(LAYERED);
    await screen.findByRole("heading", { name: "Pizza night" });
    await user.click(
      screen.getByRole("button", {
        name: "Snap to words, segments, playhead and layers",
      }),
    );

    drag(textBlock(), 130, 195);
    expect(textBlock()).toHaveAccessibleName("Text: Hi, 00:08.50 - 00:10.50");

    drag(within(textBlock()).getByTestId("item-end"), 255, 280);
    expect(textBlock()).toHaveAccessibleName("Text: Hi, 00:08.50 - 00:13.00");
  });

  it("saves the moved items with PATCH /clips/{id}/tracks", async () => {
    const user = userEvent.setup();
    const fetchMock = renderEditor(LAYERED, undefined, {
      "PATCH /api/clips/7": () => json(LAYERED),
      "PATCH /api/clips/7/tracks": (_url, init) =>
        json({
          ...LAYERED,
          tracks: { ...LAYERED.tracks, ...JSON.parse(String(init?.body)) },
        }),
    });
    await screen.findByRole("heading", { name: "Pizza night" });

    drag(textBlock(), 130, 195);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7/tracks")).toHaveLength(
        1,
      ),
    );
    const body = JSON.parse(
      String(callsTo(fetchMock, "PATCH", "/api/clips/7/tracks")[0][1]?.body),
    );
    expect(body.text).toEqual([textItem("Hi", 8, 10)]);
    expect(body.broll).toEqual(LAYERED.tracks.broll);
    expect(body).not.toHaveProperty("video");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Save changes" }),
      ).toBeDisabled(),
    );
  });
});
