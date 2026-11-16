import { useEffect, useState } from "react";
import type { Aspect } from "@/api/clips";
import type { Clip } from "@/api/types";
import { PlayerCrop } from "@/components/editor/PlayerCrop";
import { PlayerFacecam } from "@/components/editor/PlayerFacecam";
import { PlayerToolbar } from "@/components/editor/PlayerToolbar";
import { PlayerTrackPick } from "@/components/editor/PlayerTrackPick";
import { PreviewPlayer } from "@/components/editor/PreviewPlayer";
import type { ClipEdits } from "@/hooks/useClipEdits";
import type { PreviewPlayer as Player } from "@/hooks/usePreviewPlayer";
import type { SceneEdits } from "@/hooks/useSceneEdits";
import type { SceneTracker } from "@/hooks/useSceneTrack";
import { isFacecamLayout } from "@/lib/facecam";
import { previewUrl } from "@/lib/previewUrl";

interface PreviewColumnProps {
  /** The clip as saved, which the preview shows. */
  clip: Clip;
  edits: ClipEdits;
  projectAspect: Aspect;
  player: Player;
  /** The playhead's source time in seconds. */
  playhead: number;
  scenes: SceneEdits;
  tracker: SceneTracker;
}

/**
 * The editor's center column: the player toolbar over the clip's preview,
 * or over the crop tool while it is on (while the scene at the playhead is
 * in the fill layout; in screenshare or gameplay the tool moves the
 * facecam box instead), or over the subject picker while a track scene at
 * the playhead is picking its subject (before its first track, or after
 * "Pick the subject"). The preview pauses then and keeps its time; it
 * loads again after each save.
 */
export function PreviewColumn({
  clip,
  edits,
  projectAspect,
  player,
  playhead,
  scenes,
  tracker,
}: PreviewColumnProps) {
  const [cropOn, setCropOn] = useState(false);
  const { current } = scenes;
  const fill = current.layout === "fill";
  const facecam = isFacecamLayout(current.layout);
  const picking =
    fill &&
    current.mode === "track" &&
    (tracker.picking || current.crop_keyframes.length === 0);
  const canCrop = (fill && !picking) || facecam;
  const cropping = cropOn && canCrop;
  const { playing, toggle } = player;

  useEffect(() => {
    if (picking && playing) toggle();
  }, [picking, playing, toggle]);
  const toggleCropping = (next: boolean) => {
    if (next && player.playing) player.toggle();
    setCropOn(next);
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col items-center gap-4 p-6">
      <PlayerToolbar
        edits={edits}
        projectAspect={projectAspect}
        canCrop={canCrop}
        canTrack={fill && !picking}
        cropping={cropping}
        onCropping={toggleCropping}
      />
      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        <PreviewPlayer
          key={previewUrl(clip)}
          clip={clip}
          aspect={clip.framing.aspect ?? projectAspect}
          player={player}
          hidden={cropping || picking}
        />
        {picking && (
          <PlayerTrackPick
            clip={clip}
            edits={edits}
            scene={current}
            tracker={tracker}
            time={playhead}
          />
        )}
        {cropping && facecam && (
          <PlayerFacecam clip={clip} edits={edits} time={playhead} />
        )}
        {cropping && !facecam && (
          <PlayerCrop
            clip={clip}
            edits={edits}
            scenes={scenes}
            time={playhead}
          />
        )}
      </div>
    </div>
  );
}
