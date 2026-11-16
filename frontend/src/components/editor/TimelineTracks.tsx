import { useEffect, useLayoutEffect, useRef } from "react";
import type { FilmstripData } from "@/api/timelineAssets";
import type { Waveform, Word } from "@/api/types";
import { TimelineFilmstrip } from "@/components/editor/TimelineFilmstrip";
import { TimelineHandle } from "@/components/editor/TimelineHandle";
import {
  TimelineKeyframes,
  type KeyframeRowProps,
} from "@/components/editor/TimelineKeyframes";
import { TimelineRuler } from "@/components/editor/TimelineRuler";
import { TimelineSegments } from "@/components/editor/TimelineSegments";
import { TimelineWaveform } from "@/components/editor/TimelineWaveform";
import { Timeline, type TimelineProps } from "@/components/timeline/Timeline";
import {
  AUDIO_ROW,
  TrackLabels,
  VIDEO_ROW,
} from "@/components/timeline/TrackLabels";
import { useDrag } from "@/hooks/useDrag";
import { useElementWidth } from "@/hooks/useElementWidth";
import { formatTimecode } from "@/lib/format";
import type { LayerName, LayerTracks } from "@/lib/layers";
import { snapToWords } from "@/lib/segments";
import {
  clamp,
  moveHandle,
  pxToTime,
  spanPercent,
  zoomScroll,
  type ClipRange,
  type CutRange,
  type Handle,
} from "@/lib/timeline";
import { cn } from "@/lib/utils";

/** How close (px) a dragged handle snaps to a word's edge (keys move it
 * exactly). */
const SNAP_PX = 8;
const VIDEO_ROW_PX = 48;
/** The layer tracks drawn over the video row (top first) and under the
 * audio row: visual layers above the video, sound below. */
const ABOVE: LayerName[] = ["text", "overlays", "broll"];
const BELOW: LayerName[] = ["voiceover", "music", "sfx"];

export interface TimelineTracksProps {
  /** The part of the source the timeline shows. */
  view: ClipRange;
  /** The clip being edited; its handles move start and end. */
  clip: ClipRange;
  /** The clip's cut ranges, drawn as gaps. */
  cuts: CutRange[];
  splits: number[];
  /** The kept parts of the clip, as the segment row shows them. */
  parts: CutRange[];
  selected: CutRange | null;
  /** The label of a segment (how its scene is framed). */
  labelAt: (part: CutRange) => string;
  /** The keyframes row of a fixed scene, if the playhead is in one. */
  keyframes?: KeyframeRowProps;
  /** The source time the player is at. */
  playhead: number;
  zoom: number;
  /** Word edges handles snap to (empty: no snapping). */
  snapWords: Word[];
  /** Whether layer items snap (to words, segments, playhead, layers). */
  snap: boolean;
  /** The clip's layer tracks (all but video), as edited. */
  layers: LayerTracks;
  /** New items of a layer track; changes of one drag share gesture. */
  onLayerChange: TimelineProps["onChange"];
  /** The selected layer item's id, and selecting one. */
  selectedItem: string | null;
  onSelectItem: TimelineProps["onSelectItem"];
  strip?: FilmstripData;
  wave?: Waveform;
  /** A new span of the clip; changes of one drag share its gesture. */
  onChange: (clip: ClipRange, gesture?: number) => void;
  onSeek: (t: number) => void;
  onSelect: (part: CutRange) => void;
}

/** Shade over the source outside the clip, in a row. */
function Dim({ clip, view }: { clip: ClipRange; view: ClipRange }) {
  const before = spanPercent(view.start, clip.start, view);
  const after = spanPercent(clip.end, view.end, view);
  return (
    <>
      {[before, after].map((span, index) => (
        <div
          key={index}
          aria-hidden
          className="pointer-events-none absolute inset-y-0 bg-background/70"
          style={{ left: `${span.left}%`, width: `${span.width}%` }}
        />
      ))}
    </>
  );
}

/**
 * The editor timeline's rows over a window of the source, drawn zoom times
 * as wide (scrolling sideways): a ruler, the segment row, the keyframes of
 * a fixed scene at the playhead, the text, overlay and B-roll tracks
 * (components/timeline), the video row
 * (filmstrip, the clip as a bright box between two draggable handles,
 * cut ranges as gaps, split lines), the audio row (waveform) and the
 * voiceover, music and SFX tracks; outside the clip is dimmed. A gutter
 * on the left names the tracks. A playhead crosses all rows; pressing the ruler or
 * the video row seeks. Zooming keeps the playhead in place.
 */
