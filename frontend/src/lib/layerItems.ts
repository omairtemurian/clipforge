/**
 * Picking, deleting and pasting the items of a clip's layer tracks (the
 * editor's Delete and cmd+C / cmd+V on a selected item).
 */
import type { TrackItem } from "@/api/types";
import {
  LAYER_NAMES,
  moveSpan,
  type LayerName,
  type LayerTracks,
} from "@/lib/layers";

/** A layer item and the track it is on. */
export interface LayerItem {
  name: LayerName;
  item: TrackItem;
}

/** The item with id id and its track, if a layer track has it. */
export function findItem(
  layers: LayerTracks,
  id: string | null,
): LayerItem | null {
  if (id === null) return null;
  for (const name of LAYER_NAMES) {
    const item = layers[name].find((each) => each.id === id);
    if (item) return { name, item };
  }
  return null;
}

/** items without the item whose id is id. */
export function removeItem(items: TrackItem[], id: string): TrackItem[] {
  return items.filter((item) => item.id !== id);
}

/** An item id no layer item has yet, made from base ("text-1" ->
 * "text-1-copy", then "text-1-copy-2", ...). */
export function copyId(layers: LayerTracks, base: string): string {
  const taken = new Set(
    LAYER_NAMES.flatMap((name) => layers[name].map((item) => item.id)),
  );
  const root = base.replace(/-copy(-\d+)?$/, "");
  for (let n = 1; ; n += 1) {
    const id = n === 1 ? `${root}-copy` : `${root}-copy-${n}`;
    if (!taken.has(id)) return id;
  }
}

/**
 * A copy of item (a new id, same props) starting at clip time at, kept
 * inside [0, length] with its duration (shortened if the clip is shorter).
 */
export function pastedItem(
  layers: LayerTracks,
  item: TrackItem,
  at: number,
  length: number,
): TrackItem {
  return {
    ...item,
    props: structuredClone(item.props),
    id: copyId(layers, item.id),
    ...moveSpan(item, at, length),
  };
}
