/**
 * The viral hook, headline and motion graphics of a clip (SPEC-v2 3.5),
 * as the editor's panels show them.
 */
import type { TrackItem } from "@/api/types";

/** The longest hook text, and the shortest and longest hook (s): the
 * backend's HOOK_TEXT_MAX, HOOK_SECONDS_MIN and HOOK_SECONDS_MAX. */
export const HOOK_TEXT_MAX = 60;
export const HOOK_SECONDS_MIN = 2;
export const HOOK_SECONDS_MAX = 3;

/** The most motion graphics one request asks for, and the default. */
export const MOTION_GRAPHICS_MAX = 5;
export const MOTION_GRAPHICS_DEFAULT = 3;

/** The id of the headline's text item, and the prefix of the ids of the
 * motion graphics' (pipeline/headline, pipeline/motion_graphics). */
export const HEADLINE_ITEM = "headline";
const MOTION_PREFIX = "mg-";

/** Where a hook's text comes from. */
export type HookSource = "captions" | "theme" | "text";

export const HOOK_SOURCES: { value: HookSource; label: string }[] = [
  { value: "captions", label: "Opening words of the captions" },
  { value: "theme", label: "A line the AI writes" },
  { value: "text", label: "My own text" },
];

/** Whether the clip's text track holds its headline item. */
export function hasHeadlineItem(items: TrackItem[]): boolean {
  return items.some((item) => item.id === HEADLINE_ITEM);
}

/** The motion graphic items of a text track, in time order. */
export function motionGraphics(items: TrackItem[]): TrackItem[] {
  return items
    .filter((item) => item.id.startsWith(MOTION_PREFIX))
    .sort((a, b) => a.start - b.start);
}
