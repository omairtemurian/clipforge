import { useState } from "react";
import {
  clamp,
  zoomBy,
  ZOOM_MAX,
  ZOOM_MIN,
  type CutRange,
} from "@/lib/timeline";

/** The editor timeline's view state: zoom, shown or hidden, snapping to
 * words, and the selected segment or layer item (one at most). */
export interface TimelineState {
  zoom: number;
  setZoom: (zoom: number) => void;
  /** Zoom steps steps in (positive) or out (negative). */
  zoomSteps: (steps: number) => void;
  hidden: boolean;
  toggleHidden: () => void;
  snap: boolean;
  toggleSnap: () => void;
  selected: CutRange | null;
  /** Select a segment (none: unselect), which unselects the item. */
  select: (part: CutRange | null) => void;
  /** The id of the selected layer item. */
  item: string | null;
  /** Select a layer item (none: unselect), which unselects the segment. */
  selectItem: (id: string | null) => void;
}

/** The state of the editor's timeline; it starts unzoomed, shown, with
 * snapping on and nothing selected. */
export function useTimelineState(): TimelineState {
  const [zoom, setZoomValue] = useState(ZOOM_MIN);
  const [hidden, setHidden] = useState(false);
  const [snap, setSnap] = useState(true);
  const [selected, setSelected] = useState<CutRange | null>(null);
  const [item, setItem] = useState<string | null>(null);
  return {
    zoom,
    setZoom: (value) => setZoomValue(clamp(value, ZOOM_MIN, ZOOM_MAX)),
    zoomSteps: (steps) => setZoomValue((value) => zoomBy(value, steps)),
    hidden,
    toggleHidden: () => setHidden((value) => !value),
    snap,
    toggleSnap: () => setSnap((value) => !value),
    selected,
    select: (part) => {
      setSelected(part);
      if (part) setItem(null);
    },
    item,
    selectItem: (id) => {
      setItem(id);
      if (id) setSelected(null);
    },
  };
}
