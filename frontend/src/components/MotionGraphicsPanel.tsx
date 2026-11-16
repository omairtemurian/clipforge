import { SparkleIcon, TextTIcon, TrashIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useGraphicsOps, type GraphicsOp } from "@/api/clipGraphics";
import type { Clip, TextProps } from "@/api/types";
import { LayerTextField } from "@/components/editor/LayerTextField";
import { TextLayerFields } from "@/components/editor/TextLayerFields";
import { Field } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { NativeSelect } from "@/components/ui/native-select";
import { PanelGroup } from "@/components/ui/panel";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { useGesture } from "@/hooks/useGesture";
import { formatTimecode } from "@/lib/format";
import { removeItem } from "@/lib/layerItems";
import { textProps, withProps } from "@/lib/overlays";
import { choiceClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";
import {
  MOTION_GRAPHICS_DEFAULT,
  MOTION_GRAPHICS_MAX,
  motionGraphics,
} from "@/lib/viralHooks";

interface MotionGraphicsPanelProps {
  clip: Clip;
  edits: ClipEdits;
  /** A save or render is under way. */
  busy: boolean;
  /** The timeline's selected layer item, and selecting one. */
  selectedItem: string | null;
  onSelectItem: (id: string) => void;
}

const COUNTS = Array.from({ length: MOTION_GRAPHICS_MAX }, (_, i) => i + 1);

/**
 * The editor's Graphics panel (SPEC-v2 3.5): motion graphics (lower-thirds
 * for names and key phrases, number callouts for numbers and dates) that
 * the AI picks from what the clip says and puts on the text track at the
 * moment they are said. Finding them replaces the earlier ones and acts on
 * the saved clip, so it waits for unsaved changes (autosave saves them).
 * Each graphic is a text item: pick one to change its text and look (its
 * timing on the timeline) or delete it.
 */
export function MotionGraphicsPanel({
  clip,
  edits,
  busy,
  selectedItem,
  onSelectItem,
}: MotionGraphicsPanelProps) {
  const ops = useGraphicsOps(clip.id);
  const gesture = useGesture();
  const [count, setCount] = useState(MOTION_GRAPHICS_DEFAULT);
  const waiting = edits.dirty || busy;
  const locked = waiting || ops.isPending;
  const items = edits.layers.text;
  const graphics = motionGraphics(items);
  const open = graphics.find((item) => item.id === selectedItem);

  const run = async (op: GraphicsOp) => {
    try {
      edits.reset(await ops.mutateAsync(op));
    } catch {
      // apiFetch has shown the error
    }
  };
  const change = (changes: Partial<TextProps>, dragged?: boolean) => {
    if (!open) return;
    edits.setLayer(
      "text",
      withProps(items, open.id, changes),
      dragged ? gesture.current() : undefined,
    );
  };

  return (
    <div className="flex flex-col gap-5">
      {waiting && (
        <p role="status" className="text-caption text-muted-foreground">
          Edits wait until your changes are saved.
        </p>
      )}
      <PanelGroup title="Find graphics">
        <Field label="Most graphics">
          <NativeSelect
            block
            aria-label="Most graphics"
            value={count}
            onChange={(event) => setCount(Number(event.target.value))}
          >
            {COUNTS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={locked}
            onClick={() => void run({ type: "find", maxItems: count })}
          >
            <SparkleIcon />
            {graphics.length > 0 ? "Find new graphics" : "Find graphics"}
          </Button>
          {graphics.length > 0 && (
            <Button
              variant="ghost"
              disabled={locked}
              onClick={() => void run({ type: "remove" })}
            >
              <TrashIcon />
              Remove all
            </Button>
          )}
        </div>
        {ops.isPending && (
          <p role="status" className="text-caption text-muted-foreground">
            Looking for names, numbers and dates…
          </p>
        )}
      </PanelGroup>
      {graphics.length === 0 ? (
        <EmptyState
          icon={TextTIcon}
          title="No motion graphics"
          className="py-8"
        >
          Find the names, numbers and dates that the clip says.
        </EmptyState>
      ) : (
        <ul aria-label="Motion graphics" className="flex flex-col gap-2">
          {graphics.map((item) => (
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
                  {textProps(item).text.replace(/\n/g, " · ")}
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
        <PanelGroup title="Selected graphic">
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
            variant="outline"
            onClick={() => edits.setLayer("text", removeItem(items, open.id))}
          >
            <TrashIcon />
            Delete graphic
          </Button>
        </PanelGroup>
      )}
    </div>
  );
}
