import { EraserIcon, SparkleIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useHeadlineOps } from "@/api/clipGraphics";
import type { Clip } from "@/api/types";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { PanelGroup } from "@/components/ui/panel";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { cn } from "@/lib/utils";
import { HOOK_TEXT_MAX, hasHeadlineItem } from "@/lib/viralHooks";

interface HeadlineGroupProps {
  clip: Clip;
  edits: ClipEdits;
  /** Edits of the saved clip must wait (unsaved changes, a save or render). */
  locked: boolean;
}

/**
 * The headline of the clip (SPEC-v2 3.5): the line over its first seconds,
 * in the project's brand style. Type one and set it, or have the AI write
 * (and write again) one; removing it takes its text item off the timeline
 * too. Once it is on the timeline, its look is changed like any text layer.
 */
export function HeadlineGroup({ clip, edits, locked }: HeadlineGroupProps) {
  const ops = useHeadlineOps(clip.id);
  const [typed, setTyped] = useState<string | null>(null);
  const saved = clip.hook_text;
  const text = typed ?? saved;
  const has = saved !== "" || hasHeadlineItem(clip.tracks.text);
  const busy = locked || ops.isPending;

  const run = async (op: Parameters<typeof ops.mutateAsync>[0]) => {
    try {
      edits.reset(await ops.mutateAsync(op));
      setTyped(null);
    } catch {
      // apiFetch has shown the error
    }
  };

  return (
    <PanelGroup title="Headline">
      <Field label="Headline text" htmlFor="headline-text">
        <input
          id="headline-text"
          value={text}
          maxLength={HOOK_TEXT_MAX}
          onChange={(event) => setTyped(event.target.value)}
          className={cn(INPUT, "h-9")}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={busy || text.trim() === "" || text.trim() === saved}
          onClick={() => void run({ type: "set", text: text.trim() })}
        >
          Set headline
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => void run({ type: "set", text: null })}
        >
          <SparkleIcon />
          {has ? "Write a new headline" : "Write with AI"}
        </Button>
        {has && (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => void run({ type: "remove" })}
          >
            <EraserIcon />
            Remove headline
          </Button>
        )}
      </div>
      {ops.isPending && (
        <p role="status" className="text-caption text-muted-foreground">
          Writing…
        </p>
      )}
      {!has && (
        <p className="text-caption text-muted-foreground">
          The clip has no headline.
        </p>
      )}
    </PanelGroup>
  );
}
