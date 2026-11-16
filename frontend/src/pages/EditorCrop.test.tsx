import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CropTrack } from "@/api/types";
import { mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// A 1280x720 source whose 9:16 window (404x720) starts at x 100 at the
// clip's start (10 s); the frame is drawn 600 px wide (2.133 source px/px).
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

function renderCrop() {
  return renderEditor(undefined, undefined, {
    "GET /api/clips/7/crop": () => json(TRACK),
    "GET /api/clips/7/crop?aspect=1%3A1": () =>
      json({ ...TRACK, aspect: "1:1", width: 720 }),
  });
}

async function openCrop(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Crop" }));
  return screen.findByRole("group", { name: "Crop window" });
}

describe("player toolbar", () => {
  it("chooses the aspect, layout and fit background", async () => {
    const user = userEvent.setup();
    renderCrop();

    await user.click(
      await screen.findByRole("button", {
        name: "Aspect ratio: 9:16 Vertical",
      }),
    );
    await user.click(screen.getByRole("menuitem", { name: /1:1 Square/ }));
    expect(
      screen.getByRole("button", { name: "Aspect ratio: 1:1 Square" }),
    ).toBeVisible();

    expect(
      screen.queryByRole("button", { name: /^Background/ }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Layout: Fill" }));
    await user.click(screen.getByRole("menuitem", { name: "Fit" }));
    expect(screen.getByRole("button", { name: "Layout: Fit" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Crop" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Background: Blur" }));
    await user.click(screen.getByRole("menuitem", { name: "Black" }));
    expect(
      screen.getByRole("button", { name: "Background: Black" }),
    ).toBeVisible();
  });

  it("turns the tracker off and on", async () => {
    const user = userEvent.setup();
    renderCrop();

    const tracker = await screen.findByRole("button", { name: "Tracker on" });
    expect(tracker).toHaveAttribute("aria-pressed", "true");
    await user.click(tracker);
    expect(screen.getByRole("button", { name: "Tracker off" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});

describe("crop tool", () => {
  it("shows the planned window over the source at the playhead", async () => {
    const user = userEvent.setup();
    renderCrop();
    const box = await openCrop(user);

    expect(screen.getByLabelText("Source video")).toHaveAttribute(
      "src",
      expect.stringContaining("/media/1/source"),
    );
    expect(box.style.left).toBe("7.8125%");
    expect(box.style.width).toBe("31.5625%");
    expect(screen.getByText(/set a keyframe at 00:10.00/)).toBeVisible();
  });

  it("moves the window by dragging, setting a keyframe that undoes at once", async () => {
    const user = userEvent.setup();
    renderCrop();
    const box = await openCrop(user);

    fireEvent.pointerDown(box, { button: 0, clientX: 100, pointerId: 1 });
    fireEvent.pointerMove(box, { clientX: 130, pointerId: 1 });
    fireEvent.pointerMove(box, { clientX: 160, pointerId: 1 });
    fireEvent.pointerUp(box, { pointerId: 1 });

    // 60 px is 128 source px: the window starts at x 228.
    expect(box.style.left).toBe("17.8125%");
    expect(screen.getByText("Keyframe at 00:10.00")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(box.style.left).toBe("7.8125%");
  });

  it("resizes the window from a corner and resets it", async () => {
    const user = userEvent.setup();
    renderCrop();
    const box = await openCrop(user);

    const corner = screen.getByRole("button", {
      name: "Resize from the bottom right corner",
    });
    fireEvent.pointerDown(corner, { button: 0, clientX: 0, pointerId: 1 });
    fireEvent.pointerMove(corner, { clientX: -60, pointerId: 1 });
    fireEvent.pointerUp(corner, { pointerId: 1 });

    expect(box.style.width).toBe("21.5625%");
    expect(box.style.left).toBe("7.8125%");

    await user.click(screen.getByRole("button", { name: "Reset crop" }));
    expect(box.style.width).toBe("31.5625%");
  });

  it("moves the window with the arrow keys and deletes the keyframe", async () => {
    const user = userEvent.setup();
    renderCrop();
    const box = await openCrop(user);

    box.focus();
    await user.keyboard("{ArrowRight}");
    // 1% of 1280 px: 12.8 px right, placed on even pixels at 112.
    expect(box.style.left).toBe("8.75%");

    await user.click(screen.getByRole("button", { name: "Delete keyframe" }));
    expect(box.style.left).toBe("7.8125%");
  });

  it("closes when the layout leaves fill", async () => {
    const user = userEvent.setup();
    renderCrop();
    await openCrop(user);

    await user.click(screen.getByRole("button", { name: "Layout: Fill" }));
    await user.click(screen.getByRole("menuitem", { name: "Split" }));

    expect(
      screen.queryByRole("group", { name: "Crop window" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Preview of/)).toBeVisible();
  });
});
