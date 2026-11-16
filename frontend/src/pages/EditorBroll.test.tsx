import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  BrollSpot,
  Clip,
  MediaItem,
  StockClip,
  StockProviderStatus,
  TrackItem,
} from "@/api/types";
import { NO_AUDIO_DATA } from "@/testing/assetFixtures";
import { CLIP, mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { callsTo, clip, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function stock(id: string, creator: string): StockClip {
  return {
    provider: "pexels",
    provider_id: id,
    page_url: `https://www.pexels.com/video/${id}/`,
    preview_url: `https://images.pexels.com/videos/${id}/thumb.jpeg`,
    download_url: `https://videos.pexels.com/${id}.mp4`,
    width: 1080,
    height: 1920,
    duration_s: 12,
    creator,
    creator_url: null,
    tags: [],
    license: "Pexels License",
    attribution: `Video by ${creator} on Pexels`,
  };
}

const SPOTS: BrollSpot[] = [
  {
    sentence: 1,
    text: "He ate the whole pizza",
    start: 2,
    end: 4.5,
    keywords: ["pizza", "eating"],
    query: "pizza eating",
    results: [stock("101", "Ana"), stock("102", "Ben")],
    error: null,
  },
  {
    sentence: 3,
    text: "Then he slept",
    start: 8,
    end: 10,
    keywords: ["sleep"],
    query: "sleep",
    results: [],
    error: "stock search failed",
  },
];

const PROVIDERS: StockProviderStatus[] = [
  { provider: "pexels", label: "Pexels", enabled: true, message: "" },
  {
    provider: "pixabay",
    label: "Pixabay",
    enabled: false,
    message: "Set PIXABAY_API_KEY in .env",
  },
];

function brollItem(id: string, start: number, end: number): TrackItem {
  return {
    id,
    kind: "video",
    asset_id: 31,
    start,
    end,
    props: { offset: 0, mode: "cutaway", x: 0.5, y: 0.3, width: 0.8 },
  };
}

function withBroll(...items: TrackItem[]): Clip {
  return clip({
    ...CLIP,
    tracks: { ...CLIP.tracks, broll: items },
  });
}

const LIBRARY: MediaItem[] = [
  {
    asset: {
      id: 31,
      kind: "video",
      path: "/stock/101.mp4",
      license: "Pexels License",
      attribution: "Video by Ana on Pexels",
      source_url: null,
      tags: [],
      ...NO_AUDIO_DATA,
    },
    tags: [],
    name: "101.mp4",
    mime: "video/mp4",
    size_bytes: 1000,
    duration: 12,
    width: 1080,
    height: 1920,
    has_thumbnail: false,
    used_in_clips: [7],
  },
];

const ROUTES = {
  "GET /api/broll/providers": () => json(PROVIDERS),
  "GET /api/library": () => json(LIBRARY),
  "POST /api/clips/7/broll/spots": () => json(SPOTS),
};

async function openBroll(
  routes: Parameters<typeof renderEditor>[2] = {},
  data: Clip = CLIP,
) {
  const user = userEvent.setup();
  const fetchMock = renderEditor(data, undefined, { ...ROUTES, ...routes });
  await user.click(await screen.findByRole("button", { name: "B-roll" }));
  const panel = screen.getByRole("complementary", { name: "B-roll panel" });
  return { user, fetchMock, panel };
}

function bodyOf(
  fetchMock: ReturnType<typeof renderEditor>,
  method: string,
  url: string,
) {
  return JSON.parse(String(callsTo(fetchMock, method, url)[0][1]?.body));
}

async function findSpots(
  user: ReturnType<typeof userEvent.setup>,
  panel: HTMLElement,
) {
  await user.click(
    await within(panel).findByRole("button", { name: "Find B-roll spots" }),
  );
  return within(panel).findByRole("list", { name: "B-roll spots" });
}

describe("B-roll panel", () => {
  it("finds spots and shows thumbnails with attribution and license", async () => {
    const { user, fetchMock, panel } = await openBroll();
    await user.selectOptions(
      within(panel).getByRole("combobox", { name: "Show as" }),
      "pip",
    );
    const list = await findSpots(user, panel);

    expect(bodyOf(fetchMock, "POST", "/api/clips/7/broll/spots")).toEqual({
      max_spots: 4,
      mode: "pip",
      provider: null,
    });
    expect(within(list).getByText("“He ate the whole pizza”")).toBeVisible();
    expect(within(list).getByText("00:02.00 – 00:04.50")).toBeVisible();
    expect(within(list).getByText("Searched: pizza eating")).toBeVisible();
    const results = within(list).getByRole("list", {
      name: "Stock videos for 00:02.00 – 00:04.50",
    });
    expect(
      within(results).getByRole("link", { name: "Video by Ana on Pexels" }),
    ).toHaveAttribute("href", "https://www.pexels.com/video/101/");
    expect(within(results).getAllByText(/· Pexels License/)).toHaveLength(2);
    expect(results.querySelector('img[src$="/101/thumb.jpeg"]')).not.toBeNull();
    expect(within(list).getByRole("alert")).toHaveTextContent(
      "stock search failed",
    );
  });

  it("accepts a result: puts it on the spot and lists it", async () => {
    const placed = withBroll(brollItem("broll-1", 2, 4.5));
    const { user, fetchMock, panel } = await openBroll({
      "POST /api/clips/7/broll": () => json(placed),
    });
    const list = await findSpots(user, panel);
    await user.click(
      within(list).getByRole("button", {
        name: "Use with stock video by Ana (00:12.00)",
      }),
    );

    expect(bodyOf(fetchMock, "POST", "/api/clips/7/broll")).toMatchObject({
      stock: { provider_id: "101" },
      asset_id: null,
      start: 2,
      end: 4.5,
      mode: "cutaway",
    });
    const onClip = await within(panel).findByRole("list", {
      name: "B-roll on the clip",
    });
    expect(within(onClip).getByText("00:02.00 – 00:04.50")).toBeVisible();
    expect(within(onClip).getByText("Cutaway")).toBeVisible();
    expect(
      within(onClip).getByText("Video by Ana on Pexels · Pexels License"),
    ).toBeVisible();
    expect(screen.getByRole("group", { name: "B-roll track" })).toBeVisible();
  });

  it("replaces the B-roll at a spot and removes it", async () => {
    const before = withBroll(brollItem("broll-1", 2, 4.5));
    const after = withBroll({ ...brollItem("broll-1", 2, 4.5), asset_id: 32 });
    const { user, fetchMock, panel } = await openBroll(
      {
        "PUT /api/clips/7/broll/broll-1": () => json(after),
        "DELETE /api/clips/7/broll/broll-1": () => json(withBroll()),
      },
      before,
    );
    const list = await findSpots(user, panel);
    expect(within(list).getByText("B-roll placed")).toBeVisible();
    await user.click(
      within(list).getByRole("button", {
        name: "Replace with stock video by Ben (00:12.00)",
      }),
    );
    await waitFor(() =>
      expect(
        callsTo(fetchMock, "PUT", "/api/clips/7/broll/broll-1"),
      ).toHaveLength(1),
    );
    expect(bodyOf(fetchMock, "PUT", "/api/clips/7/broll/broll-1")).toEqual({
      stock: expect.objectContaining({ provider_id: "102" }),
      asset_id: null,
    });

    await user.click(
      await within(panel).findByRole("button", {
        name: "Remove B-roll at 00:02.00 – 00:04.50",
      }),
    );
    await waitFor(() =>
      expect(
        callsTo(fetchMock, "DELETE", "/api/clips/7/broll/broll-1"),
      ).toHaveLength(1),
    );
    await waitFor(() =>
      expect(
        within(panel).queryByRole("list", { name: "B-roll on the clip" }),
      ).toBe(null),
    );
  });

  it("skips a spot", async () => {
    const { user, panel } = await openBroll();
    const list = await findSpots(user, panel);
    await user.click(
      within(list).getByRole("button", { name: "Skip the spot at 00:08.00" }),
    );
    expect(within(list).queryByText("“Then he slept”")).toBe(null);
    expect(within(list).getByText("“He ate the whole pizza”")).toBeVisible();
  });

  it("says which key is missing when no provider is enabled", async () => {
    const { panel } = await openBroll({
      "GET /api/broll/providers": () =>
        json(
          PROVIDERS.map((p) => ({ ...p, enabled: false, message: "No key" })),
        ),
    });
    expect(await within(panel).findByText("No stock provider")).toBeVisible();
    expect(within(panel).getByText("No key")).toBeVisible();
    expect(
      within(panel).queryByRole("button", { name: "Find B-roll spots" }),
    ).toBe(null);
  });
});
