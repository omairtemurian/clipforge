import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CleanupPreview } from "@/api/types";
import {
  CLIP,
  mockLayoutAndMedia,
  renderEditor,
  WORDS,
} from "@/testing/editor";
import { callsTo, clip, engineStatus, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const PREVIEW: CleanupPreview = {
  filler_language: "en",
  items: [
    { start: 6.2, end: 7.55, kind: "filler", text: "um" },
    { start: 13.65, end: 16.75, kind: "pause", text: "" },
    { start: 16.9, end: 18.84, kind: "bad_take", text: "Then I bought one" },
  ],
};

async function openCleanup(
  routes: Parameters<typeof renderEditor>[2] = {},
  installed = true,
) {
  const user = userEvent.setup();
  const fetchMock = renderEditor(CLIP, WORDS, {
    "GET /api/filler-languages": () => json(["de", "en", "fa"]),
    "GET /api/engines": () => json([engineStatus("deepfilternet", installed)]),
    ...routes,
  });
  await screen.findByRole("heading", { name: "Pizza night" });
  await user.click(screen.getByRole("button", { name: "Cleanup" }));
  return { user, fetchMock };
}

function bodyOf(
  fetchMock: ReturnType<typeof renderEditor>,
  url: string,
  n = 0,
) {
  return JSON.parse(String(callsTo(fetchMock, "POST", url)[n][1]?.body));
}

describe("cleanup panel: speech cleanup", () => {
  it("lists what will be removed with checkboxes and cuts the checked ones", async () => {
    const answer = clip({ ...CLIP, cut_ranges: [[13.65, 16.75]] });
    const { user, fetchMock } = await openCleanup({
      "POST /api/clips/7/cleanup/preview": () => json(PREVIEW),
      "POST /api/clips/7/cleanup/apply": () => json(answer),
    });
    await user.click(
      await screen.findByRole("button", { name: "Find what to remove" }),
    );

    const list = await screen.findByRole("list", {
      name: "What will be removed",
    });
    const boxes = within(list).getAllByRole("checkbox");
    expect(boxes).toHaveLength(3);
    boxes.forEach((box) => expect(box).toBeChecked());
    expect(within(list).getByText("“um”")).toBeVisible();
    expect(within(list).getByText("Pause")).toBeVisible();
    expect(within(list).getByText("Then I bought one")).toBeVisible();
    expect(bodyOf(fetchMock, "/api/clips/7/cleanup/preview")).toEqual({
      fillers: true,
      pauses: true,
      pause_threshold_s: 0.6,
      bad_takes: false,
      language: null,
    });

    await user.click(boxes[0]);
    await user.click(boxes[2]);
    await user.click(screen.getByRole("button", { name: "Remove 1 cut" }));

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/clips/7/cleanup/apply"),
      ).toHaveLength(1),
    );
    expect(bodyOf(fetchMock, "/api/clips/7/cleanup/apply")).toEqual({
      items: PREVIEW.items,
      unchecked: [0, 2],
    });
    await waitFor(() =>
      expect(
        screen.queryByRole("list", { name: "What will be removed" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("sends the options the user chose", async () => {
    const { user, fetchMock } = await openCleanup({
      "POST /api/clips/7/cleanup/preview": () =>
        json({ filler_language: "de", items: [] }),
    });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Filler language" }),
      "de",
    );
    await user.click(screen.getByRole("switch", { name: "Bad takes" }));
    const slider = screen.getByRole("slider", { name: "Pause threshold" });
    slider.focus();
    await user.keyboard("{ArrowRight}");
    await user.click(
      screen.getByRole("button", { name: "Find what to remove" }),
    );

    expect(
      await screen.findByText("Nothing to remove in this clip."),
    ).toBeVisible();
    expect(bodyOf(fetchMock, "/api/clips/7/cleanup/preview")).toEqual({
      fillers: true,
      pauses: true,
      pause_threshold_s: 0.7,
      bad_takes: true,
      language: "de",
    });
  });

  it("disables the search when nothing is switched on", async () => {
    const { user } = await openCleanup();
    await user.click(
      await screen.findByRole("switch", { name: "Filler words" }),
    );
    await user.click(screen.getByRole("switch", { name: "Long pauses" }));

    expect(
      screen.getByRole("button", { name: "Find what to remove" }),
    ).toBeDisabled();
  });

  it("drops the list when an option changes", async () => {
    const { user } = await openCleanup({
      "POST /api/clips/7/cleanup/preview": () => json(PREVIEW),
    });
    await user.click(
      await screen.findByRole("button", { name: "Find what to remove" }),
    );
    await screen.findByRole("list", { name: "What will be removed" });

    await user.click(screen.getByRole("switch", { name: "Long pauses" }));

    expect(
      screen.queryByRole("list", { name: "What will be removed" }),
    ).not.toBeInTheDocument();
  });
});

describe("cleanup panel: speech enhancement", () => {
  it("sets the strength when the slider is released", async () => {
    const { user, fetchMock } = await openCleanup({
      "PUT /api/clips/7/enhance": () => json(clip({ ...CLIP, enhance: 0.05 })),
    });
    const slider = await screen.findByRole("slider", {
      name: "Enhancement strength",
    });
    expect(screen.getByText("Off")).toBeVisible();
    slider.focus();
    await user.keyboard("{ArrowRight}");

    await waitFor(() =>
      expect(callsTo(fetchMock, "PUT", "/api/clips/7/enhance")).toHaveLength(1),
    );
    expect(callsTo(fetchMock, "PUT", "/api/clips/7/enhance")[0][1]?.body).toBe(
      JSON.stringify({ strength: 0.05 }),
    );
    expect(await screen.findByText("5%")).toBeVisible();
  });

  it("shows the strength the clip has", async () => {
    const user = userEvent.setup();
    renderEditor(clip({ ...CLIP, enhance: 0.6 }), WORDS, {
      "GET /api/filler-languages": () => json(["en"]),
      "GET /api/engines": () => json([engineStatus("deepfilternet", true)]),
    });
    await screen.findByRole("heading", { name: "Pizza night" });
    await user.click(screen.getByRole("button", { name: "Cleanup" }));

    expect(await screen.findByText("60%")).toBeVisible();
  });

  it("says that DeepFilterNet is installed", async () => {
    await openCleanup();
    expect(await screen.findByText(/DeepFilterNet is installed/)).toBeVisible();
  });

  it("links to the setup when it is not", async () => {
    await openCleanup({}, false);

    expect(await screen.findByText(/Not installed/)).toBeVisible();
    expect(screen.getByRole("link", { name: "see setup" })).toHaveAttribute(
      "href",
      "https://github.com/omairtemurian/clipforge#engine-deepfilternet",
    );
    expect(
      screen.getByRole("slider", { name: "Enhancement strength" }),
    ).toBeEnabled();
  });
});
