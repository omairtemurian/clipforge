/**
 * The ways to frame a scene as the editor offers them (lib/scenes): their
 * icons, hints and order, and the clip layouts of the player toolbar.
 */
import {
  ArrowsInIcon,
  ColumnsIcon,
  CrosshairIcon,
  GameControllerIcon,
  PictureInPictureIcon,
  PushPinIcon,
  RowsIcon,
  ScanIcon,
  ScreencastIcon,
  SquareIcon,
} from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { Clip } from "@/api/types";
import { SCENE_LABELS, type SceneChoice } from "@/lib/scenes";

type Layout = Clip["layout"];

/** The icon of each way to frame a scene. */
export const LAYOUT_ICONS: Record<SceneChoice, ReactNode> = {
  auto: <ScanIcon aria-hidden />,
  track: <CrosshairIcon aria-hidden />,
  fixed: <PushPinIcon aria-hidden />,
  fit: <ArrowsInIcon aria-hidden />,
  square_blur: <SquareIcon aria-hidden />,
  split: <RowsIcon aria-hidden />,
  grid: <ColumnsIcon aria-hidden />,
  pip: <PictureInPictureIcon aria-hidden />,
  screenshare: <ScreencastIcon aria-hidden />,
  gameplay: <GameControllerIcon aria-hidden />,
};

/** What each way to frame a scene shows. */
export const LAYOUT_HINTS: Record<SceneChoice, string> = {
  auto: "Crops the video to fill the frame and follows the speaker.",
  track:
    "Crops the video to fill the frame and follows the subject you click on the video.",
  fixed:
    "Crops the video where you put the window; the crop tool sets keyframes at the playhead.",
  fit: "Shows the whole video over a blurred copy of itself.",
  square_blur:
    "Shows a square of the video around the people over a blurred copy of itself.",
  split: "Stacks the left and the right speaker, one above the other.",
  grid: "Shows the left, middle and right speaker side by side or stacked.",
  pip: "Follows the speaker, with the other speaker in a corner.",
  screenshare:
    "Shows the whole screen, with the facecam below it; the crop tool moves the facecam box.",
  gameplay:
    "Shows the facecam above the middle of the gameplay; the crop tool moves the facecam box.",
};

/** Every way to frame a scene, in the order the picker shows them. */
export const SCENE_CHOICES: SceneChoice[] = [
  "auto",
  "track",
  "fixed",
  "fit",
  "square_blur",
  "split",
  "grid",
  "pip",
  "screenshare",
  "gameplay",
];

/** Short names of the layouts, for the player toolbar's button. */
const SHORT: Partial<Record<Layout, string>> = {
  fill: "Fill",
  pip: "PiP",
  screenshare: "Screenshare",
  gameplay: "Gameplay",
};

/** A clip's layouts, as the player toolbar's menu lists them. */
export const CLIP_LAYOUTS: {
  value: Layout;
  label: string;
  short: string;
  icon: ReactNode;
}[] = (
  ["fill", "fit", "split", "grid", "pip", "screenshare", "gameplay"] as const
).map((value) => {
  const label = value === "fill" ? "Fill" : SCENE_LABELS[value];
  return {
    value,
    label,
    short: SHORT[value] ?? label,
    icon: LAYOUT_ICONS[value === "fill" ? "auto" : value],
  };
});