export function TimelineTracks(props: TimelineTracksProps) {
  const { view, clip, cuts, splits, playhead, zoom, strip, wave } = props;
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const width = useElementWidth(contentRef);
  const span = view.end - view.start;
  const head = clamp(playhead, view.start, view.end);
  const anchor = span > 0 ? (head - view.start) / span : 0;
  const lastZoom = useRef(zoom);

  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || lastZoom.current === zoom) return;
    scroller.scrollLeft = zoomScroll({
      anchor,
      viewport: scroller.clientWidth,
      scroll: scroller.scrollLeft,
      from: lastZoom.current,
      to: zoom,
    });
    lastZoom.current = zoom;
  }, [zoom, anchor]);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || zoom <= 1) return;
    const x = anchor * scroller.scrollWidth;
    const { scrollLeft, clientWidth } = scroller;
    if (x < scrollLeft || x > scrollLeft + clientWidth) {
      scroller.scrollLeft = x - clientWidth * 0.1;
    }
  }, [anchor, zoom]);

  const timeAt = (clientX: number) => {
    const rect = contentRef.current?.getBoundingClientRect();
    if (!rect) return view.start;
    return pxToTime(clientX - rect.left, {
      from: view.start,
      to: view.end,
      width: rect.width,
    });
  };
  const scrub = useDrag((clientX) => props.onSeek(timeAt(clientX)));
  const knob = useDrag((clientX) => props.onSeek(timeAt(clientX)));
  const tolerance = width > 0 && span > 0 ? (SNAP_PX * span) / width : 0;
  const onMove = (handle: Handle, t: number, gesture?: number) => {
    const dragged = gesture !== undefined;
    const snapped = dragged ? snapToWords(t, props.snapWords, tolerance) : t;
    props.onChange(moveHandle(clip, handle, snapped, view), gesture);
  };
  const percent = (t: number) => `${spanPercent(view.start, t, view).width}%`;
  const box = spanPercent(clip.start, clip.end, view);
  const layerRows = (names: LayerName[]) => (
    <Timeline
      names={names}
      layers={props.layers}
      view={view}
      clip={clip}
      cuts={cuts}
      parts={props.parts}
      playhead={playhead}
      snap={props.snap}
      words={props.snapWords}
      tolerance={tolerance}
      timeAt={timeAt}
      onChange={props.onLayerChange}
      selectedItem={props.selectedItem}
      onSelectItem={props.onSelectItem}
      onSeek={props.onSeek}
    />
  );

  return (
    <div className="flex">
      <TrackLabels
        above={ABOVE}
        below={BELOW}
        keyframes={props.keyframes !== undefined}
      />
      <div
        ref={scrollRef}
        className="min-w-0 flex-1 overflow-x-auto overflow-y-hidden pb-1"
      >
        <div
          ref={contentRef}
          className="relative select-none"
          style={{ width: `${zoom * 100}%` }}
        >
          <TimelineRuler
            view={view}
            width={width}
            timeAt={timeAt}
            onSeek={props.onSeek}
          />
          <TimelineSegments
            view={view}
            parts={props.parts}
            selected={props.selected}
            labelAt={props.labelAt}
            width={width}
            onSelect={props.onSelect}
          />
          {props.keyframes && (
            <TimelineKeyframes
              {...props.keyframes}
              view={view}
              timeAt={timeAt}
            />
          )}
          {layerRows(ABOVE)}
          <div
            aria-label="Timeline"
            {...scrub}
            className={cn(
              "relative cursor-pointer touch-none overflow-hidden rounded-md bg-muted/50",
              VIDEO_ROW,
            )}
          >
            {strip && (
              <TimelineFilmstrip
                strip={strip}
                view={view}
                width={width}
                height={VIDEO_ROW_PX}
              />
            )}
            <Dim clip={clip} view={view} />
            {cuts.map(([from, to]) => {
              const gap = spanPercent(from, to, view);
              return (
                <div
                  key={`${from}-${to}`}
                  title={`Cut ${formatTimecode(from)} - ${formatTimecode(to)}`}
                  className="pointer-events-none absolute inset-y-0 z-[5] border-x border-border bg-background"
                  style={{ left: `${gap.left}%`, width: `${gap.width}%` }}
                />
              );
            })}
            {splits.map((t) => (
              <div
                key={t}
                data-testid="split"
                className="pointer-events-none absolute inset-y-0 z-[5] w-0.5 -translate-x-1/2 bg-foreground/80"
                style={{ left: percent(t) }}
              />
            ))}
            <div
              data-testid="clip-box"
              className="pointer-events-none absolute inset-y-0 z-[6] rounded-md border-2 border-primary"
              style={{ left: `${box.left}%`, width: `${box.width}%` }}
            >
              {(["start", "end"] as const).map((handle) => (
                <TimelineHandle
                  key={handle}
                  handle={handle}
                  clip={clip}
                  view={view}
                  onMove={onMove}
                  timeAt={timeAt}
                />
              ))}
            </div>
          </div>
          <div
            aria-label="Audio"
            className={cn(
              "relative overflow-hidden rounded-md bg-muted/30",
              AUDIO_ROW,
            )}
          >
            {wave && <TimelineWaveform wave={wave} view={view} width={width} />}
            <Dim clip={clip} view={view} />
          </div>
          {layerRows(BELOW)}
          <div
            aria-hidden
            data-testid="playhead"
            className="pointer-events-none absolute top-0 bottom-0 z-20 w-0.5 -translate-x-1/2 bg-foreground"
            style={{ left: percent(head) }}
          >
            <span
              {...knob}
              className="pointer-events-auto absolute -top-0.5 left-1/2 h-4 w-2.5 -translate-x-1/2 cursor-ew-resize touch-none rounded-sm bg-foreground"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
