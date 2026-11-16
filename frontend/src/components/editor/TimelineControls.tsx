import {
  CaretLineDownIcon,
  CaretLineUpIcon,
  MagnetIcon,
  MagnifyingGlassMinusIcon,
  MagnifyingGlassPlusIcon,
  PauseIcon,
  PlayIcon,
  SkipBackIcon,
  SkipForwardIcon,
  SquareSplitHorizontalIcon,
  TrashIcon,
} from "@phosphor-icons/react";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import { Slider } from "radix-ui";
import { NativeSelect } from "@/components/ui/native-select";
import type { TimelineState } from "@/hooks/useTimelineState";
import { formatTimecode } from "@/lib/format";
import { PLAYBACK_RATES, rateLabel } from "@/lib/playbackRate";
import { ZOOM_MAX, ZOOM_MIN } from "@/lib/timeline";
import { cn } from "@/lib/utils";

const ICON_BUTTON =
  "inline-flex h-8 items-center justify-center gap-2 rounded-lg px-2 text-body text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-40 aria-pressed:bg-muted aria-pressed:text-foreground";

function ControlButton({
  label,
  icon: Icon,
  onClick,
  text,
  pressed,
  disabled,
  className,
}: {
  label: string;
  icon: PhosphorIcon;
  onClick: () => void;
  text?: string;
  pressed?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={cn(ICON_BUTTON, className)}
    >
      <Icon className="size-4" aria-hidden />
      {text}
    </button>
  );
}

interface TimelineControlsProps {
  timeline: TimelineState;
  playing: boolean;
  onTogglePlay: () => void;
  /** Clip time (cuts left out) of the playhead, and the clip's length. */
  current: number;
  total: number;
  onSplit: () => void;
  canDelete: boolean;
  onDelete: () => void;
  onSkip: (direction: -1 | 1) => void;
  /** The playback speed and changing it. */
  rate: number;
  onRate: (rate: number) => void;
}

/**
 * The timeline's control row: hide/show, split at the playhead, delete the
 * selection, snapping on/off (left); skip back, play/pause, skip forward,
 * "current / total" and the playback speed (center); the zoom slider with
 * -/+ (right).
 */
export function TimelineControls({
  timeline,
  playing,
  onTogglePlay,
  current,
  total,
  onSplit,
  canDelete,
  onDelete,
  onSkip,
  rate,
  onRate,
}: TimelineControlsProps) {
  const PlayPause = playing ? PauseIcon : PlayIcon;
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
      <div className="flex items-center gap-1">
        <ControlButton
          label={timeline.hidden ? "Show timeline" : "Hide timeline"}
          icon={timeline.hidden ? CaretLineUpIcon : CaretLineDownIcon}
          text={timeline.hidden ? "Show timeline" : "Hide timeline"}
          onClick={timeline.toggleHidden}
          className="mr-2"
        />
        <ControlButton
          label="Split at playhead (S)"
          icon={SquareSplitHorizontalIcon}
          onClick={onSplit}
        />
        <ControlButton
          label="Delete selection (Delete)"
          icon={TrashIcon}
          onClick={onDelete}
          disabled={!canDelete}
        />
        <ControlButton
          label="Snap to words, segments, playhead and layers"
          icon={MagnetIcon}
          onClick={timeline.toggleSnap}
          pressed={timeline.snap}
        />
      </div>
      <div className="flex items-center gap-2">
        <ControlButton
          label="Skip back"
          icon={SkipBackIcon}
          onClick={() => onSkip(-1)}
        />
        <button
          type="button"
          aria-label={playing ? "Pause" : "Play"}
          onClick={onTogglePlay}
          className="inline-flex size-9 items-center justify-center rounded-full text-foreground transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <PlayPause weight="fill" className="size-5" aria-hidden />
        </button>
        <ControlButton
          label="Skip forward"
          icon={SkipForwardIcon}
          onClick={() => onSkip(1)}
        />
        <p className="ml-3 text-body tabular-nums">
          <span aria-label="Current time">{formatTimecode(current)}</span>
          <span className="mx-2 text-muted-foreground">/</span>
          <span aria-label="Clip length" className="text-muted-foreground">
            {formatTimecode(total)}
          </span>
        </p>
        <NativeSelect
          aria-label="Playback speed"
          title="Playback speed (< / >)"
          value={String(rate)}
          onChange={(event) => onRate(Number(event.target.value))}
          className="ml-2 h-8 text-body"
        >
          {PLAYBACK_RATES.map((option) => (
            <option key={option} value={option}>
              {rateLabel(option)}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div className="flex items-center justify-end gap-1">
        <ControlButton
          label="Zoom out (-)"
          icon={MagnifyingGlassMinusIcon}
          onClick={() => timeline.zoomSteps(-1)}
          disabled={timeline.zoom <= ZOOM_MIN}
        />
        <Slider.Root
          min={ZOOM_MIN}
          max={ZOOM_MAX}
          step={0.1}
          value={[timeline.zoom]}
          onValueChange={([zoom]) => timeline.setZoom(zoom)}
          className="relative flex h-5 w-32 touch-none items-center select-none"
        >
          <Slider.Track className="relative h-1 grow overflow-hidden rounded-full bg-muted">
            <Slider.Range className="absolute h-full bg-muted-foreground/60" />
          </Slider.Track>
          <Slider.Thumb
            aria-label="Zoom"
            className="block size-3.5 rounded-full bg-foreground shadow outline-none focus-visible:ring-4 focus-visible:ring-ring/40"
          />
        </Slider.Root>
        <ControlButton
          label="Zoom in (+)"
          icon={MagnifyingGlassPlusIcon}
          onClick={() => timeline.zoomSteps(1)}
          disabled={timeline.zoom >= ZOOM_MAX}
        />
      </div>
    </div>
  );
}
