import { useState } from "react";
import { useUpdatePost } from "@/api/posts";
import type { Post } from "@/api/types";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { localInputValue, postTime } from "@/lib/calendar";
import { futureTime } from "@/lib/postForm";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

/** The sheet's "Publish at" field and "Reschedule" button of a draft or
 * scheduled post. */
export function PostReschedule({ post }: { post: Post }) {
  const update = useUpdatePost();
  const at = postTime(post);
  const initial = at ? localInputValue(at) : "";
  const [value, setValue] = useState(initial);
  const moment = futureTime(value);
  const problem =
    value && value !== initial && !moment
      ? "Pick a time later than now."
      : null;

  function reschedule() {
    if (!moment) return;
    update.mutate(
      { id: post.id, patch: { scheduled_at: moment } },
      {
        onSuccess: (saved) =>
          toast.success(
            `Moved to ${new Date(saved.scheduled_at ?? moment).toLocaleString()}.`,
          ),
      },
    );
  }

  return (
    <Field label="Publish at" htmlFor="post-editor-at">
      <div className="flex flex-wrap items-center gap-2">
        <input
          id="post-editor-at"
          type="datetime-local"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className={cn(INPUT, "h-9 sm:w-64")}
        />
        <Button
          variant="outline"
          disabled={!moment || value === initial || update.isPending}
          onClick={reschedule}
        >
          Reschedule
        </Button>
      </div>
      {problem && (
        <p role="status" className="text-caption text-muted-foreground">
          {problem}
        </p>
      )}
    </Field>
  );
}
