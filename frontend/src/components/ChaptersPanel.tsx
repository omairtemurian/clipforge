import { CircleNotchIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Dialog } from "radix-ui";
import { useChapters, useClipByTopic, useMakeChapters } from "@/api/chapters";
import type { Chapter, Project } from "@/api/types";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import { choiceClass } from "@/lib/surfaces";

function ChapterRow({
  chapter,
  checked,
  onToggle,
}: {
  chapter: Chapter;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      <label
        className={cn(
          choiceClass(checked),
          "flex cursor-pointer items-start gap-3 focus-within:ring-3 focus-within:ring-ring/50",
        )}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          aria-label={chapter.title}
          className="mt-1 size-4 accent-primary"
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="truncate text-body font-medium">
              {chapter.title}
            </span>
            <span className="text-caption text-muted-foreground tabular-nums">
              {formatDuration(chapter.start)} – {formatDuration(chapter.end)}
            </span>
          </span>
          <span className="mt-0.5 block text-body text-muted-foreground">
            {chapter.summary}
          </span>
        </span>
      </label>
    </li>
  );
}

/**
 * A dialog with the topic chapters of a project: make them (the LLM divides
 * the transcript), choose some and clip only those, with an optional prompt.
 */
export function ChaptersPanel({
  project,
  onClose,
}: {
  project: Project;
  onClose: () => void;
}) {
  const chapters = useChapters(project.id);
  const make = useMakeChapters(project.id);
  const clip = useClipByTopic(project.id);
  const [chosen, setChosen] = useState<ReadonlySet<number>>(new Set());
  const [prompt, setPrompt] = useState("");
  const list = chapters.data ?? [];

  function toggle(id: number) {
    const next = new Set(chosen);
    if (!next.delete(id)) next.add(id);
    setChosen(next);
  }

  function submit() {
    const ids = list.map((item) => item.id).filter((id) => chosen.has(id));
    if (ids.length === 0) return;
    clip.mutate(
      { chapters: ids, prompt: prompt.trim() || null },
      { onSuccess: onClose },
    );
  }

  let body;
  if (chapters.isPending) {
    body = <p className="mt-4 text-body text-muted-foreground">Loading…</p>;
  } else if (list.length === 0) {
    body = (
      <p className="mt-4 text-body text-muted-foreground">
        No topics yet. ClipForge reads the transcript and divides it into
        topics.
      </p>
    );
  } else {
    body = (
      <>
        <ul className="mt-4 flex flex-col gap-2" aria-label="Topics">
          {list.map((item) => (
            <ChapterRow
              key={item.id}
              chapter={item}
              checked={chosen.has(item.id)}
              onToggle={() => toggle(item.id)}
            />
          ))}
        </ul>
        <label
          htmlFor="topic-prompt"
          className="mt-4 block text-body font-medium"
        >
          Find moments about (optional)
        </label>
        <input
          id="topic-prompt"
          value={prompt}
          maxLength={2000}
          placeholder="Leave empty for the best clips of the topics"
          onChange={(event) => setPrompt(event.target.value)}
          className={cn(INPUT, "mt-1.5 h-9")}
        />
      </>
    );
  }

  return (
    <DialogFrame
      title="Topics"
      description="Clip only the parts of the video you choose. Your current clips are kept."
      onClose={onClose}
      wide
    >
      {body}
      <div className="mt-6 flex flex-wrap justify-end gap-2">
        <Dialog.Close asChild>
          <Button type="button" variant="outline">
            Close
          </Button>
        </Dialog.Close>
        <Button
          type="button"
          variant="outline"
          disabled={make.isPending || chapters.isPending}
          onClick={() =>
            make.mutate(undefined, { onSuccess: () => setChosen(new Set()) })
          }
        >
          {make.isPending && (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          )}
          {make.isPending
            ? "Finding topics…"
            : list.length === 0
              ? "Find topics"
              : "Find topics again"}
        </Button>
        {list.length > 0 && (
          <Button
            type="button"
            disabled={chosen.size === 0 || clip.isPending}
            onClick={submit}
          >
            Clip selected topics{chosen.size > 0 ? ` (${chosen.size})` : ""}
          </Button>
        )}
      </div>
    </DialogFrame>
  );
}
