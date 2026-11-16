import {
  createEvent,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, MediaItem } from "@/api/types";
import { NO_AUDIO_DATA } from "@/testing/assetFixtures";
import {
  CLIP,
  mockLayoutAndMedia,
  renderEditor,
  WORDS,
} from "@/testing/editor";
import { callsTo, clip, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function media(
  id: number,
  kind: MediaItem["asset"]["kind"],
  name: string,
  duration: number | null,
): MediaItem {
  return {
    asset: {
      id,
      kind,
      path: `/media/${name}`,
      license: "user-supplied",
      attribution: "",
      source_url: null,
      tags: ["media-library"],
      ...NO_AUDIO_DATA,
    },
    tags: [],
    name,
    mime: "video/mp4",
    size_bytes: 100,
    duration,
    width: 320,
    height: 180,
    has_thumbnail: false,
    used_in_clips: [],
  };
}

const LIBRARY = [
  media(9, "video", "city.mp4", 5),
  media(10, "logo", "logo.png", null),
  media(11, "audio", "beat.mp3", 30),
];

/** A drag's data store, as a browser's DataTransfer keeps it. */
function dataTransfer() {
  const store = new Map<string, string>();
  const types: string[] = [];
  return {
    types,
    dropEffect: "none",
    effectAllowed: "all",
    setData(type: string, value: string) {
      if (!store.has(type)) types.push(type);
      store.set(type, value);
    },
    getData: (type: string) => store.get(type) ?? "",
  };
}

/** Drop data on element at clientX (jsdom has no DragEvent, which would
 * carry it). */
function drop(element: Element, data: object, clientX: number) {
  const event = createEvent.drop(element, { dataTransfer: data });
  Object.defineProperty(event, "clientX", { value: clientX });
  fireEvent(element, event);
}

const track = (name: string) =>
  screen.getByRole("group", { name: `${name} track` });

/** The tracks PATCH body of the first save. */
async function savedTracks(fetchMock: ReturnType<typeof renderEditor>) {
  await waitFor(() =>
    expect(callsTo(fetchMock, "PATCH", "/api/clips/7/tracks")).toHaveLength(1),
  );
  return JSON.parse(
    String(callsTo(fetchMock, "PATCH", "/api/clips/7/tracks")[0][1]?.body),
  );
}

async function openPanel(name: string, data: Clip = CLIP) {
  const user = userEvent.setup();
  const fetchMock = renderEditor(data, WORDS, {
    "GET /api/library": () => json(LIBRARY),
    "PATCH /api/clips/7": () => json(data),
    "PATCH /api/clips/7/tracks": (_url, init) =>
      json({
        ...data,
        tracks: { ...data.tracks, ...JSON.parse(String(init?.body)) },
      }),
  });
  await screen.findByRole("heading", { name: "Pizza night" });
  await user.click(screen.getByRole("button", { name }));
  return { user, fetchMock };
}

describe("media library panel", () => {
  it("drags a video onto the B-roll track at the drop time and saves it", async () => {
    const { user, fetchMock } = await openPanel("Media");
    const tile = await screen.findByLabelText(
      "Drag city.mp4 onto the timeline",
    );
    const data = dataTransfer();
    fireEvent.dragStart(tile, { dataTransfer: data });

    // Music does not hold video: the drag is not taken there.
    expect(fireEvent.dragOver(track("Music"), { dataTransfer: data })).toBe(
      true,
    );
    expect(fireEvent.dragOver(track("B-roll"), { dataTransfer: data })).toBe(
      false,
    );
    expect(track("B-roll")).toHaveAttribute("data-drop-target", "true");
    // 120 px is source 12 s: clip time 2 s; the video lasts 5 s.
    drop(track("B-roll"), data, 120);

    expect(
      within(track("B-roll")).getByRole("button", {
        name: "B-roll: Video #9, 00:02.00 - 00:07.00",
      }),
    ).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const body = await savedTracks(fetchMock);
    expect(body.broll).toEqual([
      {
        id: "broll-1",
        kind: "video",
        asset_id: 9,
        start: 2,
        end: 7,
        props: { offset: 0 },
      },
    ]);
  });

  it("adds a logo at the playhead with +, and filters by kind", async () => {
    const { user } = await openPanel("Media");
    await user.click(
      await screen.findByRole("button", {
        name: "Add logo.png to the Overlays track",
      }),
    );
    expect(
      within(track("Overlays")).getByRole("button", {
        name: "Overlays: Image #10, 00:00.00 - 00:03.00",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Audio" }));
    const files = screen.getByRole("list", { name: "Media files" });
    expect(within(files).getAllByRole("listitem")).toHaveLength(1);
    expect(within(files).getByText("beat.mp3")).toBeInTheDocument();
  });

  it("uploads a file to the library", async () => {
    const user = userEvent.setup();
    let library: MediaItem[] = [];
    const fetchMock = renderEditor(CLIP, WORDS, {
      "GET /api/library": () => json(library),
      "POST /api/library": () => {
        library = [media(12, "image", "photo.png", null)];
        return json(library[0], 201);
      },
    });
    await screen.findByRole("heading", { name: "Pizza night" });
    await user.click(screen.getByRole("button", { name: "Media" }));
    expect(await screen.findByText("No media yet")).toBeInTheDocument();

    await user.upload(
      screen.getByLabelText("Upload media files"),
      new File(["png"], "photo.png", { type: "image/png" }),
    );

    expect(await screen.findByText("photo.png")).toBeInTheDocument();
    const form = callsTo(fetchMock, "POST", "/api/library")[0][1]
      ?.body as FormData;
    expect((form.get("file") as File).name).toBe("photo.png");
  });
});

describe("text layers panel", () => {
  it("adds a text layer at the playhead, styles it and saves it", async () => {
    const { user, fetchMock } = await openPanel("Text layers");
    expect(screen.getByText("No text layers")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Add text" }));
    expect(screen.getByText("1 of 5 text layers")).toBeInTheDocument();
    const text = screen.getByLabelText("Text");
    await user.clear(text);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "A text layer needs text.",
    );
    await user.type(text, "Big news");
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Animation in" }),
      "fade",
    );
    await user.click(screen.getByRole("switch", { name: "Background box" }));

    expect(
      within(track("Text")).getByRole("button", {
        name: "Text: Big news, 00:00.00 - 00:03.00",
      }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const body = await savedTracks(fetchMock);
    expect(body.text).toEqual([
      {
        id: "text-1",
        kind: "text",
        asset_id: null,
        start: 0,
        end: 3,
        props: { text: "Big news", animation_in: "fade", box: "#000000" },
      },
    ]);
  });

  it("opens the text layer selected on the timeline and deletes it", async () => {
    const layered = clip({
      ...CLIP,
      tracks: {
        ...CLIP.tracks,
        text: [
          {
            id: "hook",
            kind: "text",
            asset_id: null,
            start: 1,
            end: 2,
            props: { text: "Hook", size: 0.1 },
          },
        ],
      },
    });
    const { user } = await openPanel("Text layers", layered);
    expect(screen.queryByText("Selected text")).not.toBeInTheDocument();

    fireEvent.focus(within(track("Text")).getByRole("button"));

    expect(screen.getByLabelText("Text")).toHaveValue("Hook");
    expect(screen.getByText("10%")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete text layer" }));
    expect(within(track("Text")).queryByRole("button")).toBeNull();
    expect(screen.getByText("0 of 5 text layers")).toBeInTheDocument();
  });

  it("stops adding at five text layers", async () => {
    const five = ["a", "b", "c", "d", "e"].map((id, index) => ({
      id,
      kind: "text" as const,
      asset_id: null,
      start: index,
      end: index + 1,
      props: { text: id },
    }));
    await openPanel(
      "Text layers",
      clip({ ...CLIP, tracks: { ...CLIP.tracks, text: five } }),
    );
    expect(screen.getByRole("button", { name: "Add text" })).toBeDisabled();
  });
});

describe("transition picker", () => {
  const TWO = clip({
    ...CLIP,
    segments: [
      [10, 20],
      [30, 40],
    ],
  });

  it("sets the jump cut and section transitions and saves them", async () => {
    const { user, fetchMock } = await openPanel("Transitions", TWO);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "At jump cuts" }),
      "zoom_punch",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Section 1 to 2" }),
      "whip",
    );
    expect(
      screen.getByRole("slider", { name: "Section 1 to 2 length" }),
    ).toHaveAttribute("aria-valuenow", "0.3");

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
    );
    const body = JSON.parse(
      String(callsTo(fetchMock, "PATCH", "/api/clips/7")[0][1]?.body),
    );
    expect(body.transitions).toEqual({
      auto: { kind: "zoom_punch", duration: 0.3 },
      sections: [{ kind: "whip", duration: 0.3 }],
    });
  });

  it("undoes a transition and explains a clip with one section", async () => {
    const { user } = await openPanel("Transitions");
    expect(screen.getByText(/The clip plays one section/)).toBeInTheDocument();
    const auto = screen.getByRole("combobox", { name: "At jump cuts" });
    await user.selectOptions(auto, "crossfade");
    expect(auto).toHaveValue("crossfade");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(auto).toHaveValue("none");
  });
});
