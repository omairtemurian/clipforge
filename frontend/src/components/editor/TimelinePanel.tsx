import { useFilmstrip, useWaveform } from "@/api/timelineAssets";
import { SegmentOverride } from "@/components/editor/SegmentOverride";
import { TimelineControls } from "@/components/editor/TimelineControls";
import {
  TimelineTracks,
  type TimelineTracksProps,
} from "@/components/editor/TimelineTracks";
import type { PreviewPlayer } from "@/hooks/usePreviewPlayer";
import type { TimelineState } from "@/hooks/useTimelineState";
import type { SceneChoice } from "@/lib/scenes";
import { sourceToPreview, type ClipRange } from "@/lib/timeline";

type TrackProps = Omit<TimelineTracksProps, "zoom" | "strip" | "wave" | "snap">;

interface TimelinePanelProps extends TrackProps {
  clipId: number;
  /** The saved clip, whose surroundings the filmstrip and waveform show. */
  saved: ClipRange;
  timeline: TimelineState;
  player: PreviewPlayer;
  onSplit: () => void;
  canDelete: boolean;
  onDelete: () => void;
  onSkip: (direction: -1 | 1) => void;
  /** How the selected segment is framed and the choice of its override
   * (none while no segment is selected). */
  override?: { value: SceneChoice; onChoose: (choice: SceneChoice) => void };
}

/**
 * The bottom of the editor: the control row over the timeline's rows
 * (ruler, segments, layer tracks, filmstrip with the clip box, waveform)
 * and the selected
 * segment's layout override, which "Hide timeline" folds away. Times in the control row are clip times (cuts left
 * out).
 */
export function TimelinePanel({
  clipId,
  saved,
  timeline,
  player,
  onSplit,
  canDelete,
  onDelete,
  onSkip,
  override,
  ...tracks
}: TimelinePanelProps) {
  const strip = useFilmstrip(clipId, saved).data;
  const wave = useWaveform(clipId, saved).data;
  const { clip, cuts, playhead } = tracks;
  const total = sourceToPreview(clip.end, clip, cuts);
  const current = sourceToPreview(playhead, clip, cuts);

  return (
    <footer
      aria-label="Timeline panel"
      className="shrink-0 border-t border-border px-6 pt-2 pb-4"
    >
      <TimelineControls
        timeline={timeline}
        playing={player.playing}
        onTogglePlay={player.toggle}
        current={current}
        total={total}
        onSplit={onSplit}
        canDelete={canDelete}
        onDelete={onDelete}
        onSkip={onSkip}
        rate={player.rate}
        onRate={player.setRate}
      />
      {!timeline.hidden && (
        <div className="mt-1">
          <TimelineTracks
            {...tracks}
            zoom={timeline.zoom}
            snap={timeline.snap}
            strip={strip}
            wave={wave}
          />
          {override && (
            <SegmentOverride
              value={override.value}
              onChoose={override.onChoose}
            />
          )}
        </div>
      )}
    </footer>
  );
}
