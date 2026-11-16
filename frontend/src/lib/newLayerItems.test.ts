import { describe, expect, it } from "vitest";
import type { MediaItem, TrackItem } from "@/api/types";
import type { LayerTracks } from "@/lib/layers";
import { NO_AUDIO_DATA } from "@/testing/assetFixtures";
import {
  accepts,
  draggedKind,
  droppedMedia,
  mediaDrag,
  mediaItem,
  mediaKind,
  mediaType,
  newItemId,
  textItem,
  type MediaDrag,
} from "@/lib/newLayerItems";

const EMPTY: LayerTracks = {
  broll: [],
  overlays: [],
  text: [],
  music: [],
  sfx: [],
  voiceover: [],
};

function media(
  kind: MediaItem["asset"]["kind"],
  duration: number | null,
): MediaItem {
  return {
    asset: {
      id: 9,
      kind,
      path: "/x",
      license: "user-supplied",
      attribution: "",
      source_url: null,
      tags: ["media-library"],
      ...NO_AUDIO_DATA,
    },
    tags: [],
    name: "file",
    mime: "x/y",
    size_bytes: 1,
    duration,
    width: null,
    height: null,
    has_thumbnail: false,
    used_in_clips: [],
  };
}

function text(id: string): TrackItem {
  return { id, kind: "text", asset_id: null, start: 0, end: 1, props: {} };
}

const VIDEO: MediaDrag = {
  asset_id: 4,
  kind: "video",
  name: "b.mp4",
  duration: 5,
};

describe("media items", () => {
  it("maps asset kinds to item kinds and tracks", () => {
    expect(mediaKind(media("video", 2))).toBe("video");
    expect(mediaKind(media("logo", null))).toBe("image");
    expect(mediaKind(media("image", null))).toBe("image");
    expect(mediaKind(media("audio", 3))).toBe("audio");
    expect(accepts("broll", "video")).toBe(true);
    expect(accepts("overlays", "image")).toBe(true);
    expect(accepts("music", "video")).toBe(false);
    expect(accepts("sfx", "audio")).toBe(true);
    expect(accepts("text", "image")).toBe(false);
  });

  it("carries the kind in the drag type and the file in its data", () => {
    const drag = mediaDrag(media("logo", null));
    expect(drag).toEqual({
      asset_id: 9,
      kind: "image",
      name: "file",
      duration: null,
    });
    const store = new Map([[mediaType("image"), JSON.stringify(drag)]]);
    const data = {
      types: [...store.keys()],
      getData: (type: string) => store.get(type) ?? "",
    };
    expect(draggedKind(data.types)).toBe("image");
    expect(droppedMedia(data)).toEqual(drag);
    expect(draggedKind(["text/plain", "Files"])).toBeNull();
    expect(droppedMedia({ types: ["text/plain"], getData: () => "" })).toBe(
      null,
    );
    expect(
      droppedMedia({ types: [mediaType("video")], getData: () => "{oops" }),
    ).toBeNull();
  });

  it("makes ids no item has", () => {
    const layers = { ...EMPTY, text: [text("broll-1")] };
    expect(newItemId(EMPTY, "broll")).toBe("broll-1");
    expect(newItemId(layers, "broll")).toBe("broll-2");
  });

  it("places a file at the drop time for its length, inside the clip", () => {
    expect(mediaItem(EMPTY, "broll", VIDEO, 2, 20)).toEqual({
      id: "broll-1",
      kind: "video",
      asset_id: 4,
      start: 2,
      end: 7,
      props: { offset: 0 },
    });
    // Too near the end: moved earlier so it ends with the clip.
    expect(mediaItem(EMPTY, "broll", VIDEO, 18, 20)).toMatchObject({
      start: 15,
      end: 20,
    });
    // Longer than the clip: as long as the clip.
    expect(
      mediaItem(
        EMPTY,
        "music",
        { ...VIDEO, kind: "audio", duration: 90 },
        3,
        20,
      ),
    ).toMatchObject({ start: 0, end: 20, props: { volume: 1, offset: 0 } });
    const image = { ...VIDEO, kind: "image" as const, duration: null };
    expect(mediaItem(EMPTY, "overlays", image, 1, 20)).toMatchObject({
      kind: "image",
      start: 1,
      end: 4,
      props: { x: 0.5, y: 0.5, width: 0.3, opacity: 1, offset: 0 },
    });
  });

  it("refuses a track that does not hold the file or a clip with no length", () => {
    expect(mediaItem(EMPTY, "music", VIDEO, 0, 20)).toBeNull();
    expect(mediaItem(EMPTY, "text", VIDEO, 0, 20)).toBeNull();
    expect(mediaItem(EMPTY, "broll", VIDEO, 0, 0)).toBeNull();
  });
});

describe("textItem", () => {
  it("adds a text layer at the playhead for 3 s", () => {
    expect(textItem(EMPTY, "Hi", 4, 20)).toEqual({
      id: "text-1",
      kind: "text",
      asset_id: null,
      start: 4,
      end: 7,
      props: { text: "Hi" },
    });
  });

  it("stops at five text layers", () => {
    const layers = {
      ...EMPTY,
      text: ["a", "b", "c", "d", "e"].map(text),
    };
    expect(textItem(layers, "Hi", 0, 20)).toBeNull();
  });
});
