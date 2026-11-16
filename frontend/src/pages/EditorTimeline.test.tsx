import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Waveform } from "@/api/types";
import { TimelineTracks } from "@/components/editor/TimelineTracks";
import { useClipEdits } from "@/hooks/useClipEdits";
import {
  CLIP,
  WORDS,
  mockLayoutAndMedia,
  renderEditor,
  stat,
  video,
} from "@/testing/editor";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Move the preview to t seconds (source: the clip's start + t, before the
 * cut at 20 s). */
function playAt(t: number) {
  video().currentTime = t;
  fireEvent.timeUpdate(video());
}

function segmentNames(): string[] {
  return screen
    .getAllByRole("button", { name: /^Segment / })
    .map((button) => button.getAttribute("aria-label") ?? "");
}

describe("editor timeline", () => {
  it("splits at the playhead with S and deletes the selected segment", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByRole("heading", { name: "Pizza night" });
    expect(segmentNames()).toEqual([
      "Segment 00:10.00 - 00:20.00",
      "Segment 00:25.00 - 00:40.00",
    ]);

    playAt(17); // source 32 s
    await user.keyboard("s");
    expect(screen.getAllByTestId("split")).toHaveLength(1);
    expect(segmentNames()).toEqual([
      "Segment 00:10.00 - 00:20.00",
      "Segment 00:25.00 - 00:32.00",
      "Segment 00:32.00 - 00:40.00",
    ]);

    await user.click(
      screen.getByRole("button", { name: "Segment 00:25.00 - 00:32.00" }),
    );
    await user.keyboard("{Delete}");
    expect(segmentNames()).toEqual([
      "Segment 00:10.00 - 00:20.00",
      "Segment 00:32.00 - 00:40.00",
    ]);
    expect(screen.getByTitle("Cut 00:20.00 - 00:32.00")).toBeInTheDocument();
    expect(stat("Length")).toBe("00:18.00");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(segmentNames()).toHaveLength(3);
  });

  it("snaps a split to the nearest word edge unless snapping is off", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByRole("heading", { name: "Pizza night" });
    const split = screen.getByRole("button", { name: "Split at playhead (S)" });

    playAt(0.5); // source 10.5 s, inside "Hello" (10.2-10.6)
    await user.click(split);
    expect(segmentNames()[0]).toBe("Segment 00:10.00 - 00:10.60");

    await user.click(
      screen.getByRole("button", {
        name: "Snap to words, segments, playhead and layers",
      }),
    );
    expect(
      screen.getByRole("button", {
        name: "Snap to words, segments, playhead and layers",
      }),
    ).toHaveAttribute("aria-pressed", "false");
    playAt(0.3);
    await user.click(split);
    expect(segmentNames()[0]).toBe("Segment 00:10.00 - 00:10.30");
  });

  it("deletes selected words from the control row", async () => {
    const user = userEvent.setup();
    renderEditor();
    const remove = await screen.findByRole("button", {
      name: "Delete selection (Delete)",
    });
    expect(remove).toBeDisabled();

    await user.click(await screen.findByText("pizza"));
    expect(remove).toBeEnabled();
    await user.click(remove);
    expect(stat("Cuts")).toBe("2");
  });

  it("zooms with +/- and the buttons, and hides the timeline", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByRole("heading", { name: "Pizza night" });
    const content = () => screen.getByLabelText("Time ruler").parentElement;
    expect(content()).toHaveStyle({ width: "100%" });
    expect(screen.getByRole("button", { name: "Zoom out (-)" })).toBeDisabled();

    await user.keyboard("+");
    expect(content()).toHaveStyle({ width: "150%" });
    await user.click(screen.getByRole("button", { name: "Zoom in (+)" }));
    expect(content()).toHaveStyle({ width: "225%" });
    await user.keyboard("-");
    expect(content()).toHaveStyle({ width: "150%" });

    await user.click(screen.getByRole("button", { name: "Hide timeline" }));
    expect(screen.queryByLabelText("Timeline")).toBe(null);
    await user.click(screen.getByRole("button", { name: "Show timeline" }));
    expect(screen.getByLabelText("Timeline")).toBeVisible();
  });

  it("steps the playhead a frame or 1 s with the arrows, and skips", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByRole("heading", { name: "Pizza night" });
    playAt(5);

    await user.keyboard("{ArrowRight}");
    expect(video().currentTime).toBeCloseTo(5 + 1 / 30);
    await user.keyboard("{Shift>}{ArrowLeft}{/Shift}");
    expect(video().currentTime).toBeCloseTo(4 + 1 / 30);

    playAt(5); // source 15 s: the next edge is the cut (20-25 s), at 10 s
    const forward = screen.getByRole("button", { name: "Skip forward" });
    await user.click(forward);
    expect(video().currentTime).toBe(10);
    await user.click(forward);
    expect(video().currentTime).toBe(25);
    await user.click(screen.getByRole("button", { name: "Skip back" }));
    expect(video().currentTime).toBe(10);
    await user.click(screen.getByRole("button", { name: "Skip back" }));
    expect(video().currentTime).toBe(0);
  });

  it("draws the waveform and filmstrip of the clip's surroundings", async () => {
    const wave: Waveform = {
      start: 0,
      end: 60,
      peaks_per_second: 1,
      peaks: Array.from({ length: 60 }, (_, i) => (i % 10) / 10),
    };
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(() => Promise.resolve({ width: 60 * 160, height: 90, close() {} })),
    );
    URL.createObjectURL = vi.fn(() => "blob:filmstrip");
    URL.revokeObjectURL = vi.fn();
    const headers = {
      "X-Filmstrip-Start": "0.000",
      "X-Filmstrip-Interval": "1.000000",
      "X-Filmstrip-Count": "60",
    };
    renderEditor(CLIP, WORDS, {
      "GET /api/clips/7/waveform": () => new Response(JSON.stringify(wave)),
      "GET /api/clips/7/filmstrip": () =>
        new Response(new Blob(["jpeg"]), { headers }),
    });

    const waveform = await screen.findByTestId("waveform");
    expect(waveform.getAttribute("viewBox")).toBe("0 0 200 100");
    const strip = await screen.findByTestId("filmstrip");
    // 600 px row, 48 px tall 16:9 tiles: 85.3 px each, 8 slots.
    expect(strip.children).toHaveLength(8);
    expect(strip.style.getPropertyValue("--strip")).toBe("url(blob:filmstrip)");
    expect((strip.children[0] as HTMLElement).style.backgroundImage).toBe(
      "var(--strip)",
    );
  });
});

