import { PlusIcon, TextTIcon, TrashIcon } from "@phosphor-icons/react";
import type { TextProps, TrackItem } from "@/api/types";
import { LayerTextField } from "@/components/editor/LayerTextField";
import { TextLayerFields } from "@/components/editor/TextLayerFields";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PanelGroup } from "@/components/ui/panel";
import { useGesture } from "@/hooks/useGesture";
import { formatTimecode } from "@/lib/format";
import type { LayerTracks } from "@/lib/layers";
import { removeItem } from "@/lib/layerItems";
import { MAX_TEXT_LAYERS, textItem } from "@/lib/newLayerItems";
import { textProps, withProps } from "@/lib/overlays";
import { choiceClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

export interface TextOverlayPanelProps {
  /** The clip's layer tracks as edited. */
  layers: LayerTracks;
  /** The playhead in clip time (seconds after the cuts). */
  at: number;
  /** The clip time layer items must end by. */
  length: number;
  /** New items of the text track; changes of one gesture undo at once. */
  onChange: (items: TrackItem[], gesture?: number) => void;
  /** The selected layer item (the timeline's), and selecting one. */
  selectedItem: string | null;
  onSelectItem: (id: string) => void;
}

/**
 * The editor's Text layers panel (SPEC-v2 3.5): the clip's text overlays
 * (the text track, at most MAX_TEXT_LAYERS) in time order. "Add text" puts
 * a new one at the playhead for 3 s; choosing one selects it on the
 * timeline (and selecting one there opens it here) to change its text,
 * font, size, colors, outline, box, position and in/out animations, or to
 * delete it. Its timing changes on the timeline's Text track.
 */
export function TextOverlayPanel({
  layers,
  at,
  length,
  onChange,
  selectedItem,
  onSelectItem,
}: TextOverlayPanelProps) {
  const gesture = useGesture();
  const items = layers.text;
  const sorted = [...items].sort((a, b) => a.start - b.start);
  const open = items.find((item) => item.id === selectedItem);
  const full = items.length >= MAX_TEXT_LAYERS;

  const add = () => {
    const item = textItem(layers, "Your text", at, length);
    if (!item) return;
    onChange([...items, item]);
    onSelectItem(item.id);
  };
  const change = (changes: Partial<TextProps>, dragged?: boolean) => {
    if (!open) return;
    onChange(
      withProps(items, open.id, changes),
      dragged ? gesture.current() : undefined,
    );
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-caption text-muted-foreground">
          {items.length} of {MAX_TEXT_LAYERS} text layers
        </p>
        <Button
          type="button"
          variant="outline"
          disabled={full || length <= 0}
          title={full ? `A clip has at most ${MAX_TEXT_LAYERS}` : undefined}
          onClick={add}
        >
          <PlusIcon aria-hidden />
          Add text
        </Button>
      </div>
      {items.length === 0 ? (
        <EmptyState icon={TextTIcon} title="No text layers" className="py-8">
          Add a title, a label or a big number over the video.
        </EmptyState>
      ) : (
        <ul aria-label="Text layers" className="flex flex-col gap-2">
          {sorted.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-pressed={item.id === open?.id}
                onClick={() => onSelectItem(item.id)}
                className={cn(
                  choiceClass(item.id === open?.id),
                  "flex w-full cursor-pointer items-center justify-between gap-3",
                )}
              >
                <span className="truncate text-body">
                  {textProps(item).text}
                </span>
                <span className="shrink-0 text-micro text-muted-foreground tabular-nums">
                  {formatTimecode(item.start)} – {formatTimecode(item.end)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <PanelGroup title="Selected text">
          <LayerTextField
            key={open.id}
            item={open}
            onText={(text) => change({ text })}
          />
          <TextLayerFields
            props={textProps(open)}
            onChange={change}
            onStart={gesture.begin}
          />
          <Button
            type="button"
            variant="outline"
            onClick={() => onChange(removeItem(items, open.id))}
          >
            <TrashIcon aria-hidden />
            Delete text layer
          </Button>
        </PanelGroup>
      )}
    </div>
  );
}
