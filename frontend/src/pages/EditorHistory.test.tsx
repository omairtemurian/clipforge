import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, ClipHistory, TrackItem } from "@/api/types";
import {
  CLIP,
  mockLayoutAndMedia,
  renderEditor,
  stat,
  video,
} from "@/testing/editor";
import { callsTo, json } from "@/testing/mockApi";

beforeEach(() => {
  mockLayoutAndMedia();
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function textItem(id: string, start: number, end: number): TrackItem {
  return { id, kind: "text", asset_id: null, start, end, props: { text: id } };
}

const LAYERED: Clip = {
  ...CLIP,
  tracks: { ...CLIP.tracks, text: [textItem("Hi", 2, 4)] },
};

const HISTORY: ClipHistory = {
  current: 2,
  can_undo: true,
  can_redo: false,
  versions: [
    {
      number: 1,
      kind: "original",
      created_at: "2026-11-01T20:00:00",
      fields: [],
      restored_from: null,
    },
    {
      number: 2,
      kind: "edit",
      created_at: "2026-11-01T20:05:00",
      fields: ["segments", "title"],
      restored_from: null,
    },
  ],
};

const textTrack = () => screen.getByRole("group", { name: "Text track" });

async function openEditor(routes = {}) {
  const user = userEvent.setup();
  const fetchMock = renderEditor(LAYERED, undefined, routes);
  await screen.findByRole("heading", { name: "Pizza night" });
  return { user, fetchMock };
}

describe("editor keyboard on layer items", () => {
  it("selects an item, deletes it with Delete and undoes that", async () => {
    const { user } = await openEditor();
    const block = within(textTrack()).getByRole("button");

    await user.click(block);
    expect(block).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: "Delete selection (Delete)" }),
    ).toBeEnabled();
    await user.keyboard("{Delete}");
    expect(within(textTrack()).queryByRole("button")).toBeNull();
    expect(
      screen.getByRole("status", { name: "Autosave status" }),
    ).toHaveTextContent("Unsaved changes");

    await user.keyboard("{Meta>}z{/Meta}");
    expect(within(textTrack()).getByRole("button")).toBeInTheDocument();
  });

  it("copies an item and pastes it at the playhead", async () => {
    const { user } = await openEditor();
    await user.click(within(textTrack()).getByRole("button"));

    await user.keyboard("{Meta>}c{/Meta}");
    await user.keyboard("{Meta>}v{/Meta}");

    // The playhead is at the clip's start: the copy is clip time 0-2 s.
    const copy = screen.getByRole("button", {
      name: "Text: Hi, 00:00.00 - 00:02.00",
    });
    expect(copy).toHaveAttribute("aria-pressed", "true");
    expect(within(textTrack()).getAllByRole("button")).toHaveLength(2);
  });
});

describe("playback speed", () => {
  it("sets the preview's speed from the menu and with < / >", async () => {
    const { user } = await openEditor();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Playback speed" }),
      "1.5",
    );
    expect(video().playbackRate).toBe(1.5);

    await user.click(document.body);
    await user.keyboard(">");
    expect(video().playbackRate).toBe(2);
    expect(video().defaultPlaybackRate).toBe(2);
    await user.keyboard("<<");
    expect(video().playbackRate).toBe(1.25);
    expect(
      screen.getByRole("combobox", { name: "Playback speed" }),
    ).toHaveValue("1.25");
  });
});

describe("version history", () => {
  it("lists the saved versions and restores one", async () => {
    const restored: Clip = { ...LAYERED, start: 12, end: 30 };
    const { user, fetchMock } = await openEditor({
      "GET /api/clips/7/versions": () => json(HISTORY),
      "POST /api/clips/7/versions/1/restore": () => json(restored),
    });
    await user.click(screen.getByRole("button", { name: "Version history" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Version history",
    });
    const items = within(dialog).getAllByRole("listitem");
    expect(items.map((item) => item.getAttribute("aria-label"))).toEqual([
      "Version 2",
      "Version 1",
    ]);
    expect(items[0]).toHaveTextContent("Current");
    expect(items[0]).toHaveTextContent("Edited trim, title");
    expect(within(items[0]).queryByRole("button")).toBeNull();
    expect(items[1]).toHaveTextContent("Original clip");

    await user.click(within(items[1]).getByRole("button", { name: "Restore" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(
      callsTo(fetchMock, "POST", "/api/clips/7/versions/1/restore"),
    ).toHaveLength(1);
    expect(stat("In")).toBe("00:12.00");
  });

  it("undoes a saved clip on the server", async () => {
    const earlier: Clip = { ...LAYERED, start: 12, end: 30 };
    const { user, fetchMock } = await openEditor({
      "GET /api/clips/7/versions": () => json(HISTORY),
      "POST /api/clips/7/undo": () => json(earlier),
    });
    const undo = screen.getByRole("button", { name: "Undo" });
    await waitFor(() => expect(undo).toBeEnabled());

    await user.click(undo);

    await waitFor(() => expect(stat("In")).toBe("00:12.00"));
    expect(callsTo(fetchMock, "POST", "/api/clips/7/undo")).toHaveLength(1);
  });
});

describe("autosave", () => {
  it("saves the edits once they rest, unless turned off", async () => {
    const tracksPatched = vi.fn();
    const { user, fetchMock } = await openEditor({
      "PATCH /api/clips/7": () => json(LAYERED),
      "PATCH /api/clips/7/tracks": (_url: string, init?: RequestInit) => {
        tracksPatched();
        const tracks = JSON.parse(String(init?.body)) as Clip["tracks"];
        return json({ ...LAYERED, tracks: { ...LAYERED.tracks, ...tracks } });
      },
    });
    await user.click(within(textTrack()).getByRole("button"));
    await user.keyboard("{Delete}");

    await waitFor(() => expect(tracksPatched).toHaveBeenCalled(), {
      timeout: 4000,
    });
    expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1);
    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "Autosave status" }),
      ).toHaveTextContent("All changes saved"),
    );

    await user.click(screen.getByRole("button", { name: "Autosave" }));
    expect(screen.getByRole("button", { name: "Autosave" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(
      screen.getByRole("status", { name: "Autosave status" }),
    ).toHaveTextContent("Autosave off");
  });
});
