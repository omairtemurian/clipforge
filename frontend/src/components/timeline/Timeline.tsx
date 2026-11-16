import type { TrackItem, Word } from "@/api/types";
import { Track } from "@/components/timeline/Track";
import {
  dragSpan,
  layerLength,
  layerSnapTargets,
  moveSpan,
  placeItem,
  type ItemDrag,
  type LayerName,
  type LayerTracks,
} from "@/lib/layers";
import { mediaItem } from "@/lib/newLayerItems";
import { wordEdges } from "@/lib/segments";
import {
  previewToSource,
  sourceToPreview,
  spanPercent,
  type ClipRange,
  type CutRange,
} from "@/lib/timeline";

export interface TimelineProps {
  /** The layer tracks to draw, top to bottom. */
  names: LayerName[];
  layers: LayerTracks;
  /** The part of the source the timeline shows. */
  view: ClipRange;
  /** The clip as edited and its cut ranges (layer items are timed in
   * seconds of the clip after its cuts). */
  clip: ClipRange;
  cuts: CutRange[];
  /** The kept parts of the clip (segments), in source seconds. */
  parts: CutRange[];
  /** The source time the player is at. */
  playhead: number;
  /** Snapping on: words are the transcript's, which items snap to too. */
  snap: boolean;
  words: Word[];
  /** How close (seconds) a dragged edge snaps to a target. */
  tolerance: number;
  /** The source time under the pointer at clientX. */
  timeAt: (clientX: number) => number;
  /** New items of a track; changes of one drag share gesture. */
  onChange: (name: LayerName, items: TrackItem[], gesture?: number) => void;
  /** The id of the selected item, and selecting one. */
  selectedItem: string | null;
  onSelectItem: (id: string) => void;
  onSeek: (t: number) => void;
}

/**
 * The layer tracks of the clip's timeline (B-roll, overlays, text, music,
 * SFX, voiceover; the video row is TimelineTracks'), drawn over the same
 * window of the source as the video row: each item lies where the clip
 * shows it (its clip time mapped past the cuts). Pressing an item selects
 * it; dragging it moves or
 * trims it inside the clip; with snapping on, its edges snap to word
 * edges, segment edges, the playhead and the other layers' items.
 * Dropping a media library file on a track that holds it adds an item
 * there from the clip time under the pointer, selected.
 */
export function Timeline(props: TimelineProps) {
  const { names, layers, view, clip, cuts } = props;
  const length = layerLength(clip, cuts);
  const toClip = (clientX: number) =>
    sourceToPreview(props.timeAt(clientX), clip, cuts);
  const place = (item: TrackItem) =>
    spanPercent(
      previewToSource(item.start, clip, cuts),
      previewToSource(item.end, clip, cuts),
      view,
    );
  const targets = (item: TrackItem) =>
    props.snap
      ? layerSnapTargets({
          clip,
          cuts,
          words: wordEdges(props.words),
          parts: props.parts,
          playhead: props.playhead,
          layers,
          except: item.id,
        })
      : [];

  return (
    <>
      {names.map((name) => {
        const onDrag = (
          item: TrackItem,
          drag: ItemDrag,
          pointer: number,
          grab: number,
          gesture: number,
        ) => {
          const span = dragSpan(item, {
            drag,
            pointer,
            grab,
            targets: targets(item),
            tolerance: props.tolerance,
            length,
          });
          props.onChange(name, placeItem(layers[name], item.id, span), gesture);
        };
        const onNudge = (item: TrackItem, seconds: number) => {
          const span = moveSpan(item, item.start + seconds, length);
          props.onChange(name, placeItem(layers[name], item.id, span));
        };
        return (
          <Track
            key={name}
            name={name}
            items={layers[name]}
            place={place}
            timeAt={toClip}
            onDrag={onDrag}
            onNudge={onNudge}
            selectedId={props.selectedItem}
            onSelect={(item) => props.onSelectItem(item.id)}
            onSeek={(clientX) => props.onSeek(props.timeAt(clientX))}
            onDropMedia={(clientX, media) => {
              const added = mediaItem(
                layers,
                name,
                media,
                toClip(clientX),
                length,
              );
              if (!added) return;
              props.onChange(name, [...layers[name], added]);
              props.onSelectItem(added.id);
            }}
          />
        );
      })}
    </>
  );
}
