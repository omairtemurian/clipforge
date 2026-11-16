import { CircleNotchIcon, SwapIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useReplaceEverywhere } from "@/api/captions";
import type { ReplaceResult } from "@/api/types";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ReplaceEverywhereProps {
  projectId: number;
  /** Why it cannot run now (unsaved edits), or null. */
  blocked: string | null;
  /** Called once the project's clips changed. */
  onReplaced: () => void;
}

function summary({ transcript_matches, clips_changed }: ReplaceResult) {
  const places = transcript_matches === 1 ? "place" : "places";
  const clips = clips_changed === 1 ? "clip" : "clips";
  return `Replaced ${transcript_matches} ${places} in the transcript and changed ${clips_changed} ${clips}.`;
}

/**
 * "Replace everywhere": changes some words (whole words, any case) into
 * others in the project's transcript and every clip of it; "Remember" also
 * keeps it as a vocabulary correction for later transcripts.
 */
export function ReplaceEverywhere({
  projectId,
  blocked,
  onReplaced,
}: ReplaceEverywhereProps) {
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [remember, setRemember] = useState(true);
  const [done, setDone] = useState<string | null>(null);
  const run = useReplaceEverywhere(projectId, (result) => {
    setDone(summary(result));
    onReplaced();
  });
  const ready = find.trim() !== "" && replace.trim() !== "";

  return (
    <form
      aria-label="Replace everywhere"
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        setDone(null);
        run.mutate({ find, replace, remember });
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Find" htmlFor="replace-find">
          <input
            id="replace-find"
            value={find}
            onChange={(event) => setFind(event.target.value)}
            placeholder="clip forge"
            className={cn(INPUT, "h-9")}
          />
        </Field>
        <Field label="Replace with" htmlFor="replace-with">
          <input
            id="replace-with"
            value={replace}
            onChange={(event) => setReplace(event.target.value)}
            placeholder="ClipForge"
            className={cn(INPUT, "h-9")}
          />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-body">
        <input
          type="checkbox"
          checked={remember}
          onChange={(event) => setRemember(event.target.checked)}
          className="size-4 accent-primary"
        />
        Remember as a correction for new transcripts
      </label>
      <div className="flex items-center justify-between gap-3">
        <p className="text-caption text-muted-foreground" role="status">
          {blocked ?? done ?? ""}
        </p>
        <Button
          type="submit"
          variant="secondary"
          disabled={!ready || blocked !== null || run.isPending}
        >
          {run.isPending ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <SwapIcon aria-hidden />
          )}
          Replace everywhere
        </Button>
      </div>
    </form>
  );
}
