import { useClipTranscript } from "@/api/clips";
import type { Clip } from "@/api/types";
import { ClipDetails } from "@/components/editor/ClipDetails";
import { TranscriptEditor } from "@/components/editor/TranscriptEditor";
import type { ClipEdits } from "@/hooks/useClipEdits";
import type { WordSelection } from "@/lib/cuts";
import type { ClipRange } from "@/lib/timeline";
import { Skeleton } from "@/components/ui/skeleton";

interface TranscriptColumnProps {
  clip: Clip;
  edits: ClipEdits;
  bounds: ClipRange;
  selection: WordSelection | null;
  onSelect: (selection: WordSelection | null) => void;
  onSeek: (t: number) => void;
  onDelete: () => void;
  playhead: number;
  playing: boolean;
}

function TranscriptSkeleton() {
  return (
    <div aria-label="Loading transcript" className="flex flex-col gap-3">
      {[92, 80, 96, 64, 88].map((width) => (
        <Skeleton key={width} className="h-4" style={{ width: `${width}%` }} />
      ))}
    </div>
  );
}

/**
 * The left column of the editor: the edited clip's In/Out/Length/Cuts and
 * hook, and the transcript editor once the clip's words are loaded. It
 * fills the column; only the transcript scrolls.
 */
export function TranscriptColumn({ clip, ...editor }: TranscriptColumnProps) {
  const transcript = useClipTranscript(clip.id);
  const { range, cuts, texts } = editor.edits;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-6">
      <ClipDetails range={range} cuts={cuts} hook={texts.hook_text} />
      {transcript.isPending && <TranscriptSkeleton />}
      {transcript.isError && (
        <p role="alert" className="text-body text-muted-foreground">
          The transcript could not be loaded.
        </p>
      )}
      {transcript.data && (
        <TranscriptEditor
          clipId={clip.id}
          projectId={clip.project_id}
          words={transcript.data}
          {...editor}
        />
      )}
    </div>
  );
}