/** The timeline over clip 10-40 s with its edits, showing their PATCH body. */
function TracksWithPatch() {
  const edits = useClipEdits(CLIP);
  return (
    <>
      <TimelineTracks
        view={{ start: 0, end: 60 }}
        clip={edits.range}
        cuts={edits.cuts}
        splits={edits.splits}
        parts={[]}
        selected={null}
        labelAt={() => "Auto"}
        playhead={10}
        zoom={1}
        snapWords={WORDS}
        snap
        layers={edits.layers}
        onLayerChange={edits.setLayer}
        selectedItem={null}
        onSelectItem={() => {}}
        onChange={edits.setRange}
        onSeek={() => {}}
        onSelect={() => {}}
      />
      <output data-testid="patch">{JSON.stringify(edits.patch)}</output>
    </>
  );
}

describe("timeline handles", () => {
  it("dragging the end handle changes the end of the PATCH body", () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <TracksWithPatch />
      </QueryClientProvider>,
    );
    const end = screen.getByRole("slider", { name: "Clip end" });
    const texts = { title: "Pizza night", hook_text: "He ate it all" };
    const patch = () => {
      const { title, hook_text, start, end, cut_ranges } = JSON.parse(
        screen.getByTestId("patch").textContent!,
      );
      expect({ title, hook_text }).toEqual(texts);
      return { start, end, cut_ranges };
    };
    expect(patch()).toEqual({ start: 10, end: 40, cut_ranges: [[20, 25]] });

    fireEvent.pointerDown(end, { button: 0, clientX: 330, pointerId: 1 });
    fireEvent.pointerMove(end, { clientX: 240, pointerId: 1 });
    fireEvent.pointerUp(end, { pointerId: 1 });
    expect(patch()).toEqual({ start: 10, end: 24, cut_ranges: [[20, 24]] });

    // 39.6 s snaps to the end of "end" (39-39.5 s), 0.1 s (1 px) away.
    fireEvent.pointerDown(end, { button: 0, clientX: 396, pointerId: 2 });
    fireEvent.pointerUp(end, { pointerId: 2 });
    expect(patch()).toEqual({ start: 10, end: 39.5, cut_ranges: [[20, 25]] });
  });
});
