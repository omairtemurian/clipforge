import {
  ArrowCounterClockwiseIcon,
  TreeStructureIcon,
} from "@phosphor-icons/react";
import { useState } from "react";
import { ChaptersPanel } from "@/components/ChaptersPanel";
import { RepromptDialog } from "@/components/RepromptDialog";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import type { Project } from "@/api/types";

interface GalleryActionsProps {
  project: Project;
  /** The result set the grid shows. */
  resultSet: number;
  onResultSetChange: (resultSet: number) => void;
}

/** "Reprompt", "Topics" and, once a reprompt made more, the result set to show. */
export function GalleryActions({
  project,
  resultSet,
  onResultSetChange,
}: GalleryActionsProps) {
  const [dialog, setDialog] = useState<"reprompt" | "topics" | null>(null);
  const sets = Array.from({ length: project.result_set }, (_, i) => i + 1);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" onClick={() => setDialog("reprompt")}>
        <ArrowCounterClockwiseIcon aria-hidden />
        Reprompt
      </Button>
      <Button variant="outline" onClick={() => setDialog("topics")}>
        <TreeStructureIcon aria-hidden />
        Topics
      </Button>
      {sets.length > 1 && (
        <label className="flex items-center gap-2 text-body text-muted-foreground">
          Result
          <NativeSelect
            value={resultSet}
            onChange={(event) => onResultSetChange(Number(event.target.value))}
          >
            {sets.map((set) => (
              <option key={set} value={set}>
                {set === project.result_set ? `${set} (latest)` : set}
              </option>
            ))}
          </NativeSelect>
        </label>
      )}
      {dialog === "reprompt" && (
        <RepromptDialog project={project} onClose={() => setDialog(null)} />
      )}
      {dialog === "topics" && (
        <ChaptersPanel project={project} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}
