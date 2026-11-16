/**
 * Text layers (the text track's items) and the transitions at a clip's
 * cuts, as the editor's panels show and change them.
 */
import type {
  ClipTransitions,
  TextProps,
  TrackItem,
  Transition,
} from "@/api/types";

/** A text item's props where it sets none (models.TextProps). */
export const TEXT_DEFAULTS: TextProps = {
  text: "Text",
  font: "Montserrat ExtraBold",
  size: 0.06,
  color: "#FFFFFF",
  stroke: null,
  stroke_width: 0.08,
  box: null,
  box_opacity: 1,
  x: 0.5,
  y: 0.2,
  animation_in: "none",
  animation_out: "none",
  in_seconds: 0.4,
  out_seconds: 0.4,
};

export type TextAnimation = TextProps["animation_in"];

export const TEXT_ANIMATIONS: { value: TextAnimation; label: string }[] = [
  { value: "none", label: "None" },
  { value: "fade", label: "Fade" },
  { value: "slide_up", label: "Slide up" },
  { value: "slide_down", label: "Slide down" },
  { value: "slide_left", label: "Slide left" },
  { value: "slide_right", label: "Slide right" },
  { value: "pop", label: "Pop" },
];

/** The longest a text item's text can be. */
export const TEXT_MAX = 200;

/** A text item's props, its defaults filled in. */
export function textProps(item: TrackItem): TextProps {
  return { ...TEXT_DEFAULTS, ...(item.props as Partial<TextProps>) };
}

/** items with the props of the item whose id is id changed by changes. */
export function withProps(
  items: TrackItem[],
  id: string,
  changes: Partial<TextProps>,
): TrackItem[] {
  return items.map((item) =>
    item.id === id ? { ...item, props: { ...item.props, ...changes } } : item,
  );
}

export type TransitionKind = Transition["kind"];

export const TRANSITION_KINDS: { value: TransitionKind; label: string }[] = [
  { value: "crossfade", label: "Crossfade" },
  { value: "zoom_punch", label: "Zoom punch" },
  { value: "whip", label: "Whip" },
  { value: "slide", label: "Slide" },
];

/** A new transition's length, and the shortest and longest one (s). */
export const TRANSITION_DEFAULT_S = 0.3;
export const TRANSITION_MIN_S = 0.1;
export const TRANSITION_MAX_S = 1;

export const NO_TRANSITIONS: ClipTransitions = { auto: null, sections: [] };

/** A transition of kind lasting what current lasted (else the default);
 * null for "none". */
export function pickTransition(
  kind: TransitionKind | "none",
  current: Transition | null,
): Transition | null {
  if (kind === "none") return null;
  return { kind, duration: current?.duration ?? TRANSITION_DEFAULT_S };
}

/** The transition at the cut after section index (null: a hard cut). */
export function sectionTransition(
  transitions: ClipTransitions,
  index: number,
): Transition | null {
  return transitions.sections[index] ?? null;
}

/**
 * transitions with the cut after section index set to transition, padding
 * earlier cuts with hard cuts; trailing hard cuts are dropped.
 */
export function withSectionTransition(
  transitions: ClipTransitions,
  index: number,
  transition: Transition | null,
): ClipTransitions {
  const sections = [...transitions.sections];
  while (sections.length <= index) sections.push(null);
  sections[index] = transition;
  while (sections.length > 0 && sections[sections.length - 1] === null) {
    sections.pop();
  }
  return { ...transitions, sections };
}

/** transitions with every cut between count sections set to transition. */
export function withAllSections(
  transitions: ClipTransitions,
  count: number,
  transition: Transition | null,
): ClipTransitions {
  const cuts = Math.max(0, count - 1);
  return {
    ...transitions,
    sections: transition ? Array.from({ length: cuts }, () => transition) : [],
  };
}
