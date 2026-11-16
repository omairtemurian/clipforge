/**
 * New items of a clip's layer tracks: a media library file dropped on a
 * track (or added at the playhead) and a text layer. Items are timed in
 * seconds of the rendered clip (its cuts left out), like every layer item.
 */
import type { MediaItem, TrackItem } from "@/api/types";
import {
  LAYER_NAMES,
  MIN_ITEM_S,
  moveSpan,
  type LayerName,
  type LayerTracks,
} from "@/lib/layers";

/** The kind of item a media file becomes on the timeline. */
export type MediaItemKind = "video" | "image" | "audio";

/** The most text layers a clip renders (MAX_TEXT_LAYERS of the backend). */
export const MAX_TEXT_LAYERS = 5;
/** How long a new image or text item lasts, in seconds. */
export const STILL_S = 3;

/** The drag data type of a media file of a kind; its data is the file's
 * MediaDrag as JSON. The kind is in the type because a drag over a track
 * can only read the types, not the data. */
const MEDIA_MIME = "application/x-clipforge-media-";

/** What a dragged media file carries. */
export interface MediaDrag {
  asset_id: number;
  kind: MediaItemKind;
  name: string;
  duration: number | null;
}

/** The tracks that hold items of each kind. */
export const KIND_TRACKS: Record<MediaItemKind, LayerName[]> = {
  video: ["broll", "overlays"],
  image: ["overlays", "broll"],
  audio: ["music", "sfx", "voiceover"],
};

/** The props of a new item on each media track (the backend's defaults). */
const MEDIA_PROPS: Record<
  Exclude<LayerName, "text">,
  Record<string, unknown>
> = {
  broll: { offset: 0 },
  overlays: { x: 0.5, y: 0.5, width: 0.3, opacity: 1, offset: 0 },
  music: { volume: 1, offset: 0 },
  sfx: { volume: 1, offset: 0 },
  voiceover: { volume: 1, offset: 0 },
};

/** The item kind a media file plays as, by its asset kind. */
export function mediaKind(media: MediaItem): MediaItemKind {
  const kind = media.asset.kind;
  if (kind === "video") return "video";
  if (kind === "image" || kind === "logo") return "image";
  return "audio";
}

/** What dragging media carries. */
export function mediaDrag(media: MediaItem): MediaDrag {
  return {
    asset_id: media.asset.id,
    kind: mediaKind(media),
    name: media.name,
    duration: media.duration,
  };
}

/** The drag data type of a media file of kind. */
export function mediaType(kind: MediaItemKind): string {
  return `${MEDIA_MIME}${kind}`;
}

/** The media kind a drag carries, from its data types (lowercased by the
 * browser), if it is a media file. */
export function draggedKind(types: readonly string[]): MediaItemKind | null {
  for (const type of types) {
    if (!type.startsWith(MEDIA_MIME)) continue;
    const kind = type.slice(MEDIA_MIME.length);
    if (kind === "video" || kind === "image" || kind === "audio") return kind;
  }
  return null;
}

/** The media a drop carries (its data of type mediaType(kind)), if any. */
export function droppedMedia(
  data: Pick<DataTransfer, "types" | "getData">,
): MediaDrag | null {
  const kind = draggedKind(Array.from(data.types));
  if (!kind) return null;
  try {
    const parsed = JSON.parse(data.getData(mediaType(kind))) as MediaDrag;
    return typeof parsed.asset_id === "number" ? { ...parsed, kind } : null;
  } catch {
    return null;
  }
}

/** Whether a track holds items of kind. */
export function accepts(name: LayerName, kind: MediaItemKind): boolean {
  return KIND_TRACKS[kind].includes(name);
}

/** An item id no layer item has yet: base-1, base-2, ... */
export function newItemId(layers: LayerTracks, base: string): string {
  const taken = new Set(
    LAYER_NAMES.flatMap((name) => layers[name].map((item) => item.id)),
  );
  for (let n = 1; ; n += 1) {
    if (!taken.has(`${base}-${n}`)) return `${base}-${n}`;
  }
}

/**
 * A new item of track name that plays media from clip time at (moved
 * earlier so it ends by length): as long as the file for video and audio
 * (STILL_S if unknown), STILL_S for an image, never longer than the clip.
 * Null if the track does not hold the media or the clip is too short.
 */
export function mediaItem(
  layers: LayerTracks,
  name: LayerName,
  media: MediaDrag,
  at: number,
  length: number,
): TrackItem | null {
  if (name === "text" || !accepts(name, media.kind) || length < MIN_ITEM_S) {
    return null;
  }
  const lasts =
    media.kind === "image" || !media.duration ? STILL_S : media.duration;
  return {
    id: newItemId(layers, name),
    kind: media.kind,
    asset_id: media.asset_id,
    ...moveSpan({ start: 0, end: Math.max(MIN_ITEM_S, lasts) }, at, length),
    props: { ...MEDIA_PROPS[name] },
  };
}

/** A new text layer saying text from clip time at for STILL_S (inside the
 * clip), or null if the clip has MAX_TEXT_LAYERS already or is too short. */
export function textItem(
  layers: LayerTracks,
  text: string,
  at: number,
  length: number,
): TrackItem | null {
  if (layers.text.length >= MAX_TEXT_LAYERS || length < MIN_ITEM_S) {
    return null;
  }
  return {
    id: newItemId(layers, "text"),
    kind: "text",
    asset_id: null,
    ...moveSpan({ start: 0, end: STILL_S }, at, length),
    props: { text },
  };
}
