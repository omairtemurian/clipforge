import { ArrowCounterClockwiseIcon, TrashIcon } from "@phosphor-icons/react";
import { useRef } from "react";
import type { Clip, CropTrack } from "@/api/types";
import { CropBoxEditor } from "@/components/CropBoxEditor";
import { CropTrackGate, SourceFrame } from "@/components/editor/SourceFrame";
import { Button } from "@/components/ui/button";
import type { ClipEdits } from "@/hooks/useClipEdits";
import type { SceneEdits } from "@/hooks/useSceneEdits";
import { MIN_SCALE } from "@/lib/cropFrame";
import { cropTarget, type CropTarget } from "@/lib/cropTarget";
import { formatTimecode } from "@/lib/format";

interface PlayerCropProps {
  clip: Clip;
  edits: ClipEdits;
  scenes: SceneEdits;
  /** The playhead's source time in seconds. */
  time: number;
}

/**
 * The crop tool: the source frame at the playhead with the fill window
 * over it (of the scene there if it is fixed or tracked, else the clip's;
 * lib/cropTarget). Dragging the window moves it and dragging a corner
 * resizes it; either sets a keyframe (crop point) at the playhead, as do
 * the arrow keys on the focused window. The window's size is the clip's
 * (the scene's).
 */
export function PlayerCrop({ clip, edits, scenes, time }: PlayerCropProps) {
  return (
    <CropTrackGate clip={clip} edits={edits}>
      {(track) => (
        <CropFrame
          clip={clip}
          time={time}
          track={track}
          target={cropTarget(edits, scenes, track, time)}
        />
      )}
    </CropTrackGate>
  );
}

interface CropFrameProps {
  clip: Clip;
  time: number;
  track: CropTrack;
  target: CropTarget;
}

/** The crop tool once the clip's planned fill window (track) is loaded,
 * moving target. */
function CropFrame({ clip, time, track, target }: CropFrameProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const { rect, keyframe, place } = target;
  const frame = { width: track.frame_width, height: track.frame_height };

  return (
    <div className="flex size-full flex-col items-center justify-center gap-3">
      <SourceFrame
        projectId={clip.project_id}
        time={time}
        frame={frame}
        frameRef={frameRef}
      >
        <CropBoxEditor
          frame={frame}
          rect={rect}
          resize={{
            shape: "keep",
            minWidth: track.width * MIN_SCALE,
            maxWidth: track.width,
          }}
          label="Crop window"
          onChange={place}
        />
      </SourceFrame>
      <div className="flex items-center gap-2 text-caption text-muted-foreground">
        <span aria-live="polite">
          {keyframe
            ? `Keyframe at ${formatTimecode(time)}`
            : `Drag the window to set a keyframe at ${formatTimecode(time)}`}
        </span>
        {keyframe && (
          <Button
            type="button"
            variant="ghost"
            size="xs"
            onClick={() => target.deleteKeyframe(keyframe)}
          >
            <TrashIcon aria-hidden />
            Delete keyframe
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="xs"
          disabled={!target.canReset}
          onClick={target.reset}
        >
          <ArrowCounterClockwiseIcon aria-hidden />
          Reset crop
        </Button>
      </div>
    </div>
  );
}
