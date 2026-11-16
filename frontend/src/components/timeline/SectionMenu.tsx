import {
  CopyIcon,
  ScissorsIcon,
  SquareSplitHorizontalIcon,
} from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCopyClip, useSectionOps, type SectionOp } from "@/api/clipSections";
import type { Clip } from "@/api/types";
import { SectionList } from "@/components/timeline/SectionList";
import { SectionPicker } from "@/components/timeline/SectionPicker";
import { Button } from "@/components/ui/button";
import { PanelGroup } from "@/components/ui/panel";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { splittableSection } from "@/lib/sections";
import { toast } from "@/lib/toast";

interface SectionMenuProps {
  clip: Clip;
  edits: ClipEdits;
  /** The playhead, in source seconds (where the splits are made). */
  playhead: number;
  /** A save or render is under way. */
  busy: boolean;
}

/**
 * The editor's Sections panel (SPEC-v2 3.5): the clip's sections in play
 * order (drag to rearrange, delete), the source's transcript lines to add
 * as sections, and at the playhead: split the section in two, split the
 * clip into two clips (the second is a new clip) or duplicate the clip.
 * The edits act on the saved clip, so they wait for unsaved changes
 * (autosave saves them); the clip that an edit answers replaces the
 * editor's.
 */
export function SectionMenu({ clip, edits, playhead, busy }: SectionMenuProps) {
  const ops = useSectionOps(clip.id);
  const copy = useCopyClip(clip.id);
  const [made, setMade] = useState<Clip | null>(null);
  const waiting = edits.dirty || busy;
  const locked = waiting || ops.isPending || copy.isPending;
  const sections = clip.segments;
  const canSplit = splittableSection(sections, playhead) !== undefined;

  const edit = async (op: SectionOp) => {
    try {
      edits.reset(await ops.mutateAsync(op));
    } catch {
      // apiFetch has shown the error
    }
  };
  const copied = async (op: Parameters<typeof copy.mutateAsync>[0]) => {
    try {
      const { made: next, first } = await copy.mutateAsync(op);
      if (first) edits.reset(first);
      setMade(next);
      toast.success(
        op.type === "split" ? "Split into two clips." : "Duplicated the clip.",
      );
    } catch {
      // apiFetch has shown the error
    }
  };

  return (
    <>
      {waiting && (
        <p role="status" className="text-caption text-muted-foreground">
          Edits wait until your changes are saved.
        </p>
      )}
      <PanelGroup title="Sections">
        <SectionList
          sections={sections}
          locked={locked}
          onReorder={(order) => void edit({ type: "reorder", order })}
          onDelete={(index) => void edit({ type: "delete", index })}
        />
      </PanelGroup>
      <PanelGroup title="Add a section">
        <SectionPicker
          projectId={clip.project_id}
          sections={sections}
          locked={locked}
          onAdd={(start, end) => void edit({ type: "add", start, end })}
        />
      </PanelGroup>
      <PanelGroup title="At the playhead">
        <div className="flex flex-col items-start gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={locked || !canSplit}
            onClick={() => void edit({ type: "split", at: playhead })}
          >
            <ScissorsIcon /> Split section in two
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={locked || !canSplit}
            onClick={() => void copied({ type: "split", at: playhead })}
          >
            <SquareSplitHorizontalIcon /> Split into two clips
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={locked}
            onClick={() => void copied({ type: "duplicate" })}
          >
            <CopyIcon /> Duplicate clip
          </Button>
        </div>
        {made && (
          <p className="text-caption text-muted-foreground">
            New clip:{" "}
            <Link
              to={`/clips/${made.id}`}
              className="text-primary-ink underline-offset-4 hover:underline"
            >
              {made.title}
            </Link>
          </p>
        )}
      </PanelGroup>
    </>
  );
}
