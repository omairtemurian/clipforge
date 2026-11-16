import { CircleNotchIcon } from "@phosphor-icons/react";
import { useRef, useState, type PointerEvent } from "react";
import type { Clip, SceneReframe } from "@/api/types";
import { CropTrackGate, SourceFrame } from "@/components/editor/SourceFrame";
import { Button } from "@/components/ui/button";
import type { ClipEdits } from "@/hooks/useClipEdits";
import type { SceneTracker } from "@/hooks/useSceneTrack";
import { formatTimecode } from "@/lib/format";
import { pickSeed, type FramePoint as Point } from "@/lib/trackSeed";

interface PlayerTrackPickProps {
  clip: Clip;
  edits: ClipEdits;
  /** The track scene at the playhead. */
  scene: SceneReframe;
  tracker: SceneTracker;
  /** The playhead's source time in seconds. */
  time: number;
}

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
const percent = (value: number) => `${value * 100}%`;

/**
 * The subject picker of a track scene: the source frame at the playhead,
 * on which a click on the subject (or a box dragged around it) tracks it
 * through the scene (useSceneTrack), with the box tracked last outlined.
 */
export function PlayerTrackPick({
  clip,
  edits,
  scene,
  tracker,
  time,
}: PlayerTrackPickProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ from: Point; to: Point } | null>(null);
  const t = Math.min(scene.end, Math.max(scene.start, time));

  const at = (event: PointerEvent): Point | null => {
    const bounds = frameRef.current?.getBoundingClientRect();
    if (!bounds?.width || !bounds.height) return null;
    return {
      x: clamp01((event.clientX - bounds.left) / bounds.width),
      y: clamp01((event.clientY - bounds.top) / bounds.height),
    };
  };

  const down = (event: PointerEvent) => {
    const point = at(event);
    if (event.button !== 0 || !point || tracker.tracking) return;
    event.preventDefault();
    frameRef.current?.setPointerCapture?.(event.pointerId);
    setDrag({ from: point, to: point });
  };
  const move = (event: PointerEvent) => {
    const point = at(event);
    if (drag && point) setDrag({ ...drag, to: point });
  };
  const up = (event: PointerEvent) => {
    const bounds = frameRef.current?.getBoundingClientRect();
    const point = at(event) ?? drag?.to;
    if (drag && point && bounds) {
      tracker.track(pickSeed(drag.from, point, t, bounds));
    }
    setDrag(null);
  };

  const seed = scene.track_seed;
  const box = drag && {
    x: Math.min(drag.from.x, drag.to.x),
    y: Math.min(drag.from.y, drag.to.y),
    width: Math.abs(drag.to.x - drag.from.x),
    height: Math.abs(drag.to.y - drag.from.y),
  };

  return (
    <CropTrackGate clip={clip} edits={edits}>
      {(track) => (
        <div className="flex size-full flex-col items-center justify-center gap-3">
          <SourceFrame
            projectId={clip.project_id}
            time={time}
            frame={{ width: track.frame_width, height: track.frame_height }}
            frameRef={frameRef}
            role="application"
            aria-label="Pick the subject to track"
            className="cursor-crosshair"
            onPointerDown={down}
            onPointerMove={move}
            onPointerUp={up}
            onPointerCancel={() => setDrag(null)}
          >
            {seed && !box && seed.width > 0 && (
              <div
                aria-hidden
                className="pointer-events-none absolute border-2 border-dashed border-primary/70"
                style={{
                  left: percent(seed.x),
                  top: percent(seed.y),
                  width: percent(seed.width),
                  height: percent(seed.height),
                }}
              />
            )}
            {box && (
              <div
                aria-hidden
                className="pointer-events-none absolute border-2 border-primary bg-primary/10"
                style={{
                  left: percent(box.x),
                  top: percent(box.y),
                  width: percent(box.width),
                  height: percent(box.height),
                }}
              />
            )}
            {tracker.tracking && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/50 text-body text-white">
                <CircleNotchIcon className="size-6 animate-spin" aria-hidden />
                Tracking the subject…
              </div>
            )}
          </SourceFrame>
          <div className="flex items-center gap-2 text-caption text-muted-foreground">
            <span aria-live="polite">
              {`Click the subject at ${formatTimecode(t)}, or drag a box around it.`}
            </span>
            {scene.crop_keyframes.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="xs"
                disabled={tracker.tracking}
                onClick={() => tracker.setPicking(false)}
              >
                Cancel
              </Button>
            )}
          </div>
        </div>
      )}
    </CropTrackGate>
  );
}
