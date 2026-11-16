/**
 * A clip's layer tracks as the backend stores them: PATCH /clips/{id}/tracks
 * fills in the props an item sets none of (timeline.tidy_props), so the
 * editor compares its layers with the saved ones that way.
 */
import type { TrackItem } from "@/api/types";
import { LAYER_NAMES, type LayerName, type LayerTracks } from "@/lib/layers";
import { TEXT_DEFAULTS } from "@/lib/overlays";

/** The props the backend fills in, by track, in its props models' field
 * order (BrollProps, OverlayProps, TextProps, AudioProps, MusicProps,
 * VoiceoverProps). */
export const SAVED_PROP_DEFAULTS: Record<LayerName, Record<string, unknown>> = {
  broll: { offset: 0, mode: "cutaway", x: 0.5, y: 0.3, width: 0.8 },
  overlays: { x: 0.5, y: 0.5, width: 0.3, opacity: 1, offset: 0 },
  text: { ...TEXT_DEFAULTS },
  music: { volume: 1, offset: 0, fade_in: 0, fade_out: 0, duck: true },
  sfx: { volume: 1, offset: 0 },
  voiceover: {
    volume: 1,
    offset: 0,
    text: null,
    voice: null,
    speed: 1,
    duck: true,
  },
};

/** item's props as the backend saves them on track name: its defaults
 * filled in, a voiceover's text without surrounding whitespace. */
export function tidyProps(
  name: LayerName,
  item: TrackItem,
): Record<string, unknown> {
  const props = { ...SAVED_PROP_DEFAULTS[name], ...item.props };
  if (name === "voiceover" && typeof props.text === "string") {
    props.text = props.text.trim();
  }
  return props;
}

/** item on track name as a string that is the same for items the backend
 * saves alike (props in key order, defaults filled in). */
function itemKey(name: LayerName, item: TrackItem): string {
  const props = tidyProps(name, item);
  const sorted = Object.keys(props)
    .sort()
    .map((key) => [key, props[key]]);
  return JSON.stringify([
    item.id,
    item.kind,
    item.asset_id,
    item.start,
    item.end,
    sorted,
  ]);
}

/** Whether layers a and b are saved as the same tracks. */
export function sameLayers(a: LayerTracks, b: LayerTracks): boolean {
  return LAYER_NAMES.every((name) => {
    const left = a[name];
    const right = b[name];
    return (
      left.length === right.length &&
      left.every(
        (item, index) => itemKey(name, item) === itemKey(name, right[index]),
      )
    );
  });
}
