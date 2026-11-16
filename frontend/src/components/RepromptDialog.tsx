import { useState, type FormEvent } from "react";
import { Dialog } from "radix-ui";
import { useReprompt } from "@/api/projects";
import type { Project } from "@/api/types";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";
import { cn } from "@/lib/utils";

const PROMPT_MAX = 2000;

/**
 * A dialog that asks for a new "find moments about" request and finds the
 * project's clips again from it, without transcribing the video again. The
 * clips so far stay as the previous result set.
 */
export function RepromptDialog({
  project,
  onClose,
}: {
  project: Project;
  onClose: () => void;
}) {
  const [prompt, setPrompt] = useState(project.settings.keyword_prompt ?? "");
  const reprompt = useReprompt(project.id);
  const trimmed = prompt.trim();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!trimmed) return;
    reprompt.mutate(trimmed, { onSuccess: onClose });
  }

  return (
    <DialogFrame
      title="Reprompt"
      description="Find new clips with another request. The video is not transcribed again and your current clips are kept."
      onClose={onClose}
    >
      <form onSubmit={submit} className="mt-4">
        <label htmlFor="reprompt-prompt" className="text-sm font-medium">
          Find moments about
        </label>
        <textarea
          id="reprompt-prompt"
          value={prompt}
          rows={3}
          maxLength={PROMPT_MAX}
          placeholder="e.g. every time the host talks about pricing"
          onChange={(event) => setPrompt(event.target.value)}
          className={cn(INPUT, "mt-1.5 py-2")}
        />
        <div className="mt-6 flex justify-end gap-2">
          <Dialog.Close asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </Dialog.Close>
          <Button type="submit" disabled={!trimmed || reprompt.isPending}>
            Find clips
          </Button>
        </div>
      </form>
    </DialogFrame>
  );
}
