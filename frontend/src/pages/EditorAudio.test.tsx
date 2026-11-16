import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Asset, Clip, MusicTrack, SfxSound, TrackItem } from "@/api/types";
import { NO_AUDIO_DATA } from "@/testing/assetFixtures";
import { CLIP, mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { callsTo, clip, engineStatus, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function asset(id: number, kind: Asset["kind"], attribution: string): Asset {
  return {
    id,
    kind,
    path: `/assets/${id}.flac`,
    license: "CC0-1.0",
    attribution,
    source_url: null,
    tags: ["bundled"],
    ...NO_AUDIO_DATA,
  };
}

const MUSIC: MusicTrack[] = [
  {
    asset: asset(11, "music", "Original ClipForge loop"),
    title: "Sunny Side",
    duration: 32,
    bundled: true,
    tags: ["upbeat", "bright"],
  },
  {
    asset: asset(12, "music", "Original ClipForge loop"),
    title: "Night Drive",
    duration: 45,
    bundled: true,
    tags: ["calm"],
  },
];

const SFX: SfxSound[] = [
  {
    asset: asset(21, "sfx", "Original ClipForge sound"),
    title: "Whoosh",
    duration: 0.8,
    tags: ["whoosh", "transition"],
  },
  {
    asset: asset(22, "sfx", "Original ClipForge sound"),
    title: "Pop",
    duration: 0.3,
    tags: ["pop"],
  },
];

function audioItem(
  id: string,
  assetId: number,
  props: Record<string, unknown>,
): TrackItem {
  return { id, kind: "audio", asset_id: assetId, start: 1, end: 3, props };
}

const ROUTES = {
  "GET /api/music": () => json(MUSIC),
  "GET /api/sfx": () => json(SFX),
  "GET /api/engines": () =>
    json([engineStatus("kokoro", true), engineStatus("piper", true)]),
};

async function openAudio(
  routes: Parameters<typeof renderEditor>[2] = {},
  data: Clip = CLIP,
) {
  const user = userEvent.setup();
  const fetchMock = renderEditor(data, undefined, { ...ROUTES, ...routes });
  await user.click(await screen.findByRole("button", { name: "Audio" }));
  const panel = screen.getByRole("complementary", { name: "Audio panel" });
  return { user, fetchMock, panel };
}

function bodyOf(
  fetchMock: ReturnType<typeof renderEditor>,
  method: string,
  url: string,
) {
  return JSON.parse(String(callsTo(fetchMock, method, url)[0][1]?.body));
}

describe("audio panel: music", () => {
  it("lists the library with attribution and license", async () => {
    const { panel } = await openAudio();
    const list = await within(panel).findByRole("list", {
      name: "Music tracks",
    });
    expect(within(list).getByText("Sunny Side")).toBeVisible();
    expect(within(list).getByText("upbeat")).toBeVisible();
    expect(
      within(list).getAllByText("Original ClipForge loop · CC0-1.0"),
    ).toHaveLength(2);
    expect(within(list).getByText("00:32")).toBeVisible();
  });

  it("uses a track over the whole clip, edits its volume, fades and ducking, and removes it", async () => {
    const { user, panel } = await openAudio();
    await user.click(
      await within(panel).findByRole("button", {
        name: "Use Sunny Side as music",
      }),
    );

    const track = screen.getByRole("group", { name: "Music track" });
    expect(
      within(track).getByRole("button", { name: /^Music: Audio #11/ }),
    ).toBeVisible();
    expect(
      within(panel).getByRole("button", { name: "Use Sunny Side as music" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    expect(within(panel).getByText("50%")).toBeVisible();

    const volume = within(panel).getByRole("slider", { name: "Music volume" });
    volume.focus();
    await user.keyboard("{ArrowRight}");
    expect(within(panel).getByText("55%")).toBeVisible();
    const fade = within(panel).getByRole("slider", { name: "Fade out" });
    fade.focus();
    await user.keyboard("{ArrowRight}");
    expect(within(panel).getByText("1.5 s")).toBeVisible();
    const duck = within(panel).getByRole("switch", {
      name: "Duck under speech",
    });
    expect(duck).toBeChecked();
    await user.click(duck);
    expect(duck).not.toBeChecked();

    await user.click(
      within(panel).getByRole("button", { name: "Use Night Drive as music" }),
    );
    expect(
      within(track).getByRole("button", { name: /^Music: Audio #12/ }),
    ).toBeVisible();
    expect(within(panel).getByText("55%")).toBeVisible();

    await user.click(
      within(panel).getByRole("button", { name: "Remove music" }),
    );
    expect(within(track).queryByRole("button")).not.toBeInTheDocument();
    expect(within(panel).queryByRole("slider", { name: "Music volume" })).toBe(
      null,
    );
  });

  it("plays and stops a track's preview", async () => {
    const { user, panel } = await openAudio();
    const play = await within(panel).findByRole("button", {
      name: "Play Sunny Side",
    });
    await user.click(play);
    expect(
      within(panel).getByRole("button", { name: "Pause Sunny Side" }),
    ).toHaveAttribute("aria-pressed", "true");
    await user.click(
      within(panel).getByRole("button", { name: "Play Night Drive" }),
    );
    expect(
      within(panel).getByRole("button", { name: "Play Sunny Side" }),
    ).toBeVisible();
    await user.click(
      within(panel).getByRole("button", { name: "Pause Night Drive" }),
    );
    expect(
      within(panel).getByRole("button", { name: "Play Night Drive" }),
    ).toBeVisible();
  });
});

describe("audio panel: sound effects", () => {
  it("has the AI place sounds on the saved clip and lists them", async () => {
    const answer = clip({
      ...CLIP,
      tracks: { ...CLIP.tracks, sfx: [audioItem("auto-sfx-1", 21, {})] },
    });
    const { user, fetchMock, panel } = await openAudio({
      "POST /api/clips/7/auto-sfx": () => json(answer),
    });
    const slider = await within(panel).findByRole("slider", {
      name: "Sounds to suggest",
    });
    slider.focus();
    await user.keyboard("{ArrowLeft}");
    await user.click(
      within(panel).getByRole("button", { name: "Suggest sound effects" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/7/auto-sfx")).toHaveLength(
        1,
      ),
    );
    expect(bodyOf(fetchMock, "POST", "/api/clips/7/auto-sfx")).toEqual({
      max_items: 4,
    });
    const placed = await within(panel).findByRole("list", {
      name: "Placed sound effects",
    });
    expect(within(placed).getByText("Whoosh")).toBeVisible();
    expect(within(placed).getByText("00:01.00")).toBeVisible();

    await user.click(
      within(placed).getByRole("button", { name: "Remove Whoosh at 00:01.00" }),
    );
    expect(
      within(panel).queryByRole("list", { name: "Placed sound effects" }),
    ).toBe(null);
  });

  it("adds a sound of the pack at the playhead", async () => {
    const { user, panel } = await openAudio();
    await user.click(
      await within(panel).findByRole("button", {
        name: "Add Pop at the playhead",
      }),
    );
    const placed = within(panel).getByRole("list", {
      name: "Placed sound effects",
    });
    expect(within(placed).getByText("Pop")).toBeVisible();
    const track = screen.getByRole("group", { name: "SFX track" });
    expect(
      within(track).getByRole("button", { name: /^SFX: Audio #22/ }),
    ).toBeVisible();
  });

  it("waits for unsaved changes before asking the AI", async () => {
    const { user, panel } = await openAudio();
    await user.click(
      await within(panel).findByRole("button", {
        name: "Add Pop at the playhead",
      }),
    );
    expect(
      within(panel).getByRole("button", { name: "Suggest sound effects" }),
    ).toBeDisabled();
    expect(
      within(panel).getByText("Suggestions wait until your changes are saved."),
    ).toBeVisible();
  });
});
