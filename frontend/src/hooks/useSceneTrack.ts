import { useState } from "react";
import { useTrackScene } from "@/api/clipActions";
import type { TrackSeed } from "@/api/types";
import type { SceneEdits } from "@/hooks/useSceneEdits";

export interface SceneTracker {
  /** Whether the player shows the source frame to pick a subject on. */
  picking: boolean;
  setPicking: (picking: boolean) => void;
  /** Whether the backend is tracking a subject. */
  tracking: boolean;
  /** Track the subject that seed marks through the scene at the playhead. */
  track: (seed: TrackSeed) => void;
}

/**
 * Click-to-track for the scene at the playhead: pick a subject on the
 * source frame (PlayerTrackPick), track it (POST /clips/{id}/scenes/track)
 * and make the scene a track scene at the keyframes that follow it; then
 * onTracked (the editor saves, so the preview shows it).
 */
export function useSceneTrack(
  clipId: number,
  scenes: SceneEdits,
  onTracked: () => void,
): SceneTracker {
  const [picking, setPicking] = useState(false);
  const mutation = useTrackScene(clipId);
  const scene = scenes.current;

  const track = (seed: TrackSeed) => {
    mutation.mutate(
      { start: scene.start, end: scene.end, seed },
      {
        onSuccess: (result) => {
          scenes.update({
            ...scene,
            mode: "track",
            layout: "fill",
            crop_keyframes: result.keyframes,
            track_seed: result.seed,
          });
          setPicking(false);
          onTracked();
        },
      },
    );
  };

  return { picking, setPicking, tracking: mutation.isPending, track };
}
