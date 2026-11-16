/**
 * The audio of a clip's timeline (SPEC-v2 3.5): the music item the Audio
 * panel puts on the music track, the props of music items,
 * and how they are shown. Items are timed in seconds of the rendered clip.
 */
import type { MusicProps, TrackItem } from "@/api/types";
import type { LayerTracks } from "@/lib/layers";
import { MIN_ITEM_S } from "@/lib/layers";
import { newItemId } from "@/lib/newLayerItems";

/** The longest fade of a music item, in seconds (MUSIC_FADE_MAX). */
export const MUSIC_FADE_MAX = 10;
/** The most sound effects one AI run places (SFX_ITEMS_MAX). */
export const SFX_ITEMS_MAX = 8;
export const SFX_ITEMS_DEFAULT = 5;
/** The loudest an audio item can be (1: as recorded). */
export const VOLUME_MAX = 2;

/** What a new music item starts with: under the speech, with short fades. */
export const MUSIC_DEFAULTS: MusicProps = {
  volume: 0.5,
  offset: 0,
  fade_in: 1,
  fade_out: 1,
  duck: true,
};

/** A level as a percentage: 0.5 -> "50%". */
export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Seconds as "3.5 s". */
export function seconds(value: number): string {
  return `${value.toFixed(1)} s`;
}

/** A music item's props, its defaults filled in. */
export function musicProps(item: TrackItem): MusicProps {
  return { ...MUSIC_DEFAULTS, ...(item.props as Partial<MusicProps>) };
}

/** items with the props of the item with id id changed by changes. */
export function patchProps(
  items: TrackItem[],
  id: string,
  changes: Partial<MusicProps>,
): TrackItem[] {
  return items.map((item) =>
    item.id === id ? { ...item, props: { ...item.props, ...changes } } : item,
  );
}

/** The music item the panel edits: the selected one if it is on the music
 * track, else the first. */
export function currentMusic(
  layers: LayerTracks,
  selected: string | null,
): TrackItem | undefined {
  return layers.music.find((item) => item.id === selected) ?? layers.music[0];
}

/**
 * The music track's items after choosing asset assetId: the current item
 * plays it instead (its times and settings kept), else a new item plays it
 * over the whole clip of length seconds (the file loops) with the default
 * settings. Null if the clip is too short.
 */
export function chooseMusic(
  layers: LayerTracks,
  current: TrackItem | undefined,
  assetId: number,
  length: number,
): TrackItem[] | null {
  if (current) {
    return layers.music.map((item) =>
      item.id === current.id ? { ...item, asset_id: assetId } : item,
    );
  }
  if (length < MIN_ITEM_S) return null;
  const item: TrackItem = {
    id: newItemId(layers, "music"),
    kind: "audio",
    asset_id: assetId,
    start: 0,
    end: Math.floor(length * 1000) / 1000,
    props: { ...MUSIC_DEFAULTS },
  };
  return [...layers.music, item];
}
