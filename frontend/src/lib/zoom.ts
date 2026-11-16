/** Auto zoom's punch-ins (TASK-23): zoom keyframes of a clip. */
import type { ZoomKeyframe } from "@/api/types";

/** The number of punch-ins of keyframes: the rises from scale 1. */
export function punchCount(keyframes: ZoomKeyframe[]): number {
  return keyframes.filter(
    (key, index) =>
      key.scale > 1 && (index === 0 || keyframes[index - 1].scale === 1),
  ).length;
}
