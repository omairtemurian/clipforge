import { PlusIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useSourceTranscript } from "@/api/clipSections";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { formatTimecode } from "@/lib/format";
import { overlapsSection, pickerSegments } from "@/lib/sections";
import type { CutRange } from "@/lib/timeline";

interface SectionPickerProps {
  projectId: number;
  /** The clip's sections: a part that overlaps one cannot be added. */
  sections: CutRange[];
  locked: boolean;
  /** Add start-end of the source as a section that plays last. */
  onAdd: (start: number, end: number) => void;
}

/**
 * Parts of the source to add as sections: the lines of the source's
 * transcript (those near the clip first, narrowed by the search box), each
 * with an "Add" button; a line that overlaps a section is disabled.
 */
export function SectionPicker({
  projectId,
  sections,
  locked,
  onAdd,
}: SectionPickerProps) {
  const [query, setQuery] = useState("");
  const transcript = useSourceTranscript(projectId, true);
  const lines = pickerSegments(
    transcript.data?.segments ?? [],
    Math.min(...sections.map(([from]) => from)),
    query,
  );

  return (
    <div className="flex flex-col gap-2">
      <input
        type="search"
        aria-label="Search the source transcript"
        placeholder="Search the source transcript"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className={`${INPUT} h-8`}
      />
      {transcript.isPending && (
        <p className="text-caption text-muted-foreground">
          Loading the transcript…
        </p>
      )}
      {transcript.isError && (
        <p role="alert" className="text-caption text-destructive">
          The source transcript is not available.
        </p>
      )}
      {transcript.data && lines.length === 0 && (
        <p className="text-caption text-muted-foreground">
          No transcript line matches.
        </p>
      )}
      <ul
        aria-label="Source transcript"
        className="flex max-h-64 flex-col gap-1 overflow-y-auto"
      >
        {lines.map((line) => {
          const taken = overlapsSection(sections, line.start, line.end);
          return (
            <li key={line.id} className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-body">{line.text}</p>
                <p className="text-caption tabular-nums text-muted-foreground">
                  {formatTimecode(line.start)} – {formatTimecode(line.end)}
                  {taken && " · already in the clip"}
                </p>
              </div>
              <Button
                variant="outline"
                size="xs"
                aria-label={`Add section: ${line.text}`}
                disabled={locked || taken}
                onClick={() => onAdd(line.start, line.end)}
              >
                <PlusIcon /> Add
              </Button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
